# Phase 2A：数据库表结构与 Migration 草案

这份文件用于细化 `Phase 2：数据库与核心持久化`。

它回答三个问题：

1. V1 最少要建哪些表
2. 这些表之间如何关联
3. Migration 应按什么顺序落地

这份文档的目标不是一步到位设计完整交易平台数据库，而是为 `paper trading MVP` 提供一个足够稳、足够清晰的第一版数据库骨架。

---

## 1. 设计目标

V1 数据库设计优先保证：

- 交易状态可持久化
- 重启后核心状态可恢复
- `OrderIntent` 先落库再执行
- 关键状态变化可追踪
- 结构足够简单，便于个人项目维护

V1 不优先追求：

- 极致查询性能
- 多租户和复杂权限
- 多交易所统一超大抽象
- 高级分析型宽表
- 提前建设大而全报表仓库

---

## 2. V1 最小建表清单

### 2.1 必建表

V1 建议最少建立下面 7 张核心表：

1. `signals`
2. `order_intents`
3. `orders`
4. `fills`
5. `positions`
6. `balance_snapshots`
7. `event_logs`

### 2.2 建议延后表

下面这些表可以后置，不要求在 `Phase 2` 一次性建完：

- `pnl_snapshots`
- `strategy_runs`
- `risk_events`
- `model_inference_logs`
- `feature_snapshots`

如果当前实现还没有稳定的 PnL 更新链路，`pnl_snapshots` 可以在 `Phase 5C` 或 `Phase 7` 再补。

---

## 3. 表职责说明

### 3.1 `signals`

用途：

- 持久化策略产生的交易信号
- 让后续 `order_intent` 能追溯到信号来源

建议字段：

- `id`
- `strategy_id`
- `account_id`
- `exchange`
- `symbol`
- `timeframe`
- `signal_type`
- `side`
- `confidence`
- `target_position`
- `reason_summary`
- `status`
- `event_time`
- `created_at`

说明：

- `signal_type` 可以先支持简单枚举，例如 `ENTRY`、`EXIT`、`REDUCE`
- `status` 可以先简单定义为 `NEW / CONSUMED / EXPIRED / REJECTED`

### 3.2 `order_intents`

用途：

- 表示系统内部“准备下单”的正式意图
- 是风控之后、真实下单之前的关键持久化节点

建议字段：

- `id`
- `signal_id`
- `strategy_id`
- `account_id`
- `exchange`
- `symbol`
- `side`
- `order_type`
- `qty`
- `price`
- `time_in_force`
- `reduce_only`
- `idempotency_key`
- `status`
- `risk_decision`
- `risk_reason`
- `created_at`

说明：

- `idempotency_key` 必须唯一
- `risk_decision` 可先支持 `ALLOW / REJECT`

### 3.3 `orders`

用途：

- 表示已经进入执行阶段的订单事实
- 对应 paper execution 或未来 live execution 的订单生命周期

建议字段：

- `id`
- `order_intent_id`
- `exchange_order_id`
- `account_id`
- `exchange`
- `symbol`
- `side`
- `order_type`
- `qty`
- `price`
- `filled_qty`
- `avg_fill_price`
- `status`
- `last_error_code`
- `last_error_message`
- `submitted_at`
- `updated_at`

说明：

- `status` 至少支持：
  `NEW / ACK / PARTIALLY_FILLED / FILLED / CANCELED / REJECTED`
- `exchange_order_id` 在 paper 模式下也建议保留，方便统一语义

### 3.4 `fills`

用途：

- 持久化成交事实
- 作为持仓、余额、PnL 更新的直接输入

建议字段：

- `id`
- `order_id`
- `exchange_fill_id`
- `account_id`
- `exchange`
- `symbol`
- `side`
- `qty`
- `price`
- `fee`
- `fee_asset`
- `liquidity_type`
- `fill_time`
- `created_at`

说明：

- `exchange_fill_id` 如果外部没有，可在本地生成稳定 ID
- `fee` 和 `fee_asset` 尽量保留，后续 PnL 会用到

### 3.5 `positions`

用途：

- 表示当前持仓状态
- 作为 trader 恢复和风控的重要事实源

建议字段：

- `id`
- `account_id`
- `exchange`
- `symbol`
- `side`
- `qty`
- `avg_entry_price`
- `mark_price`
- `unrealized_pnl`
- `realized_pnl`
- `status`
- `updated_at`

说明：

- 对现货来说，`side` 可以先固定为 `LONG`
- 如果第一版只做现货，模型也可以更简单

### 3.6 `balance_snapshots`

用途：

- 持久化账户余额快照
- 支持 trader 恢复和对账

建议字段：

- `id`
- `account_id`
- `exchange`
- `asset`
- `total`
- `available`
- `locked`
- `snapshot_time`
- `created_at`

说明：

