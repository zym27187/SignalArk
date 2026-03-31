# Phase 5：OMS 与 Paper Execution

这份文件用于定义 `Phase 5` 的总目标、边界和总体验收口径。

默认推荐按下面顺序执行子任务；只有当前改动已经非常小、明确只需补一处闭环缺口时，才直接使用本文件：

- `./phase-5a-oms-persistence-and-state-machine.md`
- `./phase-5b-paper-execution-adapter.md`
- `./phase-5c-portfolio-balance-and-pnl.md`

完成 `5A -> 5B -> 5C` 后，可以回到本文件做总体验收或小范围补缝。

## 本次目标

跑通 V1 最核心的交易闭环，让系统从 `Signal` 走到 `paper fill`，并更新本地状态。

## 前置依赖

- `Phase 1：事件模型与领域对象`
- `Phase 2：数据库与核心持久化`
- `Phase 4：Trader 主循环与 Event Bus`

## 必读上下文

- `./00-master-plan.md`
- `./testing-standards.md`
- `./phase-1-domain-model.md`
- `./phase-2-db-and-persistence.md`
- `./phase-4-trader-loop-and-event-bus.md`

## 允许修改范围

- `src/domain/execution/`
- `src/domain/portfolio/`
- `src/infra/exchanges/` 中的 `paper adapter`
- `apps/trader/`
- `tests/unit/`
- `tests/integration/`
- `tests/e2e/`

## 本次必须完成的任务

- 实现 `Signal -> OrderIntent`
- 实现 `OrderIntent` 先落库再执行
- 实现 OMS 持久化流程
- 实现 `paper execution adapter`
- 支持模拟 `ACK / PARTIAL / FILL / REJECT / CANCEL`
- 更新 `Position / Balance / PnL`
- 让状态变化可追踪

## 本次不要做

- 不接真实 live 下单
- 不做复杂执行算法
- 不做多账户资金分配
- 不提前做 sandbox/live 统一平台化

## 完成标准

- 完整 paper 闭环可以跑通
- 订单、成交、持仓、余额变化都可落库
- 重启后可以恢复关键状态

## 最低验证要求

- 至少有集成测试覆盖 `Signal -> OrderIntent -> Order -> Fill`
- 至少有测试覆盖拒单或撤单场景
- 至少有测试覆盖持仓或余额更新

## 本次交付时必须汇报

- OMS 事实源落在哪些表或对象上
- `paper execution` 如何模拟成交
- 当前已覆盖哪些订单状态变化

## 可直接复制给 AI 的执行提示词

```text
你现在负责本项目的 Phase 5：OMS 与 Paper Execution。

如果当前任务可以明确收敛到 OMS 持久化、执行适配、或组合账本更新中的单一能力域，请优先改用 `Phase 5A / 5B / 5C`，不要默认直接做整个 Phase 5。

请先阅读：
- ./00-master-plan.md
- ./testing-standards.md
- ./phase-5-oms-and-paper-execution.md
- ./phase-1-domain-model.md
- ./phase-2-db-and-persistence.md
- ./phase-4-trader-loop-and-event-bus.md

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
2. 已完成能力
3. OMS 事实源设计
4. paper execution 如何模拟成交
5. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
6. 未解决风险
7. 是否可以进入 Phase 6
```
