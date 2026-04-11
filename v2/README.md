# SignalArk V2

本目录用于记录 SignalArk 下一阶段迭代文档。

当前文件：

- [00-master-plan.md](./00-master-plan.md)：V2 总控文件
- [00-scope-draft.md](./00-scope-draft.md)：V2 范围草案
- [phase-0-boundaries-and-shared-contracts.md](./phase-0-boundaries-and-shared-contracts.md)：边界、术语与共享契约
- [phase-1-frontend-usability-and-symbol-management.md](./phase-1-frontend-usability-and-symbol-management.md)：前端易用性与股票代码管理
- [phase-2-control-plane-and-balance-visibility.md](./phase-2-control-plane-and-balance-visibility.md)：控制面与账户资金可见性
- [phase-3-diagnostics-and-degraded-mode.md](./phase-3-diagnostics-and-degraded-mode.md)：诊断统一与降级模式表达
- [phase-4-research-standardization-and-comparison.md](./phase-4-research-standardization-and-comparison.md)：research 标准化与对照能力
- [phase-5-ai-strategy-seams-and-audit.md](./phase-5-ai-strategy-seams-and-audit.md)：AI 策略接缝与统一审计

使用原则：

- V2 基于当前 V1 闭环继续演进，不是推倒重来。
- 先固定边界，再拆 phase，再进入具体实现。
- 优先做能强化研究、交易、控制面一致性的事项，不先追求大而全扩张。
- 默认把“金融小白也能理解界面内容”作为前端设计约束，而不是事后补文案。
- 每个后续 phase 都应当能够独立验收，避免跨多个主题同时重写。

执行顺序建议：

1. 先阅读 [00-scope-draft.md](./00-scope-draft.md)
2. 再阅读 [00-master-plan.md](./00-master-plan.md)
3. 再按 `Phase 0 -> Phase 5` 顺序推进
