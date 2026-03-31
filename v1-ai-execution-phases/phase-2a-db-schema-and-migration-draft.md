# Phase 2A：数据库表结构与 Migration 草案

这份文件用于细化 `Phase 2：数据库与核心持久化`。

这份文件既是数据库设计草案，也是 `Phase 2` 默认推荐先执行的单次任务文件。

## 本次目标

先把 V1 的数据库 schema、关键约束和初始 migration 骨架做稳，不在这一阶段扩展到完整 repository 和恢复逻辑。

## 前置依赖

- `Phase 1：事件模型与领域对象`

## 必读上下文

- `./00-master-plan.md`
- `./testing-standards.md`
- `./implementation-decisions.md`
- `./phase-1-domain-model.md`
- `./phase-2-db-and-persistence.md`

## 允许修改范围

- `src/infra/db/`
- `migrations/` 或等价目录
- `src/domain/execution/` 中与 schema 对齐相关的少量代码
- `src/domain/portfolio/` 中与 schema 对齐相关的少量代码
- `tests/unit/`
- `tests/integration/`
- 当前文档

## 本次必须完成的任务

- 初始化 migration 框架或等价机制
- 明确并落地核心表结构
- 明确并落地主键、唯一键、必要索引
- 让 schema 与 `Signal -> OrderIntent -> Order -> Fill -> Position / Balance` 主链路对齐
- 产出可执行的第一版 migration 骨架

## 本次不要做

- 不实现完整 repository 层
- 不实现完整恢复服务
- 不做复杂分析型表设计
- 不提前建设大而全查询层

## 完成标准

- 初始 migration 可以表达 V1 核心表结构
- 关键唯一约束和基础索引已明确
- schema 设计与主链路一致

## 最低验证要求

- 至少验证 migration 可以创建核心表
- 至少验证 1 组关键唯一约束
- 至少验证 1 组基础读写路径

## 本次交付时必须汇报

- 建了哪些表
- 哪些唯一约束和索引已经落地
- 当前哪些能力刻意留到 `Phase 2` 主任务或后续阶段

## 可直接复制给 AI 的执行提示词

```text
你现在负责本项目的 Phase 2A：数据库表结构与 Migration 草案。

请先阅读：
- ./00-master-plan.md
- ./testing-standards.md
- ./implementation-decisions.md
- ./phase-2-db-and-persistence.md
- ./phase-2a-db-schema-and-migration-draft.md
- ./phase-1-domain-model.md

本次只允许修改：
- src/infra/db/
- migrations/ 或等价目录
- src/domain/execution/ 中与 schema 对齐相关的少量代码
- src/domain/portfolio/ 中与 schema 对齐相关的少量代码
- tests/unit/
- tests/integration/
- 当前文档

本次必须完成：
- 初始化 migration 框架或等价机制
- 明确并落地核心表结构
- 明确并落地主键、唯一键、必要索引
- 产出可执行的第一版 migration 骨架

严格不要做：
- 不实现完整 repository 层
- 不实现完整恢复服务
- 不做复杂分析型表设计
- 不提前建设大而全查询层

完成后请输出：
1. 已修改文件
2. 已完成能力
3. 新增或确认的 schema / migration
4. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
5. 未解决风险
6. 是否可以进入 Phase 2 主实现
```

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
- 可以按 `trader_run_id` 或等价运行批次回放关键交易事件
- A 股执行约束可以被明确表达，例如 `DAY`、`T+1` 卖出限制和 `sellable_qty`
- A 股成本模型和最小 market state 上下文可以被审计与回放
- 结构足够简单，便于个人项目维护

V1 不优先追求：

- 极致查询性能
- 多租户和复杂权限
- 多市场数据源统一超大抽象
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

即使 `strategy_runs` 或等价表后置，V1 也仍然要求核心交易事实至少能关联 `trader_run_id`。

V1 的 symbol 交易规则优先固定在配置中，不要求在 `Phase 2A` 额外引入 `symbol_rules` 表；但 schema 必须能表达这些规则带来的结果，例如归一化后的 `qty`、固定 `DAY` 有效期、`sellable_qty`、余股一次性卖出例外，以及从 `Phase 5` 起落地的成本字段。如果 V1 保留 `LIMIT` 单，审计链路还必须能恢复对应的最小 market state 上下文。

---

## 3. 表职责说明

### 3.1 `signals`

