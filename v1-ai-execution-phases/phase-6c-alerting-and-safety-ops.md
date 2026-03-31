# Phase 6C：告警与安全运维

这份文件用于把 `Phase 6` 进一步拆成更适合 AI 单次编码的子任务。

## 本次目标

补齐最小可观测与告警能力，让关键异常能被发现并触发人工介入。

## 前置依赖

- `Phase 6A：Pre-Trade Risk Rules`
- `Phase 6B：API 与操作控制`

## 必读上下文

- `./00-master-plan.md`
- `./phase-6-risk-and-control-plane.md`
- `./phase-6a-pretrade-risk-rules.md`
- `./phase-6b-api-and-operator-controls.md`

## 允许修改范围

- `src/infra/observability/`
- `apps/api/` 中与告警触发直接相关的少量代码
- `apps/trader/`
- `tests/unit/`
- `tests/integration/`

## 本次必须完成的任务

- 建立结构化日志基础
- 接入最小 Telegram 告警或等价通知路径
- 为关键异常定义告警触发点
- 让 `kill switch`、风险拒绝、保护模式等事件具备可观测性

## 本次不要做

- 不做完整监控平台
- 不做 Prometheus / Grafana
- 不做复杂告警编排系统

## 完成标准

- 关键异常可被结构化记录
- 至少有一条稳定告警路径
- 操作者能从日志和告警中快速判断系统状态

## 最低验证要求

- 至少验证一次告警链路或等价通知路径
- 至少验证一次关键异常日志输出

## 可直接复制给 AI 的执行提示词

```text
你现在负责本项目的 Phase 6C：告警与安全运维。

请先阅读：
- ./00-master-plan.md
- ./phase-6-risk-and-control-plane.md
- ./phase-6a-pretrade-risk-rules.md
- ./phase-6b-api-and-operator-controls.md
- ./phase-6c-alerting-and-safety-ops.md

本次只允许修改：
- src/infra/observability/
- apps/api/ 中与告警触发直接相关的少量代码
- apps/trader/
- tests/unit/
- tests/integration/

本次必须完成：
- 建立结构化日志基础
- 接入最小 Telegram 告警或等价通知路径
- 为关键异常定义告警触发点
- 让 kill switch、风险拒绝、保护模式等事件具备可观测性

严格不要做：
- 不做完整监控平台
- 不做 Prometheus / Grafana
- 不做复杂告警编排

完成后请输出：
1. 已修改文件
2. 已接入的告警路径
3. 关键告警触发点
4. 日志/告警验证结果
5. 是否可以认为 Phase 6 已完成
```
