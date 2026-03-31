# AI 量化交易系统 V1 执行说明

这份文档不是完整架构说明，而是给 AI 或开发助手使用的 `V1 顺序执行文件`。

目标只有一个：

> 按顺序实现一个适合个人项目的、可审计的 `A 股 paper trading MVP`。

这里定义的 `V1` 不包含真实小资金实盘，不包含 AI/ML 训练，不包含多市场数据源，不包含多策略组合。

如果需要把任务进一步拆成适合 AI 单次执行的粒度，请使用本目录下的 phase 文件。

所有 phase 的测试要求，请统一参考：

`testing-standards.md`

工程模板、技术栈和基础实现风格的固定决策，请参考：

`implementation-decisions.md`

---

## 1. V1 的固定边界

AI 在执行时，必须严格遵守下面的边界，不允许擅自扩展：

- 只支持 `1 个市场数据源`
- 只支持 `1 个交易账户`
- 只支持 `1-3 个股票标的`
- 只支持 `1 个主策略`
- 只支持 `分钟级到小时级` 策略
- 第一版市场输入以 `BarEvent` 为主
- 第一版执行模式只做 `paper trading`
- 第一版监控只做 `结构化日志 + Telegram 告警 + 少量 API`
- 第一版数据库以 `PostgreSQL` 为核心

AI 不应在 V1 中主动引入这些内容：

- `TickEvent`
- `OrderBookEvent`
- 多市场数据源
- 多账户
- 多策略组合
- `Redis Streams`
- `Kafka`
- `Kubernetes`
- `Prometheus / Grafana`
- 实盘下单
- 模型训练与在线推理

---

## 2. AI 执行规则

AI 必须按阶段顺序执行，不允许跳阶段。

每个阶段都遵守下面规则：

1. 先完成当前阶段，再进入下一阶段。
2. 当前阶段未完成时，不提前实现下个阶段的复杂能力。
3. 如果当前阶段缺少前置决策，先补文档或配置，不要直接猜完整实现。
4. 每完成一个阶段，必须输出：
   - 已修改文件
   - 已完成能力
   - 测试情况：
     - 已运行哪些测试
     - 哪些通过
     - 哪些未运行
     - 为什么未运行
     - 当前剩余测试风险
   - 未解决风险
   - 是否可以进入下一阶段
5. 如果发现某个能力会显著扩大范围，应停在当前阶段并标记为 `后置项`。
6. `Phase 2` 默认优先采用 `Phase 2A -> Phase 2` 的执行路径；`Phase 5` 默认优先采用 `Phase 5A -> Phase 5B -> Phase 5C` 的执行路径；`Phase 6` 默认优先采用 `Phase 6A -> Phase 6B -> Phase 6C` 的执行路径。
7. 每次交付都必须按 `testing-standards.md` 汇报测试执行情况，不得用“已测试”或“测试通过”替代完整测试汇报。

### 2.1 跨阶段固定契约

下面这些契约不允许留到后续实现时再猜：

