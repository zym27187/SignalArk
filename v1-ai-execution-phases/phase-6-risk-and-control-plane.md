# Phase 6：Risk 与最小控制面

这份文件用于 AI 单次执行 `Phase 6`。

如果这次改动范围过大，请优先改用下面的子任务文件：

- `./phase-6a-pretrade-risk-rules.md`
- `./phase-6b-api-and-operator-controls.md`
- `./phase-6c-alerting-and-safety-ops.md`

## 本次目标

让 V1 具备基础安全性和人工接管能力，避免系统无闸门地下单。

## 前置依赖

- `Phase 5：OMS 与 Paper Execution`

## 必读上下文

- `./00-master-plan.md`
- `./phase-5-oms-and-paper-execution.md`

## 允许修改范围

- `src/domain/risk/`
- `apps/api/`
- `src/infra/observability/`
- `apps/trader/`
- `tests/unit/`
- `tests/integration/`

## 本次必须完成的任务

- 实现最大仓位检查
- 实现最大名义价值检查
- 实现重复下单防护
- 实现行情过期检查
- 实现最小下单量与基础交易规则检查
- 提供状态查询接口
- 提供策略启停能力
- 提供 `kill switch`
- 提供 `cancel all`
- 接入最小 Telegram 告警

## 本次不要做

- 不做完整 dashboard
- 不做复杂 RBAC
- 不做复杂动态风控模型
- 不做全量监控平台

## 完成标准

- 所有下单动作都先经过统一风险闸门
- 风险拒绝有明确原因
- 人工可以查询状态并接管系统

## 最低验证要求

- 至少有测试覆盖风险放行和风险拒绝
- 至少有测试覆盖 `kill switch` 或策略暂停
- 至少验证一次告警链路或等价通知路径

## 本次交付时必须汇报

- 已实现哪些 pre-trade risk 规则
- API 暴露了哪些最小控制能力
- 当前哪些异常会触发告警

## 可直接复制给 AI 的执行提示词

```text
你现在负责本项目的 Phase 6：Risk 与最小控制面。

请先阅读：
- ./00-master-plan.md
- ./phase-6-risk-and-control-plane.md
- ./phase-5-oms-and-paper-execution.md

本次只允许修改：
- src/domain/risk/
- apps/api/
- src/infra/observability/
- apps/trader/
- tests/unit/
- tests/integration/

本次必须完成：
- 实现最大仓位、最大名义价值、重复下单、行情过期、最小下单量等 pre-trade risk
- 提供状态查询接口
- 提供策略启停、kill switch、cancel all
- 接入最小 Telegram 告警

严格不要做：
- 不做完整 dashboard
- 不做复杂 RBAC
- 不做复杂动态风控
- 不做全量监控平台

完成后请输出：
1. 已修改文件
2. 已实现的风控规则
3. API / 控制能力
4. 告警能力
5. 是否可以进入 Phase 7
```
