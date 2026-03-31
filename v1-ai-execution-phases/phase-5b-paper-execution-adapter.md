# Phase 5B：Paper Execution Adapter

这份文件用于把 `Phase 5` 进一步拆成更适合 AI 单次编码的子任务。

## 本次目标

实现 `paper execution adapter`，让 OMS 产生的订单可以被模拟执行并返回标准订单事件。

## 前置依赖

- `Phase 5A：OMS 持久化与状态机`

## 必读上下文

- `./00-master-plan.md`
- `./testing-standards.md`
- `./phase-5-oms-and-paper-execution.md`
- `./phase-5a-oms-persistence-and-state-machine.md`

## 允许修改范围

- `src/infra/exchanges/` 中的 `paper adapter`
- `src/domain/execution/` 中与执行适配相关的少量代码
- `apps/trader/`
- `tests/unit/`
- `tests/integration/`

## 本次必须完成的任务

- 实现 `paper execution adapter`
- 支持模拟 `ACK / PARTIAL / FILL / REJECT / CANCEL`
- 输出标准订单更新和成交事件
- 与 OMS 持久化流程正确衔接

## 本次不要做

- 不接真实交易所
- 不做复杂滑点与撮合算法
- 不更新完整投资组合账本逻辑

## 完成标准

- paper adapter 可以驱动订单生命周期
- OMS 能接收到标准订单更新与成交事件
- 核心拒单和撤单场景可覆盖

## 最低验证要求

- 至少有测试覆盖 ACK/FILL
- 至少有测试覆盖 REJECT 或 CANCEL

## 可直接复制给 AI 的执行提示词

```text
你现在负责本项目的 Phase 5B：Paper Execution Adapter。

请先阅读：
- ./00-master-plan.md
- ./phase-5-oms-and-paper-execution.md
- ./phase-5a-oms-persistence-and-state-machine.md
- ./phase-5b-paper-execution-adapter.md

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
