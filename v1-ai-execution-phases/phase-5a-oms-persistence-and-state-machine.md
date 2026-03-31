# Phase 5A：OMS 持久化与状态机

这份文件用于把 `Phase 5` 进一步拆成更适合 AI 单次编码的子任务。

## 本次目标

先把 OMS 的本地事实源、订单状态机和 `OrderIntent -> Order` 持久化流程做稳。

## 前置依赖

- `Phase 1：事件模型与领域对象`
- `Phase 2：数据库与核心持久化`
- `Phase 4：Trader 主循环与 Event Bus`

## 必读上下文

- `./00-master-plan.md`
- `./testing-standards.md`
- `./phase-5-oms-and-paper-execution.md`
- `./phase-1-domain-model.md`
- `./phase-2-db-and-persistence.md`

## 允许修改范围

- `src/domain/execution/`
- `src/infra/db/` 中与 OMS 直接相关的少量代码
- `apps/trader/`
- `tests/unit/`
- `tests/integration/`

## 本次必须完成的任务

- 实现 `Signal -> OrderIntent`
- 固定 `Signal.target_position -> OrderIntent.qty` 的 sizing 契约
- 实现 `OrderIntent` 先落库再执行的流程骨架
- 实现 OMS 核心持久化接口
- 明确订单状态迁移
- 为后续执行适配器预留清晰接入点

## 本次不要做

- 不实现 paper fill 细节
- 不更新完整持仓和余额
- 不接真实 live 下单

## 完成标准

- `OrderIntent` 和 `Order` 的持久化链路成立
- 订单状态机可执行且可测试
- OMS 已成为本地事实源的一部分
- `Signal`、当前持仓、`decision_price` 和 `OrderIntent.qty` 的转换规则已固定且可复现

## 最低验证要求

- 至少有测试覆盖 `Signal -> OrderIntent -> Order`
- 至少有测试覆盖订单状态迁移

## 本次交付时必须汇报

- OMS 事实源落在哪些表或对象上
- 订单状态机已经覆盖了哪些迁移
- `Signal.target_position` 如何变成 `OrderIntent.qty`
- 当前哪些执行和账本能力刻意留到 `Phase 5B / 5C`

## 可直接复制给 AI 的执行提示词

```text
你现在负责本项目的 Phase 5A：OMS 持久化与状态机。

请先阅读：
- ./00-master-plan.md
- ./testing-standards.md
- ./phase-5-oms-and-paper-execution.md
- ./phase-5a-oms-persistence-and-state-machine.md

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