- `paper` 模式下不存在外部交易所真相源；`PostgreSQL` 中持久化的 `orders / fills / positions / balance_snapshots` 是唯一可恢复事实源，内存态和 `paper adapter` 内部态只作为运行缓存
- 每次 trader 启动都必须生成新的 `trader_run_id`；`signals / order_intents / orders / fills / event_logs` 或等价事实源必须能关联该运行批次
- 单活 trader 保护默认采用基于 `PostgreSQL` 的账户级 lease；lease 至少要包含 `owner_instance_id`、`lease_expires_at`、`last_heartbeat_at`、`fencing_token`
- V1 的 A 股执行契约固定为 `long-only` 普通股票语义：不做融资融券、不做做空，不允许把当日买入数量在同一交易日再次卖出
- `Signal.target_position` 表示“目标成交后持仓”，不是增量下单量；`OrderIntent.qty` 表示基于当前持仓和交易规则归一化后的实际下单增量
- `order_type = MARKET` 在 V1 中只是 paper execution 下的“市价风格指令”，不代表交易所原生市价单；其 sizing、名义价值计算和风险判断默认使用最近一次可接受 `BarEvent.close` 作为 `decision_price`；V1 默认策略下单路径只要求支持连续竞价时段的 `MARKET` 风格指令；如果实现里保留 `LIMIT` 单，只有在系统能提供用于 A 股价格有效性、涨跌停和交易时段校验的最小 market state 输入时才允许启用
- `time_in_force` 字段可以保留为统一契约，但 V1 A 股固定为 `DAY`
- 每个支持的 symbol 都必须有明确的 A 股交易规则配置；至少包含 `lot_size`、`qty_step`、`price_tick`、`min_qty`、`allow_odd_lot_sell`、`t_plus_one_sell`、`price_limit_pct`
- 如果 V1 保留 `LIMIT` 单、涨跌停检查或交易时段检查，collector 或等价 market state 输入必须至少提供 `trade_date`、`previous_close`、`upper_limit_price`、`lower_limit_price`、`trading_phase`、`suspension_status`
- `Position` 或等价恢复事实必须能区分 `qty` 与 `sellable_qty`；所有卖单风控、减仓判断和保护模式放行边界都以 `sellable_qty` 为准，而不是只看总持仓；当 `0 < sellable_qty < lot_size` 时，应允许按 A 股语义执行一次性余股卖出
- V1 的策略触发只消费 `closed / final bar`；未收盘 bar 更新只允许用于缓存、替换或观测，不直接触发策略和下单
- 历史补数和实时 bar 必须基于稳定 bar key 去重；推荐至少使用 `exchange + symbol + timeframe + bar_start_time` 或等价时间窗口标识
- `kill switch` 默认是操作者触发的“减仓 / 平仓保护”闸门：拒绝新开仓和增仓，允许 `cancel all`、减仓和平仓；如果实现里保留 `reduce_only` 字段，它只作为该保护语义的兼容标记
- `protection mode` 默认是系统触发的“减仓 / 平仓保护”安全状态：拒绝新开仓和增仓，进入时取消所有非减仓 / 平仓保护挂单，并保留减仓和平仓路径
- paper fill、余额和 PnL 从 `Phase 5` 起就必须纳入 A 股成本模型；至少能表达佣金、过户费和卖出印花税，不能等到 `Phase 8` 才第一次引入成本
- 风控可以缩单或拒单，但不应重新解释 `Signal` 的字段语义；如果语义不明确，应先补文档而不是直接实现

---

## 3. V1 完成线

只有当下面这些条件全部成立时，V1 才算完成：

- 可以稳定接入并标准化 `BarEvent`
- 可以运行 `1 个主策略`
- 可以生成 `Signal`
- 所有下单动作都先经过 `Pre-Trade Risk`
- 所有 `OrderIntent` 都先落库，再进入 `paper execution`
- 可以记录 `Order / Fill / Position / Balance`
- 系统重启后可以恢复核心状态
- 可以人工查询状态、启停策略、触发 `kill switch`
- 可以进行最小对账，发现异常时进入保护模式
- 可以按时间段、运行批次或等价维度回放关键事件用于排查
- 可以跑通一套基线策略的 paper 闭环

---

## 4. 建议目录目标

AI 在执行 V1 时，建议尽量围绕下面的目录落代码：

```text
apps/
  api/
  trader/
  collector/
  research/

src/
  domain/
    events/
    strategy/
    risk/
    portfolio/
    execution/
    reconciliation/
  infra/
    db/
    exchanges/
    messaging/
    observability/
  services/
    backtest/
  config/
  shared/

tests/
  unit/
  integration/
  e2e/
```

如果项目当前还没有完整脚手架，AI 可以先创建最小目录结构，但不要一次性填满所有模块。

---

## 4.1 测试规范

V1 的测试规范、测试层级、测试手段、最低门槛和交付汇报格式，统一由下列文档定义：

`testing-standards.md`

所有 phase 的“最低验证要求”是局部门槛；  
真正执行时，还必须同时满足 `testing-standards.md` 中的全局规则。

---

## 4.2 技术栈基线

V1 默认技术栈如下：

- `Python 3.12`
- `uv`
- `FastAPI`
- `Pydantic v2 + pydantic-settings`
- `SQLAlchemy 2.0 + Alembic + psycopg`
- `structlog`
- `pytest`

除非当前阶段明确需要，否则 AI 不应自行切换到其他主框架。

如果需要更细的工程模板和技术栈决策，请优先阅读：

`implementation-decisions.md`

---

## 5. 顺序执行计划

下面是 AI 必须遵守的执行顺序。

---

## Phase 0：先定范围和配置骨架

### 目标

