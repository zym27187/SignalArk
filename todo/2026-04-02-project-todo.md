# SignalArk 当前待办（重新评估版）

生成时间：2026-04-02

## 本次评估依据

- 本地执行 `.venv/bin/python -m pytest -q`：`127 passed in 2.48s`。
- 本地执行 `.venv/bin/python -m pytest --collect-only -q`：当前共收集 `127` 个测试。
- 本地执行 `.venv/bin/ruff check .`：通过。
- 本地执行 `make web-test`：`5` 个前端测试文件、`9` 个测试通过。
- 本地执行 `make web-build`：通过。
- 补充阅读了 `README.md`、`apps/research/README.md`、`apps/web/README.md`、`apps/trader/control_plane.py`、`migrations/README.md`、`tests/integration/test_api_market_endpoints.py`、`tests/integration/test_research_cli.py`、`apps/web/package.json`。
- 本轮补充评估未重复跑全量测试，重点改为核对当前实现链路：`apps/api/main.py`、`apps/api/control_plane.py`、`apps/research/main.py`、`apps/research/backtest.py`、`apps/web/src/App.tsx`、`apps/web/src/components/views/ResearchView.tsx`、`apps/web/src/components/views/MarketView.tsx`、`apps/web/src/lib/research-fixtures.ts`、`apps/web/src/lib/api.ts`、`apps/web/src/hooks/use-dashboard-data.ts`、`apps/web/src/types/research.ts`。

## 当前结论

- 当前仓库已经不处于“修红灯”阶段；后端测试、lint 和前端构建都已是绿灯。
- 旧 todo 里的大部分 P0 / P1 事项已经完成，不建议继续把“已完成项”放在主待办里。
- 交易主链路已经闭环，但“研究页真实数据接入、组合权益语义、操作审计可见性”这三块仍然没有真正闭环。
- 当前更值得补的不是继续做脚手架，而是把已经存在的后端能力接成完整产品功能，减少 fixture、查库和语义漂移。

## 当前主待办：功能实现缺口

## P0：优先补齐闭环

- [x] done：接通 research 真数据链路，让研究页不再停留在 fixture 页面。
  已完成内容：新增 `/v1/research/snapshot`，后端会基于真实历史 K 线即时生成 backtest snapshot；前端新增 `useResearchData` 并改造 `ResearchView`，研究页现在优先消费真实 API 结果，不再直接读取本地 fixture。

- [x] done：修正 `/v1/portfolio/equity-curve` 的语义，避免多标的账户下曲线失真。
  已完成内容：接口现在按“全账户 `balance_snapshots` + 全账户 `fills` + 多标的历史价格”重建组合权益曲线，返回值显式补充了 `scope=account_portfolio`、`anchor_symbol`、`valuation_symbols`；前端市场页说明也已同步为“组合权益曲线”。

## P1：把可用后端能力变成可见功能

- [x] done：补齐 operator 侧的历史执行可见性：历史订单、成交、撤单结果。
  已完成内容：控制面已新增 `/v1/orders/history`、`/v1/fills/history`；前端运维页也已接入共享筛选器、历史订单表和历史成交表，支持按 `symbol`、`trader_run_id`、时间窗和条数查看执行结果，不再只能看活动订单或直查数据库。

- [x] done：给 diagnostics/replay-events 前端补筛选和定位能力。
  已完成内容：运维页已经接入共享活动筛选器，前端会把 `symbol`、`trader_run_id`、时间窗和 `limit` 同步传给 `fetchReplayEvents(...)`；事件回放现在和历史订单、历史成交共用同一组筛选上下文，可直接定位 protection mode、cancel-all 和对账相关事件。

- [x] done：清理 research snapshot 契约，把“真实导出仍标记为 fixture”的状态收口。
  已完成内容：`apps/research/snapshot.py` 与前端 `apps/web/src/types/research.ts` 现在统一支持 `fixture` / `imported` / `live` 三种来源；research CLI 导出的真实快照已改为 `sourceMode="imported"`，不再混用 fixture 语义。

## P2：增强审计一致性

- [x] done：给市场页补“runtime 实际消费数据”的审计视图，而不只是临时拉 Eastmoney 历史 K 线。
  已完成内容：runtime 状态已持久化每个 stream 的 `last seen bars` / `last strategy bars` 审计快照；后端新增 `/v1/market/runtime-bars`，前端市场页也已接入对应审计卡片，可直接看到 trader 实际看到和实际送入策略的 bar。

## P0：已完成

- [x] done：统一数据库 schema 的唯一来源到 Alembic。
  已完成内容：新增控制面表迁移，`trader_controls`、`trader_account_leases`、`trader_runtime_status` 现在由 Alembic 创建；`apps/trader/control_plane.py` 的 `ensure_schema()` 改为校验并在缺失迁移时明确报错，不再静默建表。

- [x] done：让集成 / E2E 初始化默认走真实 Alembic 迁移。
  已完成内容：新增共享 migration helper，集成 / smoke / E2E 相关测试默认通过 `alembic upgrade head` 初始化测试库；空库只读 API 测试也额外锁定了“不会因 service 初始化自动创建 control-plane 表”的行为。

## P1：已完成

- [x] done：给 `apps/web` 建立最小自动化测试基线，并接入 CI。
  已完成内容：补了 `Vitest + Testing Library` 测试栈，新增 API 请求适配测试、`use-market-data` / `use-dashboard-data` 容错回退测试、主视图切换测试，以及关键组件渲染测试；`make web-test` 与 CI `web` job 也已接入。

- [x] done：修正文档漂移，优先同步根 README 的 research 说明。
  已完成内容：根 README 已同步 research CLI、`make research`、`web-test`、前端测试覆盖范围，以及迁移后控制面表不再由运行时静默补齐的现状；`apps/web/README.md` 也补充了前端测试说明。

## 已完成且不再列为当前主待办

- Alembic URL 优先级修复。
- 迁移 smoke check 与 `make test-migrations` 补齐。
- 空库只读接口容错。
- 市场页真实数据接口接入与 fallback。
- research CLI 与 web snapshot 导出。
- 多标的 / 多视图切换。
- `REST polling + 手动刷新` 的 V1 决策固定。
- 基础 CI 搭建。

## 不计入当前待办的范围项

- 真实券商接入
- 多账户
- 多市场数据源
- 多策略组合
- AI / ML 训练平台

这些范围在 `README.md` 和 `v1-ai-execution-phases/00-master-plan.md` 里仍然属于 V1 明确不做的内容，不建议重新混入当前 todo。