用途：

- 持久化策略产生的交易信号
- 让后续 `order_intent` 能追溯到信号来源

建议字段：

- `id`
- `strategy_id`
- `trader_run_id`
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
- `target_position` 表示目标成交后的绝对持仓，不表示本次下单增量

### 3.2 `order_intents`

用途：

- 表示系统内部“准备下单”的正式意图
- 是风控之后、真实下单之前的关键持久化节点

建议字段：

- `id`
- `signal_id`
- `strategy_id`
- `trader_run_id`
- `account_id`
- `exchange`
- `symbol`
- `side`
- `order_type`
- `qty`
- `price`
- `decision_price`
- `market_context_json`
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
- `time_in_force` 字段可以保留为统一契约，但 V1 A 股固定为 `DAY`
- `reduce_only` 字段可以保留为兼容标记，但在 V1 语义中只表示“减仓 / 平仓保护”，不表示衍生品双向持仓语义
- `qty` 表示已经过精度和 lot 规则归一化后的实际下单增量；买单和标准卖单都应遵守 `lot_size / qty_step`，卖单除归一化外还必须受 `sellable_qty` 约束；当 `0 < sellable_qty < lot_size` 且配置允许时，应支持一次性余股卖出例外
- `decision_price` 用于记录生成 `OrderIntent` 时采用的参考价格；`order_type = MARKET` 仅表示 paper execution 下的市价风格指令，默认取最近可接受 `BarEvent.close`
- `market_context_json` 建议保存用于风险与价格有效性判断的最小市场上下文，例如 `trade_date`、`previous_close`、`upper_limit_price`、`lower_limit_price`、`trading_phase`、`suspension_status`
- 如果 V1 保留 `LIMIT` 单，`price` 必须显式给出；且只有在 `market_context_json` 或等价审计路径可恢复对应市场上下文时，才允许启用

### 3.3 `orders`

用途：

- 表示已经进入执行阶段的订单事实
- 对应 paper execution 或未来 live execution 的订单生命周期

建议字段：

- `id`
- `order_intent_id`
- `trader_run_id`
- `exchange_order_id`
- `account_id`
- `exchange`
- `symbol`
- `side`
- `order_type`
- `time_in_force`
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
- `time_in_force` 在 V1 A 股中固定为 `DAY`
- `exchange_order_id` 在 paper 模式下也建议保留，方便统一语义

### 3.4 `fills`

用途：

- 持久化成交事实
- 作为持仓、余额、PnL 更新的直接输入

建议字段：

- `id`
- `order_id`
- `trader_run_id`
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
- `fee` 建议从 `Phase 5` 起就能表达 A 股成本模型的结果，至少包括佣金、过户费和卖出印花税

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
- `sellable_qty`
- `avg_entry_price`
- `mark_price`
- `unrealized_pnl`
- `realized_pnl`
- `status`
- `updated_at`

说明：

- 对现货来说，`side` 可以先固定为 `LONG`
- `sellable_qty` 必须满足 `0 <= sellable_qty <= qty`，用于表达 A 股 `T+1` 可卖约束
- 当日买入成交会先增加 `qty`，但在下一个交易日或等价释放流程前，不应进入 `sellable_qty`

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
- 余额变化需要能对齐成交成本，避免后续对账时把佣金、过户费或卖出印花税遗漏为“现金漂移”

### 3.7 `event_logs`

用途：

- 保存关键事件审计日志
- 作为问题排查、重放、对账诊断依据

建议字段：

- `id`
- `event_id`
- `event_type`
- `source`
- `trader_run_id`
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
- 如果 V1 保留 `LIMIT`、涨跌停或交易时段风控，关键市场状态事件也应可回放，至少要能追溯下单时使用的 `previous_close / price band / trading_phase / suspension_status`

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
- `event_logs` 应能通过 `trader_run_id + event_time` 回放单次运行中的关键链路

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
- `signals(trader_run_id, event_time)`
- `order_intents(account_id, symbol, created_at)`
- `order_intents(trader_run_id, created_at)`
- `orders(account_id, symbol, status, updated_at)`
- `orders(trader_run_id, updated_at)`
- `fills(order_id, fill_time)`
- `positions(account_id, symbol)`
- `balance_snapshots(account_id, asset, snapshot_time)`
- `event_logs(event_type, event_time)`
- `event_logs(trader_run_id, event_time)`

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