把 V1 的业务边界、运行模式和基础配置先固定下来。

### 依赖

无

### 要做的事

- 明确市场数据源、市场类型、股票标的、周期
- 明确 `paper` 是唯一执行模式
- 建立基础配置结构
- 建立环境区分，例如 `dev`
- 明确关键配置与 secret 的必填/选填契约
- 对关键配置做 fail-fast 校验
- 建立最小日志配置
- 明确 `paper` 模式下本地持久化状态是唯一可恢复事实源
- 明确运行时 `trader_run_id` 会在 trader 启动时生成并进入日志 / 审计上下文

### 产出物

- 范围说明文档
- 配置文件骨架
- 环境变量样例或等价配置契约
- 应用启动所需的基础设置

### 完成标准

- AI 不再把需求理解成“通用平台”
- 必填配置、缺省策略和 secret 契约已经明确
- 缺失关键配置时会明确失败而不是静默使用错误值
- 代码中已经能读到固定范围配置
- `paper` 模式的事实源边界和运行时标识约定已经明确

### 禁止扩展

- 不接交易所
- 不建数据库表
- 不实现策略逻辑

---

## Phase 1：标准事件模型和领域对象

### 目标

先统一交易语义，让后续 collector、trader、backtest、paper execution 都能共用。

### 依赖

- Phase 0

### 要做的事

- 定义 `BarEvent`
- 定义 `Signal`
- 定义 `OrderIntent`
- 定义 `Order`
- 定义 `Fill`
- 定义 `Position`
- 定义 `BalanceSnapshot`
- 定义订单状态枚举和状态流转规则
- 统一时间字段和 ID 字段

### 产出物

- `domain/events`
- `domain/execution`
- `domain/portfolio`
- `domain/strategy` 中的核心类型

### 完成标准

- 核心对象有稳定 schema
- `OrderIntent` 与 `Order` 语义清晰分离
- 订单状态机有单元测试

### 禁止扩展

- 不写真实下单逻辑
- 不接数据库实现细节
- 不引入 Tick / OrderBook 模型

---

## Phase 2：数据库与核心持久化

### 目标

建立交易系统的本地事实源。

### 依赖

- Phase 1

### 推荐执行拆分

默认推荐按下面顺序执行；如果当前改动已经足够小，也可以直接做 `Phase 2`：

1. 先完成 `Phase 2A`：数据库表结构与 Migration 草案
2. 再回到 `Phase 2`：补齐 repository、幂等写入和恢复基础能力

### 要做的事

- 建立数据库连接与 migration 机制
- 为 `Signal / OrderIntent / Order / Fill / Position / BalanceSnapshot` 建表
- 建立事件日志表或等价审计表
- 建立 repository / DAO 抽象
- 支持幂等更新

### 产出物

- `infra/db`
- 数据库 schema
- migration 文件

### 完成标准

- 可以独立写入和查询核心交易状态
- 系统重启后能从数据库恢复必要状态
- 状态更新有幂等保护

### 禁止扩展

- 不接行情
- 不写策略运行时
- 不做复杂查询优化

---

## Phase 3：Collector 与 Market Gateway

### 目标

把外部市场数据转成统一的 `BarEvent`。

### 依赖

- Phase 1
- Phase 2

### 要做的事

- 接入单一市场数据源的历史 K 线
- 接入单一市场数据源的实时 K 线或等价 bar 数据
- 统一 `symbol`、时区、精度
- 建立稳定的 bar 唯一键，并对历史补数与实时数据做去重
- 保存原始 payload
- 输出标准化 `BarEvent`
- 明确只有 `closed / final bar` 可以进入可交易链路
- 处理断线重连和补数

### 产出物

- `apps/collector`
- `infra/exchanges`
- `domain/market` 或等价模块

### 完成标准

- 可以稳定采集并标准化 bar 数据
- collector 异常恢复后可以继续工作
- 关键市场数据可以写入本地持久层或事件日志
- 重复 bar 不会重复进入可交易事件链路
- 未收盘 bar 不会直接触发策略运行时

### 禁止扩展

- 不实现 Tick / OrderBook
- 不接多市场数据源
- 不为追求低延迟引入复杂消息系统

---

## Phase 4：Trader 主循环与进程内 Event Bus

### 目标

把 collector 输出送入统一交易主循环。

### 依赖

- Phase 1
- Phase 2
- Phase 3

### 要做的事

