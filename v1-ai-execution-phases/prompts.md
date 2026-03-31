# V1 AI 执行提示词汇总

这份文件把 V1 的执行提示词统一整理在一起，方便直接复制给 AI。

使用规则：

1. 每次只使用 `1 个提示词`
2. 当前阶段未完成前，不进入下一个阶段
3. `Phase 2` 默认优先采用 `Prompt 2A -> Prompt 2` 的执行路径；`Phase 5` 默认优先采用 `Prompt 5A -> Prompt 5B -> Prompt 5C` 的执行路径；`Phase 6` 默认优先采用 `Prompt 6A -> Prompt 6B -> Prompt 6C` 的执行路径
4. 所有提示词都必须遵守总纲文件：
   - `v1-ai-execution-phases/00-master-plan.md`
   - `v1-ai-execution-phases/testing-standards.md`
   - `v1-ai-execution-phases/implementation-decisions.md`
5. 从本文件复制提示词时，不要删减其中的“请先阅读”和“完成后请输出”，否则提示词不完整

推荐阅读顺序：

1. `v1-ai-execution-phases/00-master-plan.md`
2. `v1-ai-execution-phases/testing-standards.md`
3. `v1-ai-execution-phases/implementation-decisions.md`
4. `v1-ai-execution-phases/README.md`
5. 复制本文件中的某一个提示词交给 AI

---

## Prompt 0：Phase 0 范围与配置骨架

```text
你现在负责本项目的 Phase 0：范围与配置骨架。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/testing-standards.md
- v1-ai-execution-phases/implementation-decisions.md
- v1-ai-execution-phases/phase-0-scope-and-config.md

交付时必须严格按 `testing-standards.md` 中的测试汇报格式输出，不能只写“已测试”或“测试通过”。

本次只允许修改：
- configs/
- src/config/
- src/shared/ 中与配置直接相关的少量代码
- 根目录的 .env.example 或等价环境变量样例文件
- 范围说明文档
- README.md 中与启动配置直接相关的少量内容

本次必须完成：
- 固定交易所、市场类型、交易对、周期、运行模式
- 明确 V1 只做 paper trading
- 建立基础配置结构和最小日志配置
- 明确关键配置和 secret 的必填/选填契约
- 对关键配置做 fail-fast 校验
- 写清楚最小运行单元共用的配置入口约定
- 把单交易所、单账户、单策略、Bar 驱动边界写清楚
- 写清楚 paper 模式下本地持久化状态是唯一可恢复事实源
- 写清楚 trader_run_id 的生成和日志 / 审计接入约定

严格不要做：
- 不接交易所
- 不建数据库表
- 不实现策略逻辑

完成后请输出：
1. 已修改文件
2. 已完成能力
3. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
4. env / secret 契约说明
5. paper 模式事实源与运行时标识约定
6. 未解决风险
7. 是否可以进入 Phase 1
```

---

## Prompt 1：Phase 1 事件模型与领域对象

```text
你现在负责本项目的 Phase 1：事件模型与领域对象。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/testing-standards.md
- v1-ai-execution-phases/phase-1-domain-model.md
- v1-ai-execution-phases/phase-0-scope-and-config.md

交付时必须严格按 `testing-standards.md` 中的测试汇报格式输出，不能只写“已测试”或“测试通过”。

本次只允许修改：
- src/domain/events/
- src/domain/strategy/
- src/domain/execution/
- src/domain/portfolio/
- src/shared/ 中与基础类型相关的少量代码
- tests/unit/

本次必须完成：
- 定义 BarEvent、Signal、OrderIntent、Order、Fill、Position、BalanceSnapshot
- 统一时间字段和 ID 字段
- 定义订单状态枚举和状态流转规则
- 明确 Signal 不是订单、OrderIntent 先于 Order
- 明确 Signal.target_position 与 OrderIntent.qty 的 sizing contract
- 明确 BarEvent 的时间窗口、唯一键和 closed/final 语义

严格不要做：
- 不接数据库
- 不接交易所
- 不实现真实执行逻辑
- 不引入 Tick / OrderBook

完成后请输出：
1. 已修改文件
2. 已完成能力
3. 新增的核心对象和字段
4. BarEvent 时间窗口 / 唯一键 / finality 语义说明
5. target_position / qty / price 语义说明
6. 订单状态机说明
7. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
8. 未解决风险
9. 是否可以进入 Phase 2
```

---

## Prompt 2：Phase 2 数据库与核心持久化

