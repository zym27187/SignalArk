# Phase 4：research 标准化与对照能力

这份文件用于把 research 从“最小可跑”推进到“可复现、可比较、可解释”。

## 本次目标

统一 research 的运行模式、manifest、样本说明和策略对照输出，让 baseline、候选策略和未来 AI 策略都能在同一语义下比较。

## 前置依赖

- [Phase 0：边界、术语与共享契约](./phase-0-boundaries-and-shared-contracts.md)
- [Phase 3：诊断统一与降级模式表达](./phase-3-diagnostics-and-degraded-mode.md)

## 必读上下文

- [00-scope-draft.md](./00-scope-draft.md)
- [00-master-plan.md](./00-master-plan.md)
- [phase-0-boundaries-and-shared-contracts.md](./phase-0-boundaries-and-shared-contracts.md)
- [phase-3-diagnostics-and-degraded-mode.md](./phase-3-diagnostics-and-degraded-mode.md)
- [README.md](../README.md)
- [apps/research/README.md](../apps/research/README.md)
- [v1-ai-execution-phases/testing-standards.md](../v1-ai-execution-phases/testing-standards.md)

## 允许修改范围

- `apps/research/`
- `apps/api/`
- `apps/web/`
- `src/services/backtest/`
- `src/domain/strategy/`
- `tests/unit/`
- `tests/integration/`

## 本次必须完成的任务

- 标准化 research 运行模式，至少覆盖：
  - `preview`
  - `evaluation`
  - `parameter_scan`
  - `walk_forward`
- 统一 research manifest 的最小字段集合。
- 明确样本用途、时间窗、bar 数量、成本模型和参数来源。
- 让不同策略能在相同样本和相同指标语义下比较。
- 让前端或 API 能直接看见研究结果的关键摘要，而不是只能读原始产物。
- 让用户能够理解某个股票代码当前是否：
  - 可用于 research
  - 已被系统支持
  - 已进入 runtime

## 本次不要做

- 不做完整实验平台
- 不做对象存储平台化
- 不做超大规模参数搜索系统
- 不引入复杂训练编排基础设施

## 默认实现细节

### 1. manifest 建议字段

建议至少包含：

- `strategy_id`
- `strategy_version`
- `mode`
- `symbol`
- `timeframe`
- `bar_count`
- `sample_purpose`
- `cost_model`
- `parameter_snapshot`
- `generated_at`

### 2. 对照结果建议

同一份输出中建议至少能对比：

- 收益
- 回撤
- 交易次数
- 换手或等价活跃度
- 关键决策差异摘要

### 3. 前端表现建议

Research 相关视图默认应先回答：

- 这是预览还是评估
- 样本是否足够长
- 当前结果和 baseline 相比如何

## 完成标准

- research 结果具备稳定 manifest
- preview / evaluation / scan / walk-forward 有清晰边界
- baseline 与候选策略能在统一语义下比较
- research 输出对非开发者也更容易理解

## 最低验证要求

- 至少验证一种新增 research 模式
- 至少验证 manifest 或参数快照字段
- 至少验证一次 baseline 与候选策略对照
- 如前端接入 research 摘要，至少覆盖对应前端测试

## 本次交付时必须汇报

- 标准化了哪些 research 模式
- manifest 包含哪些核心字段
- 策略对照是如何定义的
- 当前 research 与 runtime 仍有哪些差异
- 是否可以进入 Phase 5