- 建立 trader 主进程
- 建立进程内 dispatcher 或 `asyncio queue`
- 建立事件订阅机制
- 让 `BarEvent` 可以进入策略运行时
- 建立清晰的 trader 启停生命周期边界
- 为后续 `health / readiness` 与单活保护预留运行状态接入点
- 在 trader 启动时生成 `trader_run_id`，并把它接入日志上下文、运行状态和后续关键事件

### 产出物

- `apps/trader`
- `infra/messaging`

### 完成标准

- trader 能消费标准事件
- 模块之间通过统一事件流衔接
- 主循环生命周期边界清晰，便于控制面接管
- 不依赖 Redis 也能跑通主链路
- 运行中的 `trader_run_id` 可被后续控制面、审计和回放链路读取

### 禁止扩展

- 不引入 `Redis Streams`
- 不拆远程微服务
- 不实现复杂调度系统

---

## Phase 5：OMS、Portfolio State 与 Paper Execution

### 目标

跑通最核心的交易闭环。

### 依赖

- Phase 1
- Phase 2
- Phase 4

### 推荐执行拆分

默认推荐按下面顺序执行；只有当前改动已经非常小、明确只需补一处闭环缺口时，才直接做 `Phase 5` 总任务：

1. 先完成 `Phase 5A`：OMS 持久化与状态机
2. 再完成 `Phase 5B`：Paper Execution Adapter
3. 最后完成 `Phase 5C`：Portfolio / Balance / PnL 更新

### 要做的事

- 实现 `Signal -> OrderIntent`
- 固定 `Signal.target_position -> OrderIntent.qty` 的 sizing 契约
- 实现 OMS 持久化流程
- 实现 `paper execution adapter`
- 模拟 `ACK / PARTIAL / FILL / REJECT / CANCEL`
- 更新 `Position / Balance / PnL`

### 产出物

- `domain/execution`
- `domain/portfolio`
- `infra/exchanges` 中的 `paper adapter`

### 完成标准

- 可以跑通完整 paper 闭环
- 所有状态变化都可以落库
- 重启后能恢复订单、持仓、余额
- `Signal`、当前持仓、`decision_price` 与 `OrderIntent.qty` 之间的转换规则是确定且可复现的

### 禁止扩展

- 不接真实 live 下单
- 不做复杂执行算法
- 不做多账户资金分配

---

## Phase 6：Pre-Trade Risk 与最小控制面

### 目标

让系统具备基本安全性和人工介入能力。

### 依赖

- Phase 5

### 推荐执行拆分

默认推荐按下面顺序执行；只有当前改动已经非常小、明确只需补一处控制或安全缺口时，才直接做 `Phase 6` 总任务：

1. 先完成 `Phase 6A`：Pre-Trade Risk Rules
2. 再完成 `Phase 6B`：API 与操作控制
3. 最后完成 `Phase 6C`：告警与安全运维

### 要做的事

- 实现最大仓位检查
- 实现最大名义价值检查
- 实现重复下单防护
- 实现行情过期检查
- 实现最小下单量和交易规则检查
- 实现策略启停
- 实现状态查询 API
- 实现 `kill switch`
- 实现 `cancel all`
- 提供健康检查与就绪检查
- 限制同一交易账户只允许 `1 个 active trader` 实例
- 基于 `PostgreSQL` lease + heartbeat + fencing token 明确单活语义
- 明确 `kill switch` 的动作边界：禁止新开仓 / 增仓，但允许 `cancel all`、减仓和平仓
- 接入 Telegram 告警

### 产出物

- `domain/risk`
- `apps/api`
- `infra/observability`

### 完成标准

- 所有下单动作必须经过统一风险闸门
- 风险拒绝有明确原因
- 可以通过 API 或控制面人工接管系统
- 操作者可以判断系统是否健康与就绪
- 同一交易账户不会被多个 active trader 实例同时接管
- lease 过期或 fencing 失效的实例不会继续提交新订单
- `kill switch` 不会阻断减仓 / 平仓保护单、减仓或平仓路径

### 禁止扩展

- 不做复杂 RBAC
- 不做完整 dashboard
- 不做复杂动态风控模型

---

## Phase 7：基线策略与端到端 Paper 验证

### 目标

用一套简单可解释的策略验证交易内核。

### 依赖

- Phase 6

### 要做的事

