# V2 Phase 2 Control Plane And Balance Visibility

**Goal:** 把运维页从“能看状态”推进到“能解释账户资金、能记录 runtime 标的变更请求、能明确控制动作作用范围”。

**Scope:** `apps/api`, `apps/trader/control_plane.py`, `apps/web`, `migrations`, `tests`

## Implementation Notes

### 1. 资金摘要接口与解释层

- 新增 `GET /v1/balance/summary`
- 返回固定字段：
  - `cash_balance`
  - `available_cash`
  - `frozen_cash`
  - `market_value`
  - `equity`
  - `as_of_time`
  - `summary_message`
- 同时补充解释字段：
  - `cash_explanation`
  - `position_explanation`
  - `equity_explanation`
- 计算口径固定为：
  - `cash_balance = 最新 CNY balance snapshot.total`
  - `equity = cash_balance + market_value`
  - `market_value = sum(qty * mark_price_or_avg_entry_price)`

### 2. runtime 标的申请闭环

- 保留 `GET /v1/symbols/inspect` 作为读路径
- 新增 `POST /v1/symbols/runtime-requests`
- 新增持久化表 `runtime_symbol_requests`
- 当前生效方式固定为 `requires_reload`
- 当前不做热更新 `SIGNALARK_SYMBOLS`
- UI 上必须区分：
  - 当前已在 runtime
  - 可提交 runtime 请求
  - 已记录请求，等待重载
  - 尚未进入 `supported_symbols`，不可申请

### 3. 控制动作结果补强

- 所有控制动作补齐：
  - `effective_scope`
  - `reason_code`
  - `effective_at`
- 当前 scope 约定：
  - `pause/resume -> strategy_submission`
  - `kill switch -> opening_order_gate`
  - `cancel all -> active_orders`

### 4. 前端承载方式

- `OperationsView` 新增“资金与权益”卡片
- `SymbolInspectorPanel` 从 Phase 1 的会话内提示升级为真正提交请求并显示结果
- `ControlPanel` 结果区新增作用范围与原因分类

## Validation

- `.venv/bin/python -m pytest tests/integration/test_api_operator_controls.py tests/smoke/test_alembic_upgrade_smoke.py -q`
- `npm --prefix apps/web test -- --run src/lib/api.test.ts src/components/SymbolInspectorPanel.test.tsx src/components/ControlPanel.test.tsx src/components/BalanceSummaryPanel.test.tsx src/hooks/use-dashboard-data.test.tsx src/App.test.tsx`
- `npm --prefix apps/web run check-types`

## Deferred

- 不做 runtime 热重载
- 不做移除 runtime 标的的控制动作
- 不做更复杂的账户分析后台
