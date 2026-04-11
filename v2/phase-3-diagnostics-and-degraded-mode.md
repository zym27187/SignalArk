# Phase 3：诊断统一与降级模式表达

这份文件用于补齐 V2 的可排查能力，减少“系统其实出问题了，但界面看起来像正常”的情况。

## 本次目标

统一 API、MCP、前端和 trader 对关键诊断状态的表达方式，并让降级模式、数据来源和审计事实对操作者可见。

## 前置依赖

- [Phase 0：边界、术语与共享契约](./phase-0-boundaries-and-shared-contracts.md)
- [Phase 2：控制面与账户资金可见性](./phase-2-control-plane-and-balance-visibility.md)

## 必读上下文

- [00-scope-draft.md](./00-scope-draft.md)
- [00-master-plan.md](./00-master-plan.md)
- [phase-0-boundaries-and-shared-contracts.md](./phase-0-boundaries-and-shared-contracts.md)
- [phase-2-control-plane-and-balance-visibility.md](./phase-2-control-plane-and-balance-visibility.md)
- [README.md](../README.md)
- [v1-ai-execution-phases/testing-standards.md](../v1-ai-execution-phases/testing-standards.md)

## 允许修改范围

- `apps/api/`
- `apps/mcp/`
- `apps/web/`
- `apps/trader/`
- `src/infra/observability/`
- `tests/unit/`
- `tests/integration/`

## 本次必须完成的任务

- 统一关键诊断状态的 reason code 或等价语义。
- 明确区分：
  - 真实数据
  - fixture 数据
  - 数据缺失
  - 数据降级
- 让前端、HTTP API 和 MCP 至少在下面能力上保持最小一致性：
  - runtime bar audit
  - control action result
  - diagnostics replay
  - degraded mode status
- 让 trader 的关键只读异常状态更容易暴露出来，例如：
  - 行情不新鲜
  - lease 丢失
  - protection mode
  - 数据源降级
- 避免静默 fallback，优先显式告诉操作者系统当前“不确定”的部分。

## 本次不要做

- 不做完整监控平台
- 不引入 Prometheus / Grafana
- 不做复杂告警编排系统
- 不把所有日志都直接搬到前端

## 默认实现细节

### 1. 降级模式建议

建议默认至少保留：

- `status`
- `reason_code`
- `message`
- `data_source`
- `effective_at`

### 2. 前端表现建议

降级状态应优先以：

- 明显提示
- 后果说明
- 建议动作

的顺序表达，而不是只显示技术错误字符串。

### 3. 审计事实优先级

本阶段建议优先收口：

- runtime bars
- control actions
- replay events
- data source status

## 完成标准

- 关键诊断语义在 API、MCP、前端三者之间更一致
- 降级模式和数据来源不再静默隐藏
- trader 的关键只读异常状态可以被值守人员直接看到

## 最低验证要求

- 至少验证一次降级状态表达
- 至少验证一次 API / MCP / 前端中的诊断契约对齐
- 至少验证一次 runtime bar audit 或 replay 查询
- 如未能覆盖三端一致性，必须明确剩余缺口

## 本次交付时必须汇报

- 哪些诊断能力实现了三端一致
- 降级模式如何定义和显示
- 真实数据与 fixture 数据如何区分
- 当前仍有哪些状态只能靠日志排查
- 是否可以进入 Phase 4
