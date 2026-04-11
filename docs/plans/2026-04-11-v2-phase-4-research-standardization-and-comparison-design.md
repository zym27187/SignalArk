# V2 Phase 4 Research Standardization And Comparison Design

## Goal

在不引入完整实验平台和复杂编排系统的前提下，把 SignalArk 当前 research 结果统一成一套更稳定、更可比较的输出契约，让操作者可以直接回答：

- 当前是快速预览、正式评估、参数扫描还是滚动评估
- 这份结果使用了什么样本、成本模型和参数快照
- baseline 与 candidate 是否真的基于同一份样本和同一套指标语义比较
- 某个股票代码当前是否可用于 research、是否已被系统支持、是否已进入 runtime

## Recommended Architecture

### 1. One Canonical Research Snapshot Contract

Phase 4 保持 `/v1/research/snapshot` 为主读接口，但扩展成统一契约：

- 顶层固定 `mode`
- 顶层新增 `summary`
- `manifest` 固定最小字段：
  - `strategyId`
  - `strategyVersion`
  - `mode`
  - `symbol`
  - `timeframe`
  - `barCount`
  - `samplePurpose`
  - `costModel`
  - `parameterSnapshot`
  - `generatedAt`
- 可选新增：
  - `experiments`
  - `comparison`

这样 research 页面、AI snapshot 和 CLI 导出可以围绕同一套解释层工作，而不是前端自己拼比较语义。

### 2. Four Explicit Research Modes

Phase 4 固定四种模式：

1. `preview`
2. `evaluation`
3. `parameter_scan`
4. `walk_forward`

其中：

- `preview` 使用 preview 样本口径，不做时间分段
- `evaluation` 使用 evaluation 样本口径，可做时间分段
- `parameter_scan` 仍基于 evaluation 样本，但额外执行 baseline 默认参数小网格扫描
- `walk_forward` 仍基于 evaluation 样本，但额外执行固定窗口与步长的滚动评估

### 3. Standardized Comparison Fact

当 candidate 存在时，统一返回 `comparison`：

- `baselineLabel`
- `candidateLabel`
- `candidateKind`
- `sameSample`
- `sameMetricSemantics`
- `netPnlDelta`
- `totalReturnDeltaPct`
- `maxDrawdownDeltaPct`
- `tradeCountDelta`
- `turnoverDelta`
- `decisionDiffCount`
- `decisionDiffs`
- `summaryMessage`

当前 Phase 4 的两个 candidate 来源：

- `parameter_scan` 里的 best variant
- `/v1/research/ai-snapshot` 里的 AI candidate

### 4. Symbol Research Readiness

`/v1/symbols/inspect` 继续保留 observed / supported / runtime 三层，但额外补一个只读事实：

- `research_status.eligible`
- `research_status.reason_code`
- `research_status.message`

当前实现明确表达：

- 只有 `supported_symbols` 内的股票代码可直接用于 research
- runtime 仍然是更严格的生效层，不等于 research ready

## Frontend Rendering Strategy

研究页默认遵守“先结论、再实验、再审计、再细节”的顺序：

- Hero 区直接切换四种 research mode
- `summary` 先回答当前模式、样本可信度和关键比较结论
- `experiments` 直接展示参数扫描或滚动评估摘要
- `comparison` 用统一字段渲染 baseline vs candidate
- symbol inspector 补 research 可用性说明

## Testing Strategy

### Backend

- API 集成测试覆盖：
  - preview / evaluation / parameter_scan / walk_forward 四种模式
  - manifest 的 mode / samplePurpose / parameterSnapshot / costModel
  - parameter scan best variant comparison
  - AI snapshot comparison
  - symbol inspect 的 `research_status`

### Frontend

- `useResearchData`：验证 mode 请求参数
- `App`：验证研究模式切换与 comparison 渲染
- `SymbolInspectorPanel`：验证 research 可用性说明
- TS type check：确保 Phase 4 新契约在全前端一致

## Out Of Scope

- 不做完整实验任务队列
- 不做多策略实验数据库
- 不做大规模参数搜索系统
- 不做对象存储与结果归档平台化