```text
你现在负责本项目的 Phase 2：数据库与核心持久化。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/testing-standards.md
- v1-ai-execution-phases/implementation-decisions.md
- v1-ai-execution-phases/phase-2-db-and-persistence.md
- v1-ai-execution-phases/phase-1-domain-model.md
- v1-ai-execution-phases/phase-2a-db-schema-and-migration-draft.md

如果你发现当前改动范围超出单次可控交付，请收缩为 Phase 2A，只先完成 schema 与 migration 骨架。

交付时必须严格按 `testing-standards.md` 中的测试汇报格式输出，不能只写“已测试”或“测试通过”。

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
2. 已完成能力
3. 新增表结构
4. 已可持久化对象
5. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
6. 未解决风险
7. 是否可以进入 Phase 3
```

---

## Prompt 2A：Phase 2A 数据库表结构与 Migration 草案

```text
你现在负责本项目的 Phase 2A：数据库表结构与 Migration 草案。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/testing-standards.md
- v1-ai-execution-phases/implementation-decisions.md
- v1-ai-execution-phases/phase-2-db-and-persistence.md
- v1-ai-execution-phases/phase-2a-db-schema-and-migration-draft.md
- v1-ai-execution-phases/phase-1-domain-model.md

交付时必须严格按 `testing-standards.md` 中的测试汇报格式输出，不能只写“已测试”或“测试通过”。

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
- 让 schema 与 Signal -> OrderIntent -> Order -> Fill -> Position / Balance 主链路对齐
- 确保核心交易事实可以关联 trader_run_id，并为 market order 保留 decision_price 或等价字段
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

---

## Prompt 3：Phase 3 Collector 与 Market Gateway

```text
你现在负责本项目的 Phase 3：Collector 与 Market Gateway。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/testing-standards.md
- v1-ai-execution-phases/phase-3-collector-and-market-gateway.md
- v1-ai-execution-phases/phase-1-domain-model.md
- v1-ai-execution-phases/phase-2-db-and-persistence.md

交付时必须严格按 `testing-standards.md` 中的测试汇报格式输出，不能只写“已测试”或“测试通过”。

本次只允许修改：
- apps/collector/
- src/infra/exchanges/
- src/domain/events/ 中与 bar 事件适配有关的少量代码
- src/domain/market/ 或等价目录
- tests/unit/
- tests/integration/

本次必须完成：
- 接入单一交易所的历史和实时 bar 数据
- 统一 symbol、时区、精度
- 建立稳定 bar 唯一键，并对历史补数与实时数据做去重
- 标准化为 BarEvent
- 明确只有 closed / final bar 可以进入可交易链路
- 保留原始 payload 或最小原始记录
- 处理基本断线重连和补数

严格不要做：
- 不实现 Tick
- 不实现 OrderBook
- 不接多交易所
- 不引入复杂消息中间件

完成后请输出：
1. 已修改文件
2. 已完成能力
3. 接入了什么市场数据
4. BarEvent 生成路径
5. bar 唯一键 / closed bar / 去重规则
6. 恢复/补数能力
7. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
8. 未解决风险
9. 是否可以进入 Phase 4
```

---

## Prompt 4：Phase 4 Trader 主循环与 Event Bus

```text
你现在负责本项目的 Phase 4：Trader 主循环与 Event Bus。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/testing-standards.md
- v1-ai-execution-phases/phase-4-trader-loop-and-event-bus.md
- v1-ai-execution-phases/phase-3-collector-and-market-gateway.md

交付时必须严格按 `testing-standards.md` 中的测试汇报格式输出，不能只写“已测试”或“测试通过”。

本次只允许修改：
- apps/trader/
- src/infra/messaging/
- src/domain/events/ 中与订阅分发相关的少量代码
- tests/unit/
- tests/integration/

本次必须完成：
- 建立 trader 主进程或等价入口
- 建立进程内 dispatcher 或 asyncio queue
- 建立事件订阅和处理机制
- 让 BarEvent 可以进入 trader
- 让主循环具备清晰的启动、停止和退出边界
- 为 health / readiness 与单活保护预留运行状态接入点
- 为 strategy / risk / OMS 预留清晰接入点
- 在 trader 启动时生成 trader_run_id，并接入日志上下文、运行状态和关键事件
- 在策略触发边界忽略重复或非 final 的 BarEvent

严格不要做：
- 不引入 Redis Streams
- 不拆远程微服务
- 不实现复杂调度系统

完成后请输出：
1. 已修改文件
2. 已完成能力
3. 主循环启动方式
4. 事件分发机制
5. 生命周期与运行状态接入点
6. trader_run_id 生成与传递方式
7. 重复 / 非 final bar 处理边界
8. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
9. 未解决风险
10. 是否可以进入 Phase 5
```

---

## Prompt 5：Phase 5 OMS 与 Paper Execution

```text
你现在负责本项目的 Phase 5：OMS 与 Paper Execution。

