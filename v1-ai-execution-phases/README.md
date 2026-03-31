# V1 AI 单次执行文件索引

这组文件用于把 V1 拆成适合 AI 单次执行的任务。

使用方式：

1. 先阅读总控文件：`./00-master-plan.md`
2. 再阅读测试规范：`./testing-standards.md`
3. 再阅读工程模板与技术栈固定决策：`./implementation-decisions.md`
4. 如果想直接复制提示词，优先使用：`./prompts.md`，并保留提示词中的“请先阅读”和“完成后请输出”
5. 每次只选择 `1 个 phase` 文件或 `1 个提示词` 交给 AI
6. 当前 phase 未完成前，不进入下一个 phase
7. AI 完成后，先验收，再进入下一阶段

执行顺序：

1. [Phase 0：范围与配置骨架](./phase-0-scope-and-config.md)
2. [Phase 1：事件模型与领域对象](./phase-1-domain-model.md)
3. [Phase 2A：数据库表结构与 Migration 草案](./phase-2a-db-schema-and-migration-draft.md)
4. [Phase 2：数据库与核心持久化](./phase-2-db-and-persistence.md)
5. [Phase 3：Collector 与 Market Gateway](./phase-3-collector-and-market-gateway.md)
6. [Phase 4：Trader 主循环与 Event Bus](./phase-4-trader-loop-and-event-bus.md)
7. [Phase 5A：OMS 持久化与状态机](./phase-5a-oms-persistence-and-state-machine.md)
8. [Phase 5B：Paper Execution Adapter](./phase-5b-paper-execution-adapter.md)
9. [Phase 5C：Portfolio / Balance / PnL 更新](./phase-5c-portfolio-balance-and-pnl.md)
10. [Phase 6A：Pre-Trade Risk Rules](./phase-6a-pretrade-risk-rules.md)
11. [Phase 6B：API 与操作控制](./phase-6b-api-and-operator-controls.md)
12. [Phase 6C：告警与安全运维](./phase-6c-alerting-and-safety-ops.md)
13. [Phase 7：基线策略](./phase-7-baseline-strategy.md)
14. [Phase 8：最小 Backtest 一致性](./phase-8-backtest-minimum.md)
15. [Phase 9：对账与保护模式](./phase-9-reconciliation-and-protection.md)

总览文件：

- [Phase 5：OMS 与 Paper Execution](./phase-5-oms-and-paper-execution.md)
- [Phase 6：Risk 与最小控制面](./phase-6-risk-and-control-plane.md)

使用原则：

- 一次只让 AI 做一个 phase
- 不要把多个 phase 合并成一次执行
- 如果单次改动明显过大，优先把 `Phase 2`、`Phase 5` 或 `Phase 6` 再细拆
- 所有 phase 都必须遵守总控文件里的 V1 固定边界
- 工程模板、基础目录和技术栈默认以 `implementation-decisions.md` 为准；如果某个 phase 需要偏离，必须在交付说明中写清楚原因
- `Phase 2` 默认优先采用 `Phase 2A -> Phase 2` 的执行路径；如果当前改动已经足够小，也可以直接做 `Phase 2`
- `Phase 5` 默认优先采用 `Phase 5A -> Phase 5B -> Phase 5C` 的执行路径；`Phase 5` 总览文件主要用于边界说明、总体验收和小范围补缝
- `Phase 6` 默认优先采用 `Phase 6A -> Phase 6B -> Phase 6C` 的执行路径；`Phase 6` 总览文件主要用于边界说明、总体验收和小范围补缝
- `Phase 0` 除了配置骨架，还要固定 env / secret 契约、`paper` 模式事实源边界和 `trader_run_id` 约定
- `Phase 2A` 需要让核心交易事实可关联 `trader_run_id`，并为 market order 保留 `decision_price` 或等价字段
- `Phase 5 / 5A` 需要固定 `Signal.target_position -> OrderIntent.qty` 的 sizing contract，避免后续实现各自解释字段
- `Phase 3` 需要明确 bar 唯一键、去重规则，以及“只有 closed / final bar 才能进入可交易链路”
- `Phase 6` 需要补齐健康检查、就绪检查和单活 trader 保护，不能只做控制接口
- `Phase 6 / 6B` 的单活保护需要明确 `PostgreSQL lease + heartbeat + fencing token` 语义，不能只写“限制单活”
- `Phase 6 / 6A / 6B` 需要明确 `kill switch` 默认是 `reduce-only` 闸门：禁新开 / 增仓，但允许 `cancel all`、减仓和平仓
- `Phase 8` 除基础绩效外，还要产出 run manifest 或等价元数据，保证结果可复现
- `Phase 9` 除对账和保护模式外，还要明确 `paper` 模式的对账真相源、保护模式进入后的挂单处理，以及按 `time range / trader_run_id / account_id / symbol` 回放的最小入口
- 所有交付都必须按 `testing-standards.md` 中的测试汇报格式逐项输出，不能只写“已测试”或“测试通过”

建议验收输出：

- 已修改文件
- 已完成能力
- 测试情况：
  - 已运行哪些测试
  - 哪些通过
  - 哪些未运行
  - 为什么未运行
  - 当前剩余测试风险
- 未完成项
- 风险与待确认点
- 是否可以进入下一阶段

补充文档：

- [工程模板与技术栈固定决策](./implementation-decisions.md)
