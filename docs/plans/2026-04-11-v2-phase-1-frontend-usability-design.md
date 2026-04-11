# V2 Phase 1 Frontend Usability Design

## Goal

在不提前进入 Phase 2 runtime 配置闭环的前提下，重构运维页的信息表达，并补齐股票代码输入与状态反馈入口，让金融小白可以看懂当前系统状态、关键风险，以及新增股票代码当前所处的 `observed / supported / runtime_enabled` 层级。

## Why This Phase Exists

Phase 0 已经固定了三平面边界、股票代码层级和关键只读事实的命名，但当前前端仍主要展示“系统内部状态”，缺少“对用户意味着什么”的解释层。用户看见 `kill switch`、`protection mode`、`runtime symbols` 时，仍需要依赖背景知识判断影响。

Phase 1 的目标不是做配置热更新，而是把“理解”和“确认”补到前端主流程中。

## Scope

### In Scope

- 重构 `Operations` 主视图的信息架构，遵循“先结论、再解释、再细节”
- 为关键术语补齐稳定解释
- 为高风险动作补齐影响说明和确认文案
- 新增股票代码检查入口
- 新增一个最小只读接口，用于返回股票代码规范化、层级状态和影响说明
- 为空状态、异常状态、降级状态补充更面向用户的提示
- 补充前端测试和相关 API 集成测试

### Out of Scope

- 不直接修改 `SIGNALARK_SYMBOLS`
- 不新增后端 runtime 热更新或重载逻辑
- 不做全局 onboarding 或完整新手教学系统
- 不重写 `Market` / `Research` 两页结构
- 不把“申请进入 runtime”做成真正生效的控制动作

## Recommended Architecture

### 1. Operations View As The Main Phase-1 Landing Zone

`OperationsView` 已经承载运行状态、控制动作、筛选器和时间线，是最自然的“理解入口”。Phase 1 继续以它为主承载页：

- `StatusHero`：先告诉用户系统能不能运行、当前风险会影响什么、最新行情是否可信
- 指标卡：保留，但 hint 改成面向用户的解释
- `ControlPanel`：补充动作影响说明和后果确认
- 新增 `SymbolInspectorPanel`：提供股票代码输入与层级反馈
- 新增 `TradingGlossaryPanel`：解释持仓、成交、冻结资金、权益、回撤、`kill switch`、`protection mode`

这样可以在不扩散范围的前提下，把 Phase 1 的关键能力集中到一个页面完成。

### 2. Minimal Read-only Symbol Inspection Endpoint

新增一个只读接口，例如 `GET /v1/symbols/inspect?symbol=...`，由 API 返回：

- 原始输入
- 规范化后的代码
- 格式是否合法
- 市场归属和交易所后缀解释
- 股票名称或“名称缺失”提示
- 当前层级状态：
  - `observed`
  - `supported`
  - `runtime_enabled`
- `reason_code`
- 用户可读 `message`
- “申请进入 runtime” 的影响说明和确认提示

该接口只做校验和解释，不做状态变更。

### 3. Contract Reuse Strategy

Phase 1 复用 Phase 0 已固定的共享语义：

- `supported_symbols` 仍是系统支持边界
- `status.symbols` 仍表示当前 runtime 边界
- `observed / supported / runtime_enabled` 的顺序和含义不能在前端重新定义
- 股票代码检查接口必须返回机器字段和用户可读摘要两层信息

前端不复制另一套业务语义，只负责把后端结果翻译成更易理解的界面。

## Component Design

### StatusHero

当前 `StatusHero` 主要是一句摘要。Phase 1 改成三层结构：

- 结论：系统现在是否可用
- 影响：当前风险会阻止什么，用户还能做什么
- 细节：环境、模式、实例、最近行情时间

当 `kill_switch_active`、`protection_mode_active`、`market_data_fresh=false` 或接口异常时，要明确告诉用户“影响是什么”，而不是只展示内部状态字符串。

### ControlPanel

控制面板继续保留现有动作，但要补强：

- 每个动作的影响范围说明
- 高风险动作确认时的后果提示
- 最近一次动作结果的“解释层”

例如 `cancel-all` 不只显示数量，还要说明“系统会尝试撤掉当前排队订单，但减仓保护订单可能被保留”。

### SymbolInspectorPanel

新组件放在 `OperationsView` 右侧栏，承担股票代码管理入口：

- 输入框 + 检查按钮
- 展示规范化结果
- 展示名称 / 名称缺失、市场归属、格式是否合法
- 用明确的层级卡片或标签显示：
  - 仅观察
  - 系统已支持
  - 当前 runtime 已启用
- 提供一个“申请加入 runtime” 的显式开关或按钮
- 当用户选择这一步时，弹出本阶段仅做影响说明的确认区域：
  - 当前不会立即生效
  - 真正加入 runtime 需要后续 phase 的后端闭环
  - 可能影响 trader 的交易范围

Phase 1 允许该“申请”只存在于当前前端会话，不做持久化。

### TradingGlossaryPanel

新增一个小型术语解释区，固定下面术语的通俗解释：

- 持仓
- 成交
- 冻结资金
- 权益
- 回撤
- `kill switch`
- `protection mode`

文案原则：

- 先说它代表什么
- 再说什么时候需要关注
- 少用内部缩写

## Data Flow

1. `useDashboardData` 继续负责读取 status / positions / orders / history / events
2. `SymbolInspectorPanel` 自己管理输入态，并在用户提交时调用新的 inspect API
3. inspect API 返回标准层级与解释信息
4. 用户如果勾选“申请加入 runtime”，前端只在本地显示确认态和影响说明，不发送变更请求

## Error Handling

### Symbol Inspection Errors

- 如果输入为空：提示用户先输入代码
- 如果格式不合法：仍展示规范化结果和修正建议
- 如果后端请求失败：前端保留输入和本地格式判断，但明确标记“系统层状态未确认”

### Dashboard Errors

对已有 `status` / `control` / `events` 错误提示做更面向用户的文案，例如：

- 行情接口失败时，说明价格可能不是最新
- 状态接口失败时，说明当前页面无法确认系统是否仍在运行

## Testing Strategy

### Frontend Tests

- `StatusHero`：验证结论和影响说明
- `ControlPanel`：验证高风险动作的确认和结果解释
- `SymbolInspectorPanel`：验证输入、检查、层级展示、runtime 申请确认
- `App` 或 `OperationsView`：验证新模块被挂载并与现有状态共存

### API Tests

- 新增 inspect endpoint 的集成测试：
  - 支持中的 runtime symbol
  - 支持中但未启用的 symbol
  - 未支持但格式合法的 symbol
  - 格式不合法的 symbol

## Success Criteria

- 用户打开 `Operations` 页后，能先看到“系统现在能不能用”和“当前风险影响什么”
- 用户输入股票代码后，可以明确知道它属于观察层、支持层还是 runtime 层
- 用户能理解“申请进入 runtime” 当前不会立即生效
- 关键术语和高风险动作不再需要依赖口头解释