如果当前任务可以明确收敛到 OMS 持久化、执行适配、或组合账本更新中的单一能力域，请优先改用 `Prompt 5A / 5B / 5C`，不要默认直接做整个 Phase 5。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/testing-standards.md
- v1-ai-execution-phases/phase-5-oms-and-paper-execution.md
- v1-ai-execution-phases/phase-1-domain-model.md
- v1-ai-execution-phases/phase-2-db-and-persistence.md
- v1-ai-execution-phases/phase-4-trader-loop-and-event-bus.md

交付时必须严格按 `testing-standards.md` 中的测试汇报格式输出，不能只写“已测试”或“测试通过”。

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
- 固定 Signal.target_position -> OrderIntent.qty 的 sizing 契约
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
2. 已完成能力
3. OMS 事实源设计
4. Signal.target_position 到 OrderIntent.qty 的转换规则
5. paper execution 如何模拟成交
6. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
7. 未解决风险
8. 是否可以进入 Phase 6
```

---

## Prompt 5A：OMS 持久化与状态机

```text
你现在负责本项目的 Phase 5A：OMS 持久化与状态机。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/testing-standards.md
- v1-ai-execution-phases/phase-5-oms-and-paper-execution.md
- v1-ai-execution-phases/phase-5a-oms-persistence-and-state-machine.md

交付时必须严格按 `testing-standards.md` 中的测试汇报格式输出，不能只写“已测试”或“测试通过”。

本次只允许修改：
- src/domain/execution/
- src/infra/db/ 中与 OMS 直接相关的少量代码
- apps/trader/
- tests/unit/
- tests/integration/

本次必须完成：
- 实现 Signal -> OrderIntent
- 固定 Signal.target_position -> OrderIntent.qty 的 sizing 契约
- 实现 OrderIntent 先落库再执行的流程骨架
- 实现 OMS 核心持久化接口
- 明确并落地订单状态机

严格不要做：
- 不实现 paper fill 细节
- 不更新完整持仓和余额
- 不接真实下单

完成后请输出：
1. 已修改文件
2. 已完成能力
3. OMS 事实源设计
4. Signal.target_position 到 OrderIntent.qty 的转换规则
5. 订单状态机说明
6. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
7. 未解决风险
8. 是否可以进入 Phase 5B
```

---

## Prompt 5B：Paper Execution Adapter

```text
你现在负责本项目的 Phase 5B：Paper Execution Adapter。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/testing-standards.md
- v1-ai-execution-phases/phase-5-oms-and-paper-execution.md
- v1-ai-execution-phases/phase-5a-oms-persistence-and-state-machine.md
- v1-ai-execution-phases/phase-5b-paper-execution-adapter.md

交付时必须严格按 `testing-standards.md` 中的测试汇报格式输出，不能只写“已测试”或“测试通过”。

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
2. 已完成能力
3. adapter 如何模拟执行
4. 已覆盖的订单状态
5. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
6. 未解决风险
7. 是否可以进入 Phase 5C
```

---

## Prompt 5C：Portfolio / Balance / PnL 更新

```text
你现在负责本项目的 Phase 5C：Portfolio / Balance / PnL 更新。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/testing-standards.md
- v1-ai-execution-phases/phase-5-oms-and-paper-execution.md
- v1-ai-execution-phases/phase-5a-oms-persistence-and-state-machine.md
- v1-ai-execution-phases/phase-5b-paper-execution-adapter.md
- v1-ai-execution-phases/phase-5c-portfolio-balance-and-pnl.md

交付时必须严格按 `testing-standards.md` 中的测试汇报格式输出，不能只写“已测试”或“测试通过”。

本次只允许修改：
- src/domain/portfolio/
- apps/trader/
- src/domain/execution/ 中与状态更新衔接相关的少量代码
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
2. 已完成能力
3. 持仓/余额/PnL 更新规则
4. 恢复能力说明
5. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
6. 未解决风险
7. 是否可以认为 Phase 5 已完成
```

---

## Prompt 6：Phase 6 Risk 与最小控制面

```text
你现在负责本项目的 Phase 6：Risk 与最小控制面。

如果当前任务可以明确收敛到 pre-trade risk、操作控制、或告警与安全运维中的单一能力域，请优先改用 `Prompt 6A / 6B / 6C`，不要默认直接做整个 Phase 6。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/testing-standards.md
- v1-ai-execution-phases/implementation-decisions.md
- v1-ai-execution-phases/phase-6-risk-and-control-plane.md
- v1-ai-execution-phases/phase-5-oms-and-paper-execution.md

