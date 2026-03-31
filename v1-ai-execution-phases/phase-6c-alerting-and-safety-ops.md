# Phase 6C：告警与安全运维

这份文件用于把 `Phase 6` 进一步拆成更适合 AI 单次编码的子任务。

## 本次目标

补齐最小可观测与告警能力，让关键异常能被发现并触发人工介入。

## 前置依赖

- `Phase 6A：Pre-Trade Risk Rules`
- `Phase 6B：API 与操作控制`

## 必读上下文

- `./00-master-plan.md`
- `./testing-standards.md`
- `./implementation-decisions.md`
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

## 默认实现细节

### 1. 结构化日志字段

建议默认所有关键日志事件至少包含：

- `event_name`
- `severity`
- `timestamp`
- `trader_run_id`
- `instance_id`
- `account_id`
- `exchange`
- `symbol`
- `control_state`
- `reason_code`

如果与订单相关，建议继续补充：

- `signal_id`
- `order_intent_id`
- `order_id`
- `fencing_token`

### 2. 建议立即告警的事件

建议默认把下面事件定义为“立即通知”：

- 进入 `protection_mode`
- lease 丢失或 fencing 失效
- 关键数据库写入失败，尤其是 `order_intent / order / fill`
- `cancel all` 执行失败
- trader 连续超过 `30s` 处于 `not ready`

### 3. 建议告知型告警的事件

建议默认把下面事件定义为“操作者知情即可”：

- `kill switch` 被启用或解除
- 手工 `cancel all` 被触发
- 同一 symbol / rule 在 `5 分钟` 内连续出现多次风险拒绝
- 行情连续过期超过 `2` 个检测周期

### 4. Telegram 消息最小内容

Telegram 或等价通知建议至少包含：

- 事件名称
- 严重级别
- `account_id`
- `symbol`
- `control_state`
- `reason_code`
- 时间戳

### 5. 告警降噪

为避免单个故障刷屏，建议默认加入简单 cooldown：

- 相同 `event_name + account_id + symbol + reason_code` 组合在 `5 分钟` 内合并
- 进入 `protection_mode` 与 lease 丢失不做合并，始终立即发送

## 完成标准

- 关键异常可被结构化记录
- 至少有一条稳定告警路径
- 操作者能从日志和告警中快速判断系统状态

## 最低验证要求

- 至少验证一次告警链路或等价通知路径
- 至少验证一次关键异常日志输出

## 本次交付时必须汇报

- 已接入哪条告警路径
- 哪些关键异常会触发告警
- 哪些复杂监控与运维能力仍是后续项

## 可直接复制给 AI 的执行提示词

```text
你现在负责本项目的 Phase 6C：告警与安全运维。

请先阅读：
- ./00-master-plan.md
- ./testing-standards.md
- ./implementation-decisions.md
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
2. 已完成能力
3. 已接入的告警路径
4. 关键告警触发点
5. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
6. 未解决风险
7. 是否可以认为 Phase 6 已完成
```
