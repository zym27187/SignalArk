# Phase 9：对账与保护模式

这份文件用于 AI 单次执行 `Phase 9`。

## 本次目标

在 V1 中补齐最小对账和保护模式，防止系统在异常状态下继续运行。

## 前置依赖

- `Phase 5：OMS 与 Paper Execution`
- `Phase 6：Risk 与最小控制面`

## 必读上下文

- `./00-master-plan.md`
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
- 检查订单、持仓、余额漂移
- 对账异常时进入保护模式
- 记录诊断信息
- 发送异常告警

## 本次不要做

- 不追求复杂自动修复
- 不实现完整自愈系统
- 不把对账扩展成大而全的审计平台

## 完成标准

- 能发现关键状态漂移
- 能阻止系统在异常时继续开新仓
- 能留下足够排查信息

## 最低验证要求

- 至少有测试覆盖启动恢复或定时对账之一
- 至少有测试覆盖异常进入保护模式
- 至少验证一次漂移检测场景

## 本次交付时必须汇报

- 当前对账覆盖了哪些对象
- 进入保护模式的触发条件有哪些
- 哪些修复能力仍然是后续项

## 可直接复制给 AI 的执行提示词

```text
你现在负责本项目的 Phase 9：对账与保护模式。

请先阅读：
- ./00-master-plan.md
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
- 检查订单、持仓、余额漂移
- 对账异常时进入保护模式
- 记录诊断信息并发送告警

严格不要做：
- 不追求复杂自动修复
- 不实现完整自愈系统
- 不把对账扩展成大而全审计平台

完成后请输出：
1. 已修改文件
2. 当前对账覆盖对象
3. 保护模式触发条件
4. 测试结果
5. V1 是否已满足完成线
```