交付时必须严格按 `testing-standards.md` 中的测试汇报格式输出，不能只写“已测试”或“测试通过”。

本次只允许修改：
- src/domain/risk/
- apps/api/
- src/infra/observability/
- src/infra/db/ 中与单活 trader 保护直接相关的少量代码
- apps/trader/
- tests/unit/
- tests/integration/

本次必须完成：
- 实现最大仓位、最大名义价值、重复下单、行情过期、最小下单量等 pre-trade risk
- 提供状态查询接口
- 提供策略启停、kill switch、cancel all
- 提供健康检查与就绪检查
- 限制同一交易账户只允许 1 个 active trader 实例
- 基于 PostgreSQL lease + heartbeat + fencing token 明确单活语义
- 明确 kill switch 的动作边界：禁止新开仓 / 增仓，但允许 cancel all、减仓和平仓
- 接入最小 Telegram 告警

严格不要做：
- 不做完整 dashboard
- 不做复杂 RBAC
- 不做复杂动态风控
- 不做全量监控平台

完成后请输出：
1. 已修改文件
2. 已完成能力
3. 已实现的风控规则
4. API / 控制能力
5. 健康检查 / 单活保护
6. lease TTL / heartbeat / fencing 规则
7. kill switch / cancel all 动作边界
8. 告警能力
9. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
10. 未解决风险
11. 是否可以进入 Phase 7
```

---

## Prompt 6A：Pre-Trade Risk Rules

```text
你现在负责本项目的 Phase 6A：Pre-Trade Risk Rules。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/testing-standards.md
- v1-ai-execution-phases/implementation-decisions.md
- v1-ai-execution-phases/phase-6-risk-and-control-plane.md
- v1-ai-execution-phases/phase-6a-pretrade-risk-rules.md
- v1-ai-execution-phases/phase-5-oms-and-paper-execution.md

交付时必须严格按 `testing-standards.md` 中的测试汇报格式输出，不能只写“已测试”或“测试通过”。

本次只允许修改：
- src/domain/risk/
- apps/trader/
- tests/unit/
- tests/integration/

本次必须完成：
- 实现最大仓位、最大名义价值、重复下单、行情过期、最小下单量等规则
- 在 kill switch 或 protection mode 下，拒绝新开仓 / 增仓，但允许 reduce_only、减仓和平仓单通过统一风险闸门
- 让所有下单动作先经过统一风险闸门

严格不要做：
- 不做复杂自适应风控
- 不做完整控制面
- 不做 in-trade/post-trade 复杂规则

完成后请输出：
1. 已修改文件
2. 已完成能力
3. 已实现的风险规则
4. 风险拒绝原因格式
5. kill switch / protection mode 下的放行与拒绝边界
6. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
7. 未解决风险
8. 是否可以进入 Phase 6B
```

---

## Prompt 6B：API 与操作控制

```text
你现在负责本项目的 Phase 6B：API 与操作控制。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/testing-standards.md
- v1-ai-execution-phases/implementation-decisions.md
- v1-ai-execution-phases/phase-6-risk-and-control-plane.md
- v1-ai-execution-phases/phase-6a-pretrade-risk-rules.md
- v1-ai-execution-phases/phase-6b-api-and-operator-controls.md

交付时必须严格按 `testing-standards.md` 中的测试汇报格式输出，不能只写“已测试”或“测试通过”。

本次只允许修改：
- apps/api/
- apps/trader/
- src/infra/db/ 中与单活 trader 保护直接相关的少量代码
- src/domain/risk/ 中与控制状态衔接相关的少量代码
- tests/unit/
- tests/integration/

本次必须完成：
- 提供状态查询接口
- 提供策略启停
- 提供 kill switch
- 提供 cancel all
- 提供健康检查与就绪检查
- 限制同一交易账户只允许 1 个 active trader 实例
- 基于 PostgreSQL lease 明确 owner_instance_id / lease_expires_at / last_heartbeat_at / fencing_token
- lease 丢失或过期时，让实例降级为 not ready 并停止提交新订单
- 让 kill switch 激活后进入 reduce-only 状态：拒绝新开仓 / 增仓，但允许 cancel all、减仓和平仓
- 让控制动作真正影响 trader 状态

严格不要做：
- 不做完整 dashboard
- 不做复杂 RBAC
- 不做运营后台

