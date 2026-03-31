# V1 AI 单次执行文件索引

这组文件用于把 V1 拆成适合 AI 单次执行的任务。

使用方式：

1. 先阅读总控文件：`./00-master-plan.md`
2. 如果想直接复制提示词，优先使用：`./prompts.md`
3. 每次只选择 `1 个 phase` 文件或 `1 个提示词` 交给 AI
4. 当前 phase 未完成前，不进入下一个 phase
5. AI 完成后，先验收，再进入下一阶段

执行顺序：

1. [Phase 0：范围与配置骨架](./phase-0-scope-and-config.md)
2. [Phase 1：事件模型与领域对象](./phase-1-domain-model.md)
3. [Phase 2：数据库与核心持久化](./phase-2-db-and-persistence.md)
4. [Phase 3：Collector 与 Market Gateway](./phase-3-collector-and-market-gateway.md)
5. [Phase 4：Trader 主循环与 Event Bus](./phase-4-trader-loop-and-event-bus.md)
6. [Phase 5：OMS 与 Paper Execution](./phase-5-oms-and-paper-execution.md)
7. [Phase 6：Risk 与最小控制面](./phase-6-risk-and-control-plane.md)
8. [Phase 7：基线策略](./phase-7-baseline-strategy.md)
9. [Phase 8：最小 Backtest 一致性](./phase-8-backtest-minimum.md)
10. [Phase 9：对账与保护模式](./phase-9-reconciliation-and-protection.md)

如果需要更细粒度的单次编码任务，请优先使用下面这些子任务文件：

- [Phase 5A：OMS 持久化与状态机](./phase-5a-oms-persistence-and-state-machine.md)
- [Phase 5B：Paper Execution Adapter](./phase-5b-paper-execution-adapter.md)
- [Phase 5C：Portfolio / Balance / PnL 更新](./phase-5c-portfolio-balance-and-pnl.md)
- [Phase 6A：Pre-Trade Risk Rules](./phase-6a-pretrade-risk-rules.md)
- [Phase 6B：API 与操作控制](./phase-6b-api-and-operator-controls.md)
- [Phase 6C：告警与安全运维](./phase-6c-alerting-and-safety-ops.md)

使用原则：

- 一次只让 AI 做一个 phase
- 不要把多个 phase 合并成一次执行
- 如果单次改动明显过大，优先把 `Phase 5` 或 `Phase 6` 再细拆
- 所有 phase 都必须遵守总控文件里的 V1 固定边界
- `Phase 5` 和 `Phase 6` 如果单次改动明显过大，优先改用 5A-5C、6A-6C 子任务文件

建议验收输出：

- 已修改文件
- 已完成能力
- 未完成项
- 风险与待确认点
- 是否可以进入下一阶段
