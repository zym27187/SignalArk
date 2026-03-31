# Phase 9：对账与保护模式

这份文件用于 AI 单次执行 `Phase 9`。

## 本次目标

在 V1 中补齐最小对账和保护模式，防止系统在异常状态下继续运行。

## 前置依赖

- `Phase 5：OMS 与 Paper Execution`
- `Phase 6：Risk 与最小控制面`

## 必读上下文

- `./00-master-plan.md`
- `./testing-standards.md`
- `./phase-5-oms-and-paper-execution.md`
- `./phase-6-risk-and-control-plane.md`

## 允许修改范围

- `src/domain/reconciliation/`
- `apps/trader/`
- `apps/api/` 中与保护模式直接相关的少量代码
- `src/infra/observability/`
- `scripts/` 或等价任务入口
- `tests/unit/`
- `tests/integration/`

## 本次必须完成的任务

- 实现启动恢复
- 实现定时对账
- 在 `paper` 模式下，以本地持久化 `orders / fills / positions / balance_snapshots` 为对账真相源
- 检查订单、持仓、余额漂移，以及 `sellable_qty / fee / tax` 等派生状态漂移
- 对账异常时进入保护模式
- 进入保护模式后取消所有非减仓 / 平仓保护挂单，并保留减仓和平仓路径；如果实现里保留 `reduce_only` 字段，则等价于取消所有 `reduce_only = false` 的挂单
- 记录诊断信息
- 发送异常告警
- 提供最小事件回放或诊断入口，例如 `replay_events` 或等价工具，至少支持 `time range / trader_run_id / account_id / symbol`

## 本次不要做

- 不追求复杂自动修复
- 不实现完整自愈系统
- 不把对账扩展成大而全的审计平台

## 完成标准

- 能发现关键状态漂移
- 能阻止系统在异常时继续开新仓
- 能留下足够排查信息
- 关键异常可以结合审计记录进行最小回放或复盘
- `paper` 模式下的对账对象、真相源和派生状态边界是明确的
- `sellable_qty`、成交成本和现金变动不会因为日切或账本更新而长期漂移
- 保护模式的动作边界清晰：禁新开 / 增仓，允减仓 / 平仓，并处理所有非减仓 / 平仓保护挂单

## 最低验证要求

- 至少有测试覆盖启动恢复或定时对账之一
- 至少有测试覆盖异常进入保护模式
- 至少验证一次漂移检测场景
- 至少验证一次最小回放或诊断入口可以读取关键事件
- 至少验证一次保护模式下开仓被阻止但减仓或平仓仍可执行

## 本次交付时必须汇报

- 当前对账覆盖了哪些对象
- `paper` 模式下当前采用什么真相源
- 进入保护模式的触发条件有哪些
- 进入保护模式后哪些挂单会被取消，哪些动作仍被允许
- `sellable_qty / fee / tax` 派生状态是如何校验的
- 当前最小回放入口支持哪些筛选维度
- 哪些修复能力仍然是后续项

## 可直接复制给 AI 的执行提示词

```text
你现在负责本项目的 Phase 9：对账与保护模式。

请先阅读：
- ./00-master-plan.md
- ./testing-standards.md
- ./phase-9-reconciliation-and-protection.md
- ./phase-5-oms-and-paper-execution.md
- ./phase-6-risk-and-control-plane.md

本次只允许修改：
- src/domain/reconciliation/
- apps/trader/
- apps/api/ 中与保护模式直接相关的少量代码
- src/infra/observability/
- scripts/ 或等价任务入口
- tests/unit/
- tests/integration/

本次必须完成：
- 实现启动恢复
- 实现定时对账
- 在 paper 模式下，以本地持久化 orders / fills / positions / balance_snapshots 为对账真相源
- 检查订单、持仓、余额，以及 sellable_qty / fee / tax 派生状态漂移
- 对账异常时进入保护模式
- 进入保护模式后取消所有非减仓 / 平仓保护挂单，并保留减仓和平仓路径；如果实现里保留 `reduce_only` 字段，则等价为取消所有 `reduce_only = false` 的挂单
- 记录诊断信息并发送告警
- 提供最小事件回放或诊断入口，例如 replay_events 或等价工具，至少支持 time range / trader_run_id / account_id / symbol

严格不要做：
- 不追求复杂自动修复
- 不实现完整自愈系统
- 不把对账扩展成大而全审计平台

完成后请输出：
1. 已修改文件
2. 已完成能力
3. 当前对账覆盖对象
4. paper 模式下的对账真相源
5. 保护模式触发条件
6. 保护模式下挂单处理与允许动作
7. sellable_qty / fee / tax 派生状态校验
8. 最小回放 / 诊断入口
9. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
10. 未解决风险
11. V1 是否已满足完成线
```
