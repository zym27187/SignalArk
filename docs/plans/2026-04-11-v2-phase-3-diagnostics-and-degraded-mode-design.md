# V2 Phase 3 Diagnostics And Degraded Mode Design

## Goal

在不引入额外监控平台和复杂聚合服务的前提下，把 SignalArk 当前已经存在的诊断事实收口成一套更一致的控制面表达，让操作者可以明确知道：

- 当前看到的是实时数据、fixture 数据、缺失数据还是降级状态
- trader 当前是健康、保护、租约异常还是行情不新鲜
- API、MCP、前端对 runtime bar audit、diagnostics replay 和 degraded mode 的解释是否一致

## Recommended Architecture

### 1. One Canonical `degraded_mode` Fact

Phase 3 新增一个统一事实对象 `degraded_mode`，最小字段固定为：

- `status`
- `reason_code`
- `message`
- `data_source`
- `effective_at`

并补两个面向操作者的字段：

- `impact`
- `suggested_action`

该对象不只提供独立接口，也要复用到以下现有 payload：

- `/health/ready`
- `/v1/status`
- `/v1/market/runtime-bars`
- `/v1/diagnostics/replay-events`

这样前端、MCP 和 API 都可以围绕同一套事实工作，而不是各自推断。

### 2. Status Resolution Order

为避免“多个异常同时出现时谁覆盖谁”不清楚，Phase 3 固定以下优先级：

1. `CONTROL_PLANE_SCHEMA_MISSING`
2. `FIXTURE_DATA_IN_USE`
3. `PROTECTION_MODE_ACTIVE`
4. `LEASE_NOT_HELD`
5. `MARKET_DATA_STALE`
6. `MARKET_DATA_MISSING`
7. `RUNTIME_STATUS_MISSING`
8. `LIVE_DATA_READY`

含义：

- 前三类优先表示系统虽然还能给出部分状态，但操作者不能把它当成正常在线交易
- `MARKET_DATA_MISSING` 与 `MARKET_DATA_STALE` 明确区分“没有数据”和“有数据但过旧”
- `FIXTURE_DATA_IN_USE` 单独成类，避免前端只靠颜色或 fallback 标签隐式表达

### 3. MCP Alignment

当前 MCP 已有：

- `get_status`
- `get_shared_contracts`
- `replay_events`

但缺少：

- runtime bar audit 入口
- degraded mode 独立入口

Phase 3 补两个只读 MCP 工具：

- `get_runtime_bars`
- `get_degraded_mode`

其中 `get_runtime_bars` 直接复用 API control-plane service 的 runtime bar audit payload，保证返回结构和 HTTP API 一致。

### 4. Frontend Rendering Strategy

前端遵守“明显提示 -> 后果说明 -> 建议动作”的顺序。

具体落点：

- `StatusHero`：显示当前 degraded mode 结论
- `MarketView`：在 runtime bar audit 和数据说明区域显式说明当前数据来源与降级原因
- `EventTimeline`：显示 replay event 的 `reason_code`，减少只看事件名还要翻日志的情况

Phase 3 不新增整页诊断中心，而是在当前主要控制面页面里把解释层补齐。

## Data Flow

1. `ApiControlPlaneService` 统一生成 `degraded_mode`
2. `status_payload`、`market_runtime_bars_payload`、`replay_events_payload` 嵌入同一对象
3. MCP backend 直接代理对应 payload
4. 前端通过现有 `useDashboardData` / `useMarketData` 读取嵌入后的状态，不额外再造一套推断逻辑

## Error Handling

- 控制面 schema 缺失时，`degraded_mode` 仍应可返回，不能再靠异常字符串隐式表达
- replay 结果为空时，不等于“系统健康”，仍要带出当前 degraded mode
- 市场页 fallback 到 fixture 时，必须用明确文案告诉用户“当前数据只适合演练，不应视为真实市场”

## Testing Strategy

### Backend

- API 集成测试覆盖：
  - schema 缺失时的 degraded mode
  - fixture source 下的 degraded mode
  - runtime bar audit payload 含统一 degraded mode
  - replay payload 含统一 degraded mode 与 event `reason_code`

### MCP

- 单元测试覆盖：
  - `tools/list` 含 `get_runtime_bars` 和 `get_degraded_mode`
  - 两个工具都直接复用控制面 payload

### Frontend

- `StatusHero`：验证 degraded mode 的明显提示、后果说明、建议动作
- `useMarketData`：验证 runtime bar audit 带 degraded mode 时仍可稳定消费
- `App` 或相关组件测试：验证 market / operations 页面会显式展示 degraded mode

## Out Of Scope

- 不做完整监控大盘
- 不引入 Prometheus / Grafana
- 不把全部日志流直接暴露到前端
- 不实现新的控制动作写接口
