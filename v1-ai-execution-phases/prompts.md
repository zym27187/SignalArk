# V1 AI 执行提示词汇总

这份文件把 V1 的执行提示词统一整理在一起，方便直接复制给 AI。

使用规则：

1. 每次只使用 `1 个提示词`
2. 当前阶段未完成前，不进入下一个阶段
3. `Phase 5` 和 `Phase 6` 如果范围偏大，优先使用它们的子任务提示词
4. 所有提示词都必须遵守总纲文件：
   - `v1-ai-execution-phases/00-master-plan.md`

推荐阅读顺序：

1. `v1-ai-execution-phases/00-master-plan.md`
2. `v1-ai-execution-phases/README.md`
3. 复制本文件中的某一个提示词交给 AI

---

## Prompt 0：Phase 0 范围与配置骨架

```text
你现在负责本项目的 Phase 0：范围与配置骨架。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/phase-0-scope-and-config.md

本次只允许修改：
- configs/
- src/config/
- src/shared/ 中与配置直接相关的少量代码
- 范围说明文档

本次必须完成：
- 固定交易所、市场类型、交易对、周期、运行模式
- 明确 V1 只做 paper trading
- 建立基础配置结构和最小日志配置
- 把单交易所、单账户、单策略、Bar 驱动边界写清楚

严格不要做：
- 不接交易所
- 不建数据库表
- 不实现策略逻辑

完成后请输出：
1. 已修改文件
2. 已完成能力
3. 测试或验证结果
4. 未解决风险
5. 是否可以进入 Phase 1
```

---

## Prompt 1：Phase 1 事件模型与领域对象

```text
你现在负责本项目的 Phase 1：事件模型与领域对象。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/phase-1-domain-model.md
- v1-ai-execution-phases/phase-0-scope-and-config.md

本次只允许修改：
- src/domain/events/
- src/domain/strategy/
- src/domain/execution/
- src/domain/portfolio/
- tests/unit/

本次必须完成：
- 定义 BarEvent、Signal、OrderIntent、Order、Fill、Position、BalanceSnapshot
- 统一时间字段和 ID 字段
- 定义订单状态枚举和状态流转规则
- 明确 Signal 不是订单、OrderIntent 先于 Order

严格不要做：
- 不接数据库
- 不接交易所
- 不实现真实执行逻辑
- 不引入 Tick / OrderBook

完成后请输出：
1. 已修改文件
2. 新增的核心对象和字段
3. 订单状态机说明
4. 测试结果
5. 是否可以进入 Phase 2
```

---

## Prompt 2：Phase 2 数据库与核心持久化

```text
你现在负责本项目的 Phase 2：数据库与核心持久化。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/phase-2-db-and-persistence.md
- v1-ai-execution-phases/phase-1-domain-model.md

本次只允许修改：
- src/infra/db/
- migrations/ 或等价目录
- src/domain/execution/ 中与持久化接口相关的少量代码
- src/domain/portfolio/ 中与持久化接口相关的少量代码
- tests/unit/
- tests/integration/

本次必须完成：
- 建立数据库连接与 migration 机制
- 为 Signal、OrderIntent、Order、Fill、Position、BalanceSnapshot 建表
- 建立事件日志或审计表
- 建立 repository / DAO 抽象
- 支持幂等更新和基础恢复能力

严格不要做：
- 不接行情
- 不写策略运行时
- 不做复杂查询优化

完成后请输出：
1. 已修改文件
2. 新增表结构
3. 已可持久化对象
4. 测试结果
5. 是否可以进入 Phase 3
```

---

## Prompt 3：Phase 3 Collector 与 Market Gateway

```text
你现在负责本项目的 Phase 3：Collector 与 Market Gateway。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/phase-3-collector-and-market-gateway.md
- v1-ai-execution-phases/phase-1-domain-model.md
- v1-ai-execution-phases/phase-2-db-and-persistence.md

本次只允许修改：
- apps/collector/
- src/infra/exchanges/
- src/domain/market/ 或等价目录
- 与 BarEvent 标准化直接相关的少量代码
- tests/unit/
- tests/integration/

本次必须完成：
- 接入单一交易所的历史和实时 bar 数据
- 统一 symbol、时区、精度
- 标准化为 BarEvent
- 保留原始 payload 或最小原始记录
- 处理基本断线重连和补数

严格不要做：
- 不实现 Tick
- 不实现 OrderBook
- 不接多交易所
- 不引入复杂消息中间件

完成后请输出：
1. 已修改文件
2. 接入了什么市场数据
3. BarEvent 生成路径
4. 恢复/补数能力
5. 是否可以进入 Phase 4
```

