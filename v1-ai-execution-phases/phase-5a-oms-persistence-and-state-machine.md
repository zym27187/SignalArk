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

## 最低验证要求

- 至少有测试覆盖 `Signal -> OrderIntent -> Order`
- 至少有测试覆盖订单状态迁移

## 可直接复制给 AI 的执行提示词

```text
你现在负责本项目的 Phase 5A：OMS 持久化与状态机。

请先阅读：
- ./00-master-plan.md
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