- 实现一套简单规则策略，例如均线或动量
- 记录策略输入快照、输出信号、原因摘要
- 跑通端到端 paper 流程
- 输出最小交易结果摘要

### 产出物

- `domain/strategy`
- 对应测试和示例配置

### 完成标准

- 至少 1 套基线策略能在 paper 模式稳定运行
- 策略能持续产生可审计的信号与订单记录

### 禁止扩展

- 不引入 AI 推理
- 不做多策略调度
- 不做复杂因子库

---

## Phase 8：最小 Backtest 一致性

### 目标

让同一套策略接口能用于研究验证，而不是做两套逻辑。

### 依赖

- Phase 7

### 要做的事

- 建立最小事件驱动回测器
- 复用相同策略接口
- 复用相同订单语义
- 加入与 paper 一致的 A 股成本模型和简单滑点，至少覆盖佣金、过户费和卖出印花税
- 输出 run manifest 或等价元数据，记录策略、参数、数据和成本假设
- 输出标准绩效摘要

### 产出物

- `services/backtest`
- `apps/research`
- 回测 run manifest 或等价元数据

### 完成标准

- 同一策略可以运行在 backtest 和 paper
- 回测结果可复现，且能追溯策略、数据、参数和成本假设
- 报表至少包含收益、回撤、交易次数等基础指标

### 禁止扩展

- 不建设完整研究平台
- 不做大规模参数搜索
- 不接 AI/ML pipeline

---

## Phase 9：最小对账与保护模式

### 目标

保证系统出现异常时不会继续带病运行。

### 依赖

- Phase 5
- Phase 6

### 要做的事

- 实现启动恢复
- 实现定时对账
- 在 `paper` 模式下，以本地持久化 `orders / fills / positions / balance_snapshots` 为对账真相源
- 检查订单、持仓、余额漂移
- 对账异常时进入保护模式
- 进入保护模式后取消所有非减仓 / 平仓保护挂单，并保留减仓和平仓路径
- 记录诊断信息并发送告警
- 提供最小事件回放或诊断入口，例如 `replay_events` 或等价工具，至少支持 `time range / trader_run_id / account_id / symbol`

### 产出物

- `domain/reconciliation`
- 对账与回放脚本或任务入口

### 完成标准

- 能发现状态漂移
- 能阻止系统在异常状态下继续开新仓
- 能留存足够排查信息
- 关键异常可以结合审计记录进行最小回放或复盘
- 回放与诊断入口可以按运行批次读取关键交易事件
- 保护模式的动作边界清晰：禁新开 / 增仓，允减仓 / 平仓，可执行 `cancel all`

### 禁止扩展

- 不追求全自动修复
- 不实现复杂自愈系统

---

## 6. 推荐执行顺序摘要

AI 执行时，只允许按下面顺序前进：

1. `Phase 0`：范围和配置骨架
2. `Phase 1`：事件模型和领域对象
3. `Phase 2A`：数据库表结构与 Migration 草案
4. `Phase 2`：数据库与核心持久化
5. `Phase 3`：Collector 与 Market Gateway
6. `Phase 4`：Trader 主循环与进程内 Event Bus
7. `Phase 5A`：OMS 持久化与状态机
8. `Phase 5B`：Paper Execution Adapter
9. `Phase 5C`：Portfolio / Balance / PnL 更新
10. `Phase 6A`：Pre-Trade Risk Rules
11. `Phase 6B`：API 与操作控制
12. `Phase 6C`：告警与安全运维
13. `Phase 7`：基线策略 + 端到端 Paper 验证
14. `Phase 8`：最小 Backtest 一致性
15. `Phase 9`：最小对账与保护模式

如果 `Phase 5` 还没有稳定跑通，就不应该进入 `Phase 8` 和 `Phase 9` 之后的扩展工作。

---

## 7. V1 完成后再考虑的内容

只有 V1 完成后，AI 才可以进入这些后续主题：

- 小资金 live trading
- 更完善的对账修复
- 特征工程 pipeline
- 传统 ML 模型
- 在线推理
- 多策略组合
- 多品种扩展
- 更细粒度执行逻辑

---

## 8. 一句话交付定义

如果 AI 最终交付的是下面这个系统，就算 V1 成功：

> 一个单市场数据源、单账户、单策略、K 线驱动、可审计、可回放、带基础风控与保护模式的 A 股 paper trading 系统。