---

## Prompt 4：Phase 4 Trader 主循环与 Event Bus

```text
你现在负责本项目的 Phase 4：Trader 主循环与 Event Bus。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/phase-4-trader-loop-and-event-bus.md
- v1-ai-execution-phases/phase-3-collector-and-market-gateway.md

本次只允许修改：
- apps/trader/
- src/infra/messaging/
- 与事件订阅分发直接相关的少量代码
- tests/unit/
- tests/integration/

本次必须完成：
- 建立 trader 主进程或等价入口
- 建立进程内 dispatcher 或 asyncio queue
- 建立事件订阅和处理机制
- 让 BarEvent 可以进入 trader
- 为 strategy / risk / OMS 预留清晰接入点

严格不要做：
- 不引入 Redis Streams
- 不拆远程微服务
- 不实现复杂调度系统

完成后请输出：
1. 已修改文件
2. 主循环启动方式
3. 事件分发机制
4. 测试结果
5. 是否可以进入 Phase 5
```

---

## Prompt 5：Phase 5 OMS 与 Paper Execution

```text
你现在负责本项目的 Phase 5：OMS 与 Paper Execution。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/phase-5-oms-and-paper-execution.md
- v1-ai-execution-phases/phase-1-domain-model.md
- v1-ai-execution-phases/phase-2-db-and-persistence.md
- v1-ai-execution-phases/phase-4-trader-loop-and-event-bus.md

本次只允许修改：
- src/domain/execution/
- src/domain/portfolio/
- src/infra/exchanges/ 中的 paper adapter
- apps/trader/
- tests/unit/
- tests/integration/
- tests/e2e/

本次必须完成：
- 实现 Signal -> OrderIntent
- 实现 OrderIntent 先落库再执行
- 实现 OMS 持久化流程
- 实现 paper execution adapter
- 支持 ACK / PARTIAL / FILL / REJECT / CANCEL
- 更新 Position / Balance / PnL

严格不要做：
- 不接真实 live 下单
- 不做复杂执行算法
- 不做多账户资金分配
- 不提前做 sandbox/live 平台化

完成后请输出：
1. 已修改文件
2. OMS 事实源设计
3. paper execution 如何模拟成交
4. 测试结果
5. 是否可以进入 Phase 6
```

---

## Prompt 5A：OMS 持久化与状态机

```text
你现在负责本项目的 Phase 5A：OMS 持久化与状态机。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/phase-5-oms-and-paper-execution.md
- v1-ai-execution-phases/phase-5a-oms-persistence-and-state-machine.md

本次只允许修改：
- src/domain/execution/
- src/infra/db/ 中与 OMS 直接相关的少量代码
- apps/trader/
- tests/unit/
- tests/integration/

本次必须完成：
- 实现 Signal -> OrderIntent
- 实现 OrderIntent 先落库再执行的流程骨架
- 实现 OMS 核心持久化接口
- 明确并落地订单状态机

严格不要做：
- 不实现 paper fill 细节
- 不更新完整持仓和余额
- 不接真实下单

完成后请输出：
1. 已修改文件
2. OMS 事实源设计
3. 订单状态机说明
4. 测试结果
5. 是否可以进入 Phase 5B
```

---

## Prompt 5B：Paper Execution Adapter

