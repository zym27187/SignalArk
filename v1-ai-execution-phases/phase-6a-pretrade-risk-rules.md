# Phase 6A：Pre-Trade Risk Rules

这份文件用于把 `Phase 6` 进一步拆成更适合 AI 单次编码的子任务。

## 本次目标

先把最基础、最关键的 `pre-trade risk` 规则做出来，并接入统一下单闸门。

## 前置依赖

- `Phase 5：OMS 与 Paper Execution`

## 必读上下文

- `./00-master-plan.md`
- `./phase-6-risk-and-control-plane.md`
- `./phase-5-oms-and-paper-execution.md`

## 允许修改范围

- `src/domain/risk/`
- `apps/trader/`
- `tests/unit/`
- `tests/integration/`

## 本次必须完成的任务

- 实现最大仓位检查
- 实现最大名义价值检查
- 实现重复下单防护
- 实现行情过期检查
- 实现最小下单量和基础交易规则检查
- 让所有下单动作先经过统一风险闸门

## 本次不要做

- 不做 in-trade / post-trade 复杂风控
- 不做复杂自适应风控
- 不做完整控制面

## 完成标准

- 风险规则能明确放行或拒绝
- 拒绝原因可解释
- trader 下单前已经过统一风控入口

## 最低验证要求

- 至少有测试覆盖放行与拒绝
- 至少有测试覆盖重复单或过期行情

## 可直接复制给 AI 的执行提示词

```text
你现在负责本项目的 Phase 6A：Pre-Trade Risk Rules。

请先阅读：
- ./00-master-plan.md
- ./phase-6-risk-and-control-plane.md
- ./phase-6a-pretrade-risk-rules.md
- ./phase-5-oms-and-paper-execution.md

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
