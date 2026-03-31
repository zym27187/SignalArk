# Phase 5C：Portfolio / Balance / PnL 更新

这份文件用于把 `Phase 5` 进一步拆成更适合 AI 单次编码的子任务。

## 本次目标

把 `Fill / OrderUpdate` 转成稳定的持仓、余额和基础 PnL 更新逻辑。

## 前置依赖

- `Phase 5A：OMS 持久化与状态机`
- `Phase 5B：Paper Execution Adapter`

## 必读上下文

- `./00-master-plan.md`
- `./phase-5-oms-and-paper-execution.md`
- `./phase-5a-oms-persistence-and-state-machine.md`
- `./phase-5b-paper-execution-adapter.md`

## 允许修改范围

- `src/domain/portfolio/`
- `apps/trader/`
- `src/domain/execution/` 中与状态更新衔接相关的少量代码
- `tests/unit/`
- `tests/integration/`

## 本次必须完成的任务

- 处理 `Fill` 对 `Position` 的影响
- 处理余额变动
- 生成基础 `PnL` 更新
- 支持重启后的关键状态恢复
- 让状态更新具备可追踪性

## 本次不要做

- 不做复杂绩效分析
- 不做多账户汇总
- 不引入高级风险归因

## 完成标准

- 持仓、余额和基础 PnL 能随 paper fill 正确变化
- 重启后关键状态可以恢复
- 交易闭环中的核心状态已经连起来

## 最低验证要求

- 至少有测试覆盖成交后的持仓变化
- 至少有测试覆盖余额或基础 PnL 更新

## 可直接复制给 AI 的执行提示词

```text
你现在负责本项目的 Phase 5C：Portfolio / Balance / PnL 更新。

请先阅读：
- ./00-master-plan.md
- ./phase-5-oms-and-paper-execution.md
- ./phase-5a-oms-persistence-and-state-machine.md
- ./phase-5b-paper-execution-adapter.md
- ./phase-5c-portfolio-balance-and-pnl.md

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
