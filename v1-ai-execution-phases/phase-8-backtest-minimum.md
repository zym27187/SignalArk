# Phase 8：最小 Backtest 一致性

这份文件用于 AI 单次执行 `Phase 8`。

## 本次目标

让同一套策略接口可以运行在最小回测环境中，验证回测和 paper 使用同一套交易语义。

## 前置依赖

- `Phase 7：基线策略`

## 必读上下文

- `./00-master-plan.md`
- `./testing-standards.md`
- `./phase-7-baseline-strategy.md`

## 允许修改范围

- `src/services/backtest/`
- `apps/research/`
- `src/domain/strategy/` 中与回测复用直接相关的少量代码
- `tests/unit/`
- `tests/integration/`

## 本次必须完成的任务

- 建立最小事件驱动回测器
- 复用相同策略接口
- 复用相同订单语义
- 加入手续费和简单滑点
- 输出标准绩效摘要

## 本次不要做

- 不建设完整研究平台
- 不做大规模参数搜索
- 不接 AI/ML pipeline
- 不为了报表美观引入大量非核心依赖

## 完成标准

- 同一策略可运行在 backtest 和 paper
- 回测结果可复现
- 至少能输出收益、回撤、交易次数等基础指标

## 最低验证要求

- 至少有测试覆盖回测事件驱动流程
- 至少验证一次策略在 backtest 和 paper 的接口一致性

## 本次交付时必须汇报

- 回测器复用了哪些交易语义
- 当前回测和 paper 还存在哪些差异
- 产出了哪些基础绩效指标

## 可直接复制给 AI 的执行提示词

```text
你现在负责本项目的 Phase 8：最小 Backtest 一致性。

请先阅读：
- ./00-master-plan.md
- ./phase-8-backtest-minimum.md
- ./phase-7-baseline-strategy.md

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
