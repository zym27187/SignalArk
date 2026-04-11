# Phase 0：边界、术语与共享契约

这份文件用于定义 V2 的起始阶段，先把语义和契约收口，再进入具体功能实现。

## 本次目标

固定 V2 的共享术语、关键状态模型和跨平面契约，避免后续在前端、API、MCP、research、trader 各自实现一套近似但不一致的语义。

## 前置依赖

- 当前 V1 主链路已可运行

## 必读上下文

- [00-scope-draft.md](./00-scope-draft.md)
- [00-master-plan.md](./00-master-plan.md)
- [README.md](../README.md)
- [v1-ai-execution-phases/testing-standards.md](../v1-ai-execution-phases/testing-standards.md)

## 允许修改范围

- `v2/`
- `README.md`
- `apps/api/` 中与响应契约或只读 schema 直接相关的少量代码
- `apps/mcp/` 中与只读契约对齐直接相关的少量代码
- `apps/web/src/types/`
- `apps/web/src/lib/`
- `src/config/`
- `tests/unit/`

## 本次必须完成的任务

- 明确 `Research Plane / Trading Plane / Control Plane` 的职责边界。
- 固定前端新增股票代码的分层语义，至少覆盖：
  - `observed`
  - `supported`
  - `runtime_enabled`
- 固定关键只读事实的字段语义，例如：
  - `balance summary`
  - `control action result`
  - `runtime bar audit summary`
  - `degraded mode status`
  - `research manifest summary`
- 固定关键 reason code 或等价错误分类，避免 UI、API、MCP 各自起名。
- 为后续 Phase 提供统一的命名、状态和值域约定。

## 本次不要做

- 不直接重写前端页面
- 不一次性补完所有接口
- 不在本阶段扩写复杂业务逻辑
- 不把“文档阶段”演变成大规模目录重构

## 默认实现细节

### 1. 股票代码状态建议

V2 建议至少固定下面 3 层状态：

- `observed`：前端已添加，可用于观察或 research 候选
- `supported`：系统具备名称、规则和基础校验能力
- `runtime_enabled`：已进入 trader 当前运行标的

可额外保留：

- `research_enabled`
- `validation_status`
- `activation_requires_confirmation`

### 2. 面向用户的表达建议

同一个状态建议同时保留两层信息：

- 机器可消费字段，例如 `reason_code`
- 用户可阅读摘要，例如 `message` 或 `summary`

### 3. 契约优先级

本阶段默认优先固定：

1. 字段语义
2. 状态取值
3. 前后端共享名称
4. 最小示例输出

只有在这几项固定后，后续 Phase 才进入批量实现。

## 完成标准

- V2 核心共享语义有清晰文档
- 股票代码的分层状态不再需要靠口头解释
- 关键只读事实已收口为稳定契约
- 后续 Phase 能够基于本文件继续拆实现，而不是重新讨论字段含义

## 最低验证要求

- 至少校对一次当前 API / 前端 / MCP / research 中已存在的相关命名差异
- 如本阶段引入类型或 schema 代码，至少运行相关 `unit` 测试
- 如未运行测试，必须明确说明原因和残余风险

## 当前 Phase 0 落地约定

本阶段已经约定并集中暴露以下共享契约入口：

- API：`GET /v1/contracts/shared`
- MCP：`get_shared_contracts`
- Python 共享源：`src/config/shared_contracts.py`

当前入口固定了下面几类内容：

- `Research Plane / Trading Plane / Control Plane` 的职责边界
- 股票代码 `observed / supported / runtime_enabled` 三层语义，以及 `supported_symbols` 与 `SIGNALARK_SYMBOLS` 的边界关系
- 关键事实的最小字段语义目录：
  - `balance_summary`
  - `control_action_result`
  - `runtime_bar_audit_summary`
  - `degraded_mode_status`
  - `research_manifest_summary`
- 当前已观察到的命名差异与后续 phase 的收口方向
- 关键 `reason_code` 家族，避免后续 API / MCP / 前端再次各自起名

本阶段默认保持两条兼容原则：

- 不打破现有 V1 主接口 shape
- 允许 research 继续保留现有 camelCase surface，但必须在共享契约里给出 canonical alias

## 本次交付时必须汇报

- 固定了哪些共享契约
- 股票代码的分层状态如何定义
- 哪些契约明确留给后续 Phase 再实现
- 当前仍有哪些语义尚未完全收口
- 是否可以进入 Phase 1
