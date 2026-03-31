# Phase 6B：API 与操作控制

这份文件用于把 `Phase 6` 进一步拆成更适合 AI 单次编码的子任务。

## 本次目标

提供最小控制面，让操作者可以查询状态、启停策略并执行保命动作。

## 前置依赖

- `Phase 5：OMS 与 Paper Execution`
- `Phase 6A：Pre-Trade Risk Rules`

## 必读上下文

- `./00-master-plan.md`
- `./testing-standards.md`
- `./phase-6-risk-and-control-plane.md`
- `./phase-6a-pretrade-risk-rules.md`

## 允许修改范围

- `apps/api/`
- `apps/trader/`
- `src/domain/risk/` 中与控制状态衔接相关的少量代码
- `tests/unit/`
- `tests/integration/`

## 本次必须完成的任务

- 提供状态查询接口
- 提供策略启停能力
- 提供 `kill switch`
- 提供 `cancel all`
- 让这些控制动作能影响 trader 运行状态

## 本次不要做

- 不做完整 dashboard
- 不做复杂 RBAC
- 不做运营后台

## 完成标准

- 操作者可以查询系统关键状态
- 操作者可以主动阻止系统继续开新仓
- 控制动作与 trader 状态有明确连接

## 最低验证要求

- 至少有测试覆盖状态查询
- 至少有测试覆盖 `kill switch` 或策略暂停

## 可直接复制给 AI 的执行提示词

```text
你现在负责本项目的 Phase 6B：API 与操作控制。

请先阅读：
- ./00-master-plan.md
- ./phase-6-risk-and-control-plane.md
- ./phase-6a-pretrade-risk-rules.md
- ./phase-6b-api-and-operator-controls.md

本次只允许修改：
- apps/api/
- apps/trader/
- 与控制状态衔接相关的少量 risk 代码
- tests/unit/
- tests/integration/

本次必须完成：
- 提供状态查询接口
- 提供策略启停
- 提供 kill switch
- 提供 cancel all
- 让控制动作真正影响 trader 状态

严格不要做：
- 不做完整 dashboard
- 不做复杂 RBAC
- 不做运营后台

完成后请输出：
1. 已修改文件
2. 暴露了哪些 API / 控制能力
3. trader 如何响应这些控制动作
4. 测试结果
5. 是否可以进入 Phase 6C
```