完成后请输出：
1. 已修改文件
2. 已完成能力
3. 暴露了哪些 API / 控制能力
4. 健康检查 / 就绪检查定义
5. 单活 trader 保护机制
6. lease TTL / heartbeat / fencing 规则
7. kill switch / cancel all 动作边界
8. trader 如何响应这些控制动作
9. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
10. 未解决风险
11. 是否可以进入 Phase 6C
```

---

## Prompt 6C：告警与安全运维

```text
你现在负责本项目的 Phase 6C：告警与安全运维。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/testing-standards.md
- v1-ai-execution-phases/phase-6-risk-and-control-plane.md
- v1-ai-execution-phases/phase-6a-pretrade-risk-rules.md
- v1-ai-execution-phases/phase-6b-api-and-operator-controls.md
- v1-ai-execution-phases/phase-6c-alerting-and-safety-ops.md

交付时必须严格按 `testing-standards.md` 中的测试汇报格式输出，不能只写“已测试”或“测试通过”。

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
2. 已完成能力
3. 已接入的告警路径
4. 关键告警触发点
5. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
6. 日志/告警验证结果
7. 未解决风险
8. 是否可以认为 Phase 6 已完成
```

---

## Prompt 7：Phase 7 基线策略

```text
你现在负责本项目的 Phase 7：基线策略。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/testing-standards.md
- v1-ai-execution-phases/phase-7-baseline-strategy.md
- v1-ai-execution-phases/phase-6-risk-and-control-plane.md

交付时必须严格按 `testing-standards.md` 中的测试汇报格式输出，不能只写“已测试”或“测试通过”。

本次只允许修改：
- src/domain/strategy/
- configs/strategies/ 或等价目录
- apps/trader/ 中与策略接入直接相关的少量代码
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
2. 已完成能力
3. 实现了哪种基线策略
4. 策略输入输出说明
5. 这套策略如何验证了交易内核
6. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
7. 未解决风险
8. 是否可以进入 Phase 8
```

---

## Prompt 8：Phase 8 最小 Backtest 一致性

```text
你现在负责本项目的 Phase 8：最小 Backtest 一致性。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/testing-standards.md
- v1-ai-execution-phases/phase-8-backtest-minimum.md
- v1-ai-execution-phases/phase-7-baseline-strategy.md

交付时必须严格按 `testing-standards.md` 中的测试汇报格式输出，不能只写“已测试”或“测试通过”。

本次只允许修改：
- src/services/backtest/
- apps/research/
- src/domain/strategy/ 中与回测复用直接相关的少量代码
- tests/unit/
- tests/integration/

本次必须完成：
- 建立最小事件驱动回测器
- 复用相同策略接口和订单语义
- 加入手续费和简单滑点
- 输出 run manifest 或等价元数据，记录策略、参数、数据和成本假设
- 输出标准绩效摘要

严格不要做：
- 不建设完整研究平台
- 不做大规模参数搜索
- 不接 AI/ML pipeline

完成后请输出：
1. 已修改文件
2. 已完成能力
3. 回测器复用了哪些语义
4. 当前与 paper 的差异
5. 可复现元数据 / run manifest
6. 基础绩效指标
7. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
8. 未解决风险
9. 是否可以进入 Phase 9
```

---

## Prompt 9：Phase 9 对账与保护模式

```text
你现在负责本项目的 Phase 9：对账与保护模式。

请先阅读：
- v1-ai-execution-phases/00-master-plan.md
- v1-ai-execution-phases/testing-standards.md
- v1-ai-execution-phases/phase-9-reconciliation-and-protection.md
- v1-ai-execution-phases/phase-5-oms-and-paper-execution.md
- v1-ai-execution-phases/phase-6-risk-and-control-plane.md

交付时必须严格按 `testing-standards.md` 中的测试汇报格式输出，不能只写“已测试”或“测试通过”。

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
- 在 paper 模式下，以本地持久化 orders / fills / positions / balance_snapshots 为对账真相源
- 检查订单、持仓、余额漂移
- 对账异常时进入保护模式
- 进入保护模式后取消所有非 reduce_only 挂单，并保留减仓和平仓路径
- 记录诊断信息并发送告警
- 提供最小事件回放或诊断入口，例如 replay_events 或等价工具，至少支持 time range / trader_run_id / account_id / symbol

严格不要做：
- 不追求复杂自动修复
- 不实现完整自愈系统
- 不把对账扩展成大而全审计平台

完成后请输出：
1. 已修改文件
2. 已完成能力
3. 当前对账覆盖对象
4. paper 模式下的对账真相源
5. 保护模式触发条件
6. 保护模式下挂单处理与允许动作
7. 最小回放 / 诊断入口
8. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
9. 未解决风险
10. V1 是否已满足完成线
```
