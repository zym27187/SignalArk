# SignalArk V2 执行说明

这份文件用于定义 V2 的执行顺序、阶段边界和统一交付口径。

V2 不是重写项目，而是在当前 V1 稳定闭环基础上的结构化迭代：

- 强化三平面边界
- 强化前端可理解性
- 强化控制面、诊断面和 research 一致性
- 为 AI 增强预留稳定接缝

## 1. V2 的固定边界

V2 执行时，默认仍然必须遵守下面边界：

- 只支持 `cn_equity`
- 只支持 `a_share`
- 只支持 `paper`
- 只支持 `1 个交易账户`
- 只允许 `1 个 active trader`
- 实盘运行时只维持 `1 个 active 主策略`
- 交易触发仍以 `closed_bar` 为核心
- 数据源仍以当前 `eastmoney + fixture` 体系为基础
- PostgreSQL 仍是核心恢复事实源
- 不在 V2 中引入 Kafka、Kubernetes 或大规模服务拆分

V2 的重点不是扩边界，而是把当前边界下的产品可理解性、运维可见性和研究一致性做稳。

## 2. V2 的执行规则

V2 默认按 phase 顺序执行，不建议跳阶段。

每个阶段都遵守下面规则：

1. 先完成当前阶段，再进入下一个阶段。
2. 当前阶段如仍存在关键语义未固定，不提前实现后续复杂能力。
3. 若某项需求会显著扩大范围，应在当前阶段标记为后置项，而不是顺手扩写。
4. 所有阶段都必须遵守 [00-scope-draft.md](./00-scope-draft.md) 的固定边界。
5. 所有阶段的测试执行与风险汇报，当前统一参考 [v1-ai-execution-phases/testing-standards.md](../v1-ai-execution-phases/testing-standards.md)。
6. V2 前端相关改动必须默认面向金融小白可理解，不应把解释层留到最后补。
7. “前端添加股票代码”必须区分观察、research、supported、runtime 等不同生效层级，不能默认等同于立刻加入 trader 交易范围。
8. 涉及 trader 当前运行标的的变更，必须要求显式确认，并说明是否立即生效、延迟生效或需要重启/重载。

## 3. 跨阶段固定契约

以下契约不应留到后续实现时再猜：

- `supported_symbols` 仍是系统支持边界，`SIGNALARK_SYMBOLS` 仍是当前 trader 运行边界，后者必须是前者的非空子集。
- 前端新增股票代码功能至少要能表达三层语义：
  - 仅观察或 research 使用
  - 已被系统支持
  - 已被当前 trader 运行时启用
- “输入股票代码”不应自动触发 trader 立即交易；任何会影响运行时交易范围的动作都要有显式确认和结果反馈。
- 前端对关键状态的表达默认采用“先结论、再解释、再细节”的顺序。
- 前端、HTTP API、MCP 对关键诊断能力应逐步收口为同一套 reason code 或等价语义，而不是各自起名字。
- research 输出需要稳定 manifest；不同策略之间的比较必须基于同一套样本、成本模型和指标语义。
- AI 策略实验必须复用统一的 strategy audit 契约，并保留 deterministic fallback。

## 4. V2 完成线

只有当下面这些条件基本同时成立时，V2 才算完成：

- 三平面边界在代码和文档层面都已清晰。
- 金融小白可以独立理解主要前端页面中的关键状态和风险提示。
- 用户可以通过前端添加股票代码，并清楚理解该代码当前的观察、research、supported、runtime 状态。
- 账户余额、可用资金、冻结资金和权益变化可以被控制台直接解释。
- 降级模式、数据来源和关键诊断状态具备统一表达。
- research 结果具备标准化 manifest、模式和对照输出。
- AI 候选策略能在统一语义下与 baseline 做横向比较。
- V2 没有破坏当前单账户、单主策略、A 股 `paper` 的稳定主链路。

## 5. 顺序执行计划

1. [Phase 0：边界、术语与共享契约](./phase-0-boundaries-and-shared-contracts.md)
2. [Phase 1：前端易用性与股票代码管理](./phase-1-frontend-usability-and-symbol-management.md)
3. [Phase 2：控制面与账户资金可见性](./phase-2-control-plane-and-balance-visibility.md)
4. [Phase 3：诊断统一与降级模式表达](./phase-3-diagnostics-and-degraded-mode.md)
5. [Phase 4：research 标准化与对照能力](./phase-4-research-standardization-and-comparison.md)
6. [Phase 5：AI 策略接缝与统一审计](./phase-5-ai-strategy-seams-and-audit.md)

## 6. 每次交付必须汇报

- 已修改文件
- 已完成能力
- 本阶段新增或固定了哪些契约
- 测试情况：
  - 已运行哪些测试
  - 哪些通过
  - 哪些未运行
  - 为什么未运行
  - 当前剩余测试风险
- 未完成项
- 风险与待确认点
- 是否可以进入下一阶段