```text
你现在负责本项目的 Phase 5B：Paper Execution Adapter。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/phase-5-oms-and-paper-execution.md
- v1-ai-execution-phases/phase-5a-oms-persistence-and-state-machine.md
- v1-ai-execution-phases/phase-5b-paper-execution-adapter.md

本次只允许修改：
- src/infra/exchanges/ 中的 paper adapter
- src/domain/execution/ 中与执行适配相关的少量代码
- apps/trader/
- tests/unit/
- tests/integration/

本次必须完成：
- 实现 paper execution adapter
- 支持 ACK / PARTIAL / FILL / REJECT / CANCEL
- 输出标准订单更新和成交事件
- 与 OMS 正确衔接

严格不要做：
- 不接真实交易所
- 不做复杂撮合算法
- 不更新完整组合账本

完成后请输出：
1. 已修改文件
2. adapter 如何模拟执行
3. 已覆盖的订单状态
4. 测试结果
5. 是否可以进入 Phase 5C
```

---

## Prompt 5C：Portfolio / Balance / PnL 更新

```text
你现在负责本项目的 Phase 5C：Portfolio / Balance / PnL 更新。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/phase-5-oms-and-paper-execution.md
- v1-ai-execution-phases/phase-5a-oms-persistence-and-state-machine.md
- v1-ai-execution-phases/phase-5b-paper-execution-adapter.md
- v1-ai-execution-phases/phase-5c-portfolio-balance-and-pnl.md

本次只允许修改：
- src/domain/portfolio/
- apps/trader/
- 与状态更新衔接相关的少量 execution 代码
- tests/unit/
- tests/integration/

本次必须完成：
- 处理 Fill 对 Position 的影响
- 处理余额变动
- 生成基础 PnL 更新
- 支持关键状态恢复

严格不要做：
- 不做复杂绩效分析
- 不做多账户汇总
- 不引入高级风险归因

完成后请输出：
1. 已修改文件
2. 持仓/余额/PnL 更新规则
3. 恢复能力说明
4. 测试结果
5. 是否可以认为 Phase 5 已完成
```

---

## Prompt 6：Phase 6 Risk 与最小控制面

```text
你现在负责本项目的 Phase 6：Risk 与最小控制面。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/phase-6-risk-and-control-plane.md
- v1-ai-execution-phases/phase-5-oms-and-paper-execution.md

本次只允许修改：
- src/domain/risk/
- apps/api/
- src/infra/observability/
- apps/trader/
- tests/unit/
- tests/integration/

本次必须完成：
- 实现最大仓位、最大名义价值、重复下单、行情过期、最小下单量等 pre-trade risk
- 提供状态查询接口
- 提供策略启停、kill switch、cancel all
- 接入最小 Telegram 告警

严格不要做：
- 不做完整 dashboard
- 不做复杂 RBAC
- 不做复杂动态风控
- 不做全量监控平台

完成后请输出：
1. 已修改文件
2. 已实现的风控规则
3. API / 控制能力
4. 告警能力
5. 是否可以进入 Phase 7
```

---

## Prompt 6A：Pre-Trade Risk Rules

```text
你现在负责本项目的 Phase 6A：Pre-Trade Risk Rules。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/phase-6-risk-and-control-plane.md
- v1-ai-execution-phases/phase-6a-pretrade-risk-rules.md
- v1-ai-execution-phases/phase-5-oms-and-paper-execution.md

本次只允许修改：
- src/domain/risk/
- apps/trader/
- tests/unit/
- tests/integration/

本次必须完成：
- 实现最大仓位、最大名义价值、重复下单、行情过期、最小下单量等规则
- 让所有下单动作先经过统一风险闸门

严格不要做：
- 不做复杂自适应风控
- 不做完整控制面
- 不做 in-trade/post-trade 复杂规则

完成后请输出：
1. 已修改文件
2. 已实现的风险规则
3. 风险拒绝原因格式
4. 测试结果
5. 是否可以进入 Phase 6B
```

---

## Prompt 6B：API 与操作控制

```text
你现在负责本项目的 Phase 6B：API 与操作控制。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/phase-6-risk-and-control-plane.md
- v1-ai-execution-phases/phase-6a-pretrade-risk-rules.md
- v1-ai-execution-phases/phase-6b-api-and-operator-controls.md

本次只允许修改：
- apps/api/
- apps/trader/
- 与控制状态衔接相关的少量 risk 代码
- tests/unit/
- tests/integration/

本次必须完成：
- 提供状态查询接口
- 提供策略启停
- 提供 kill switch
- 提供 cancel all
- 让控制动作真正影响 trader 状态

严格不要做：
- 不做完整 dashboard
- 不做复杂 RBAC
- 不做运营后台

完成后请输出：
1. 已修改文件
2. 暴露了哪些 API / 控制能力
3. trader 如何响应这些控制动作
4. 测试结果
5. 是否可以进入 Phase 6C
```

