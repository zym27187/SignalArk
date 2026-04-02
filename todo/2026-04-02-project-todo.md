# SignalArk 待完善清单

生成时间：2026-04-02

## 梳理依据

- 本地执行 `.venv/bin/python -m pytest -q`：共收集 122 个测试，当前有 9 个错误，其余 113 个通过。
- 本地执行 `.venv/bin/ruff check .`：通过。
- 本地执行 `npm --prefix apps/web run build`：通过。
- 补充阅读了 `README.md`、`apps/research/README.md`、`apps/web/README.md`、`migrations/env.py`、`apps/api/main.py`、`apps/web/src/components/views/*` 等关键文件。

## P0：建议优先处理

- [x] done：修复 Alembic URL 优先级问题：`migrations/env.py` 现在优先显式传入的 `sqlalchemy.url`，未显式传入时再回退到项目 settings，避免覆盖测试或命令行指定的临时库。

- [x] done：把迁移路径纳入稳定回归门禁：新增 `make test-migrations` 和 Alembic 临时库 smoke check，并把 `tests/smoke` 纳入 `make test-integration`。

- [x] done：改善空库启动体验：`/v1/positions`、`/v1/orders/active`、`/v1/diagnostics/replay-events` 在核心持久化表尚未迁移时会返回空结果，前端 README 说明也已同步更新。

## P1：下一阶段建议补齐的能力

- [x] done：给市场页接真实后端数据：已补 `/v1/market/bars` 和 `/v1/portfolio/equity-curve` 两个只读接口，市场页优先读取真实 API，并在空数据或接口暂时不可用时自动回退到 `researchSnapshotFixture`。

- [x] done：给研究页提供正式入口：本次选择补 `research CLI`。已新增 `python -m apps.research` / `make research ARGS="..."` 入口，支持读取 `BarEvent` JSON、执行回测、导出 `BacktestRunResult`，并可选导出前端友好的 research snapshot JSON。

- [x] done：支持前端的多标的/多视图切换：市场页与研究页现在共享当前选中的 `symbol` 上下文，研究页补齐了多标的 / 多周期 fixture 目录，市场页也支持 `15m / 1h` 切换并随之请求真实只读 API 或回退对应示例数据。

- [ ] 评估是否引入推送式刷新：`apps/web/README.md` 目前明确是 REST 轮询。对控制面来说这已经够用，但如果后续要做盘中监控、事件流和更细粒度的运行态反馈，可以规划 WebSocket 或 SSE。

## P2：工程化与交付质量

- [ ] 增加 CI：仓库根目录下暂时没有 `.github` 工作流。建议至少自动跑 `ruff`、`pytest` 和 `npm --prefix apps/web run build`，避免当前这种“本地能一眼看出的红灯”在提交后继续漂着。

- [ ] 给前端补自动化测试：`apps/web/` 下目前没有 `*.test.*` 或 `*.spec.*` 文件。建议先补最小的 API 适配、视图切换和关键组件渲染测试，避免页面结构和数据契约漂移。

- [ ] 评估把控制面表纳入 Alembic：现在 `apps/trader/control_plane.py` 通过 `Base.metadata.create_all(...)` 自动补齐 `trader_controls`、`trader_account_leases`、`trader_runtime_status`。这对本地开发方便，但长期看会带来“迁移脚本”和“运行时自建表”双轨并存的问题，建议后续统一到迁移体系里。

- [ ] 让更多集成/E2E 流程走真实迁移初始化，而不是直接 `Base.metadata.create_all(...)`：这样更容易提前发现 schema 漂移、约束缺失和初始化顺序问题。

## 不计入当前待办的范围项

- 真实券商接入
- 多账户
- 多市场数据源
- 多策略组合
- AI/ML 训练平台

上面这些在 `README.md` 和 `v1-ai-execution-phases/00-master-plan.md` 里都属于 V1 明确不做的范围，不建议混入当前修补清单。
