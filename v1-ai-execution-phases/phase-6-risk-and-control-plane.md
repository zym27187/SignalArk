# Phase 6：Risk 与最小控制面

这份文件用于定义 `Phase 6` 的总目标、边界和总体验收口径。

默认推荐按下面顺序执行子任务；只有当前改动已经非常小、明确只需补一处控制或安全缺口时，才直接使用本文件：

- `./phase-6a-pretrade-risk-rules.md`
- `./phase-6b-api-and-operator-controls.md`
- `./phase-6c-alerting-and-safety-ops.md`

完成 `6A -> 6B -> 6C` 后，可以回到本文件做总体验收或小范围补缝。

## 本次目标

让 V1 具备基础安全性和人工接管能力，避免系统无闸门地下单。

## 前置依赖

- `Phase 5：OMS 与 Paper Execution`

## 必读上下文

- `./00-master-plan.md`
- `./testing-standards.md`
- `./implementation-decisions.md`
- `./phase-5-oms-and-paper-execution.md`

## 允许修改范围

- `src/domain/risk/`
- `apps/api/`
- `src/infra/observability/`
- `src/infra/db/` 中与单活 trader 保护直接相关的少量代码
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
- 提供健康检查与就绪检查
- 限制同一交易账户只允许 `1 个 active trader` 实例
- 明确 `kill switch` 的动作边界：禁止新开仓 / 增仓，但允许 `cancel all`、减仓和平仓
- 接入最小 Telegram 告警

## 本次不要做

- 不做完整 dashboard
- 不做复杂 RBAC
- 不做复杂动态风控模型
- 不做全量监控平台

## 默认实现细节

### 1. 控制状态优先级

Phase 6 默认采用下面 4 个控制状态：

- `normal`
- `strategy_paused`
- `kill_switch`
- `protection_mode`

状态优先级建议固定为：

`protection_mode > kill_switch > strategy_paused > normal`

说明：

- `strategy_paused`：停止生成新的交易动作，但不等于系统故障
- `kill_switch`：操作者触发的 `reduce-only` 闸门
- `protection_mode`：系统自动进入的 `reduce-only` 安全状态

### 2. 默认配置键与建议初值

如果项目中尚未引入独立配置覆盖，建议默认采用：

- `risk.max_single_symbol_notional_usdt = 5000`
- `risk.max_total_open_notional_usdt = 10000`
- `risk.min_order_notional_usdt = 25`
- `risk.market_stale_threshold_seconds = 120`
- `controls.lease_ttl_seconds = 15`
- `controls.lease_heartbeat_interval_seconds = 5`
- `alerts.telegram.enabled = false`

说明：

- 这些值是 V1 的保守基线，不是收益优化参数
- 如果后续在 `Phase 0` 或配置文件中调整，字段语义必须保持不变

### 3. 默认控制面 API

如果当前仓库尚未存在既定 API 风格，建议最小控制面至少暴露：

- `GET /health/live`
- `GET /health/ready`
- `GET /v1/status`
- `GET /v1/positions`
- `GET /v1/orders/active`
- `POST /v1/controls/strategy/pause`
- `POST /v1/controls/strategy/resume`
- `POST /v1/controls/kill-switch/enable`
- `POST /v1/controls/kill-switch/disable`
- `POST /v1/controls/cancel-all`

`GET /v1/status` 建议至少返回：

- `trader_run_id`
- `instance_id`
- `account_id`
- `control_state`
- `strategy_enabled`
- `kill_switch_active`
- `protection_mode_active`
- `ready`
- `market_data_fresh`
- `latest_final_bar_time`
- `lease_owner_instance_id`
- `lease_expires_at`
- `fencing_token`

### 4. 默认日志与告警字段

Phase 6 中的关键日志和告警建议至少带上：

- `event_name`
- `severity`
- `trader_run_id`
- `instance_id`
- `account_id`
- `exchange`
- `symbol`
- `control_state`
- `reason_code`
- `fencing_token`

## 完成标准

- 所有下单动作都先经过统一风险闸门
- 风险拒绝有明确原因
- 人工可以查询状态并接管系统
- 操作者可以判断系统是否健康与就绪
- 同一交易账户不会被多个 active trader 实例同时接管
- `kill switch` 激活后不会阻断 `reduce_only`、减仓和平仓路径

## 最低验证要求

- 至少有测试覆盖风险放行和风险拒绝
- 至少有测试覆盖 `kill switch` 或策略暂停
- 至少有测试覆盖健康检查或就绪检查
- 至少验证一次重复 trader 启动被拦截或等价保护路径
- 至少验证一次告警链路或等价通知路径
- 至少验证一次 `kill switch` 拦截开仓但允许减仓或平仓

## 本次交付时必须汇报

- 已实现哪些 pre-trade risk 规则
- API 暴露了哪些最小控制能力
- 健康检查如何定义
- 单活 trader 保护采用什么机制
- `kill switch` 与 `cancel all` 允许 / 禁止哪些动作
- 当前哪些异常会触发告警

## 可直接复制给 AI 的执行提示词

```text
你现在负责本项目的 Phase 6：Risk 与最小控制面。

如果当前任务可以明确收敛到 pre-trade risk、操作控制、或告警与安全运维中的单一能力域，请优先改用 `Phase 6A / 6B / 6C`，不要默认直接做整个 Phase 6。

请先阅读：
- ./00-master-plan.md
- ./testing-standards.md
- ./implementation-decisions.md
- ./phase-6-risk-and-control-plane.md
- ./phase-5-oms-and-paper-execution.md

本次只允许修改：
- src/domain/risk/
- apps/api/
- src/infra/observability/
- src/infra/db/ 中与单活 trader 保护直接相关的少量代码
- apps/trader/
- tests/unit/
- tests/integration/

本次必须完成：
- 实现最大仓位、最大名义价值、重复下单、行情过期、最小下单量等 pre-trade risk
- 提供状态查询接口
- 提供策略启停、kill switch、cancel all
- 提供健康检查与就绪检查
- 限制同一交易账户只允许 1 个 active trader 实例
- 明确 kill switch 的动作边界：禁止新开仓 / 增仓，但允许 cancel all、减仓和平仓
- 接入最小 Telegram 告警

严格不要做：
- 不做完整 dashboard
- 不做复杂 RBAC
- 不做复杂动态风控
- 不做全量监控平台

完成后请输出：
1. 已修改文件
2. 已完成能力
3. 已实现的风控规则
4. API / 控制能力
5. 健康检查 / 单活保护
6. kill switch / cancel all 动作边界
7. 告警能力
8. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
9. 未解决风险
10. 是否可以进入 Phase 7
```