---

## Prompt 6C：告警与安全运维

```text
你现在负责本项目的 Phase 6C：告警与安全运维。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/phase-6-risk-and-control-plane.md
- v1-ai-execution-phases/phase-6a-pretrade-risk-rules.md
- v1-ai-execution-phases/phase-6b-api-and-operator-controls.md
- v1-ai-execution-phases/phase-6c-alerting-and-safety-ops.md

本次只允许修改：
- src/infra/observability/
- apps/api/ 中与告警触发直接相关的少量代码
- apps/trader/
- tests/unit/
- tests/integration/

本次必须完成：
- 建立结构化日志基础
- 接入最小 Telegram 告警或等价通知路径
- 为关键异常定义告警触发点
- 让 kill switch、风险拒绝、保护模式等事件具备可观测性

严格不要做：
- 不做完整监控平台
- 不做 Prometheus / Grafana
- 不做复杂告警编排

完成后请输出：
1. 已修改文件
2. 已接入的告警路径
3. 关键告警触发点
4. 日志/告警验证结果
5. 是否可以认为 Phase 6 已完成
```

---

## Prompt 7：Phase 7 基线策略

```text
你现在负责本项目的 Phase 7：基线策略。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/phase-7-baseline-strategy.md
- v1-ai-execution-phases/phase-6-risk-and-control-plane.md

本次只允许修改：
- src/domain/strategy/
- configs/strategies/ 或等价目录
- 与策略接入直接相关的少量 trader 代码
- tests/unit/
- tests/integration/

本次必须完成：
- 实现至少 1 套简单规则策略，例如均线或动量
- 记录策略输入快照、输出信号和原因摘要
- 跑通端到端 paper 验证

严格不要做：
- 不引入 AI 推理
- 不做多策略调度
- 不做复杂因子库

完成后请输出：
1. 已修改文件
2. 实现了哪种基线策略
3. 策略输入输出说明
4. 验证结果
5. 是否可以进入 Phase 8
```

---

## Prompt 8：Phase 8 最小 Backtest 一致性

```text
你现在负责本项目的 Phase 8：最小 Backtest 一致性。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/phase-8-backtest-minimum.md
- v1-ai-execution-phases/phase-7-baseline-strategy.md

本次只允许修改：
- src/services/backtest/
- apps/research/
- 与回测复用直接相关的少量 strategy 代码
- tests/unit/
- tests/integration/

本次必须完成：
- 建立最小事件驱动回测器
- 复用相同策略接口和订单语义
- 加入手续费和简单滑点
- 输出标准绩效摘要

严格不要做：
- 不建设完整研究平台
- 不做大规模参数搜索
- 不接 AI/ML pipeline

完成后请输出：
1. 已修改文件
2. 回测器复用了哪些语义
3. 当前与 paper 的差异
4. 基础绩效指标
5. 是否可以进入 Phase 9
```

---

## Prompt 9：Phase 9 对账与保护模式

```text
你现在负责本项目的 Phase 9：对账与保护模式。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/phase-9-reconciliation-and-protection.md
- v1-ai-execution-phases/phase-5-oms-and-paper-execution.md
- v1-ai-execution-phases/phase-6-risk-and-control-plane.md

本次只允许修改：
- src/domain/reconciliation/
- apps/trader/
- apps/api/ 中与保护模式直接相关的少量代码
- src/infra/observability/
- scripts/ 或等价任务入口
- tests/unit/
- tests/integration/

本次必须完成：
- 实现启动恢复
- 实现定时对账
- 检查订单、持仓、余额漂移
- 对账异常时进入保护模式
- 记录诊断信息并发送告警

严格不要做：
- 不追求复杂自动修复
- 不实现完整自愈系统
- 不把对账扩展成大而全审计平台

完成后请输出：
1. 已修改文件
2. 当前对账覆盖对象
3. 保护模式触发条件
4. 测试结果
5. V1 是否已满足完成线
```