- 第一版不必急着做复杂账户维度汇总
- 优先保证每种资产余额可追踪

### 3.7 `event_logs`

用途：

- 保存关键事件审计日志
- 作为问题排查、重放、对账诊断依据

建议字段：

- `id`
- `event_id`
- `event_type`
- `source`
- `account_id`
- `exchange`
- `symbol`
- `related_object_type`
- `related_object_id`
- `event_time`
- `ingest_time`
- `payload_json`
- `created_at`

说明：

- 第一版不用把所有内部事件都强制写进去
- 优先记录关键交易事件和关键账户事件

---

## 4. 表关系草案

V1 推荐的最小关系如下：

```text
signals
  1 -> n order_intents

order_intents
  1 -> n orders

orders
  1 -> n fills

fills
  -> 驱动 positions 更新
  -> 驱动 balance_snapshots 更新

event_logs
  -> 可引用 signal / order_intent / order / fill / position / balance_snapshot
```

更具体地说：

- 一个 `signal` 可以产生 0 到多个 `order_intent`
- 一个 `order_intent` 在第一版通常只对应 1 个主订单，但结构上建议保留 1 对多空间
- 一个 `order` 可以对应多个 `fill`
- `positions` 和 `balance_snapshots` 更像“当前状态”或“快照状态”，不建议直接设计成强外键链路中心

---

## 5. 主键、唯一键与索引建议

### 5.1 主键

推荐所有核心表统一使用应用侧生成的字符串 ID，例如：

- UUID
- ULID

优点：

- 便于跨模块提前生成对象 ID
- 便于先写日志、再写状态对象
- 适合事件驱动场景

### 5.2 唯一键

建议至少有以下唯一约束：

- `order_intents.idempotency_key`
- `orders.exchange_order_id` 在非空时唯一
- `fills.exchange_fill_id` 在非空时唯一
- `event_logs.event_id`

### 5.3 索引

建议优先建立这些索引：

- `signals(strategy_id, symbol, event_time)`
- `order_intents(account_id, symbol, created_at)`
- `orders(account_id, symbol, status, updated_at)`
- `fills(order_id, fill_time)`
- `positions(account_id, symbol)`
- `balance_snapshots(account_id, asset, snapshot_time)`
- `event_logs(event_type, event_time)`

V1 不需要一开始就做复杂复合索引优化，先覆盖最常见查询路径即可。

---

## 6. V1 推荐的 Migration 顺序

建议按下面顺序做 migration：

1. 初始化 Alembic / migration 框架
2. 建立公共审计字段约定
3. 建立 `signals`
4. 建立 `order_intents`
5. 建立 `orders`
6. 建立 `fills`
7. 建立 `positions`
8. 建立 `balance_snapshots`
9. 建立 `event_logs`
10. 增加唯一约束与必要索引

这样做的原因：

- 先落最核心的“意图 -> 订单 -> 成交”链路
- 再补状态与审计
- 最后加索引，避免过早调优

---

## 7. 推荐的实现边界

### 7.1 `Phase 2` 应完成

- 建表
- migration
- 基本 repository / DAO
- 基本幂等写入
- 基本读取和恢复接口

### 7.2 `Phase 2` 不必完成

- 全量复杂查询服务
- 高级报表 SQL
- 完整 PnL 宽表
- 多账户聚合视图
- 大量历史行情仓库优化

---

## 8. 建议的恢复策略

V1 中，数据库恢复重点是“能恢复必要状态”，不是“完整重建所有世界”。

建议最少支持：

- 读取未完成订单
- 读取当前持仓
- 读取最新余额快照
- 读取最近关键事件日志

恢复时的优先顺序：

1. 未完成订单
2. 当前持仓
3. 最新余额
4. 最近事件日志

---

## 9. 推荐测试清单

这部分是在 `testing-standards.md` 基础上的 `Phase 2` 专项测试建议。

### 必测

- migration 可以成功执行
- 所有核心表可以创建
- repository 基本读写可用
- `order_intents.idempotency_key` 唯一约束有效
- 重复写入时不会产生重复关键记录

### 建议测

- 未完成订单查询
- 最新余额快照查询
- 持仓读取和恢复路径
- 关键事件日志写入

---

## 10. 给 AI 的实现建议

如果后面把数据库任务交给 AI，建议优先按下面粒度实现：

1. 先完成 schema 与 migration
2. 再完成 repository / DAO
3. 再补恢复查询接口
4. 最后补 `Phase 5` 所需的执行链路写入能力

不要让 AI 在 `Phase 2` 一次性去做：

- 全项目 ORM 设计
- 完整 service 层
- 高级仓储模式大抽象

---

## 11. 一句话版本

`Phase 2` 的数据库设计重点不是“把所有未来都设计好”，而是：

> 先把 `Signal -> OrderIntent -> Order -> Fill -> Position / Balance` 这条链路需要的最小事实源做稳。
