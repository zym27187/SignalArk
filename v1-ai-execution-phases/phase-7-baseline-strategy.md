# Phase 7：基线策略

这份文件用于 AI 单次执行 `Phase 7`。

## 本次目标

用一套简单可解释的规则策略验证交易内核，而不是追求复杂收益。

## 前置依赖

- `Phase 6：Risk 与最小控制面`

## 必读上下文

- `./00-master-plan.md`
- `./testing-standards.md`
- `./phase-6-risk-and-control-plane.md`

## 允许修改范围

- `src/domain/strategy/`
- `configs/strategies/` 或等价目录
- `apps/trader/` 中与策略接入直接相关的少量代码
- `tests/unit/`
- `tests/integration/`

## 本次必须完成的任务

- 实现至少 1 套简单规则策略，例如均线或动量
- 记录策略输入快照
- 记录策略输出信号
- 记录简要原因摘要
- 跑通端到端 paper 验证

## 本次不要做

- 不引入 AI 推理
- 不做多策略调度
- 不做复杂因子库
- 不为策略框架加入过度抽象

## 完成标准

- 至少 1 套基线策略能在 paper 模式稳定运行
- 信号、订单、成交记录可审计
- 能看出策略是否真的驱动了交易闭环

## 最低验证要求

- 至少有单元测试覆盖策略信号生成
- 至少有 1 条端到端验证路径覆盖策略到订单

## 本次交付时必须汇报

- 实现了哪种基线策略
- 策略输入输出是什么
- 这套策略如何验证了交易内核

## 可直接复制给 AI 的执行提示词

```text
你现在负责本项目的 Phase 7：基线策略。

请先阅读：
- ./00-master-plan.md
- ./testing-standards.md
- ./phase-7-baseline-strategy.md
- ./phase-6-risk-and-control-plane.md

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
