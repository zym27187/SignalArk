# Phase 2：控制面与账户资金可见性

这份文件用于把控制面从“能看基本状态”推进到“能解释账户和控制动作”。

## 本次目标

补齐账户资金可见性、控制动作结果反馈和股票代码管理的最小控制面闭环。

## 前置依赖

- [Phase 0：边界、术语与共享契约](./phase-0-boundaries-and-shared-contracts.md)
- [Phase 1：前端易用性与股票代码管理](./phase-1-frontend-usability-and-symbol-management.md)

## 必读上下文

- [00-scope-draft.md](./00-scope-draft.md)
- [00-master-plan.md](./00-master-plan.md)
- [phase-0-boundaries-and-shared-contracts.md](./phase-0-boundaries-and-shared-contracts.md)
- [phase-1-frontend-usability-and-symbol-management.md](./phase-1-frontend-usability-and-symbol-management.md)
- [README.md](../README.md)
- [v1-ai-execution-phases/testing-standards.md](../v1-ai-execution-phases/testing-standards.md)

## 允许修改范围

- `apps/api/`
- `apps/trader/` 中与只读状态或控制动作衔接相关的少量代码
- `apps/web/`
- `src/infra/db/`
- `tests/unit/`
- `tests/integration/`

## 本次必须完成的任务

- 提供账户资金相关只读视图，至少包括：
  - 最新余额
  - 可用资金
  - 冻结资金
  - 关键快照时间
- 让控制台能解释 `现金变化 / 持仓变化 / 权益变化` 的关系。
- 强化控制动作结果回显，尤其是：
  - `kill switch`
  - `cancel all`
  - 策略暂停与恢复
- 为股票代码管理提供最小控制面闭环，至少包括：
  - 代码格式与市场校验
  - 是否属于 `supported_symbols`
  - 是否已进入当前 runtime
  - 修改 runtime 范围时的确认与结果反馈
- 明确股票代码变更的生效方式：
  - 立即只读生效
  - 延迟生效
  - 需要重启或重载

## 本次不要做

- 不做复杂权限系统
- 不做实时推送式控制台
- 不做完整账户分析后台
- 不在本阶段扩展到真实券商账户

## 默认实现细节

### 1. 资金视图建议

建议最小返回结构至少包含：

- `cash_balance`
- `available_cash`
- `frozen_cash`
- `equity`
- `as_of_time`
- `summary_message`

### 2. 股票代码管理建议

默认建议把动作分成：

- 添加到观察范围
- 标记为 supported
- 申请进入 runtime

其中最后一项必须显式展示影响范围。

### 3. 控制动作结果建议

每个关键动作默认至少返回：

- `accepted`
- `effective_scope`
- `control_state`
- `message`
- `effective_at`

## 完成标准

- 操作者能直接理解账户资金和权益状态
- 控制动作结果更完整可解释
- 股票代码的控制面闭环基本成立
- 影响运行时标的的动作具有明确反馈

## 最低验证要求

- 至少验证一次资金视图的只读查询
- 至少验证一次控制动作结果回显
- 至少验证一次股票代码管理相关的校验或状态变更
- 如涉及 DB 或 API，至少运行相关集成测试

## 本次交付时必须汇报

- 新增了哪些资金可见性字段或接口
- 控制动作结果补强了哪些信息
- 股票代码管理如何区分观察、supported 和 runtime
- runtime 范围变更如何生效
- 当前仍有哪些控制面缺口
- 是否可以进入 Phase 3
