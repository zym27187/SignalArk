# SignalArk 当前待办（重新评估版）

生成时间：2026-04-02

## 本次评估依据

- 本地执行 `.venv/bin/python -m pytest -q`：`127 passed in 2.48s`。
- 本地执行 `.venv/bin/python -m pytest --collect-only -q`：当前共收集 `127` 个测试。
- 本地执行 `.venv/bin/ruff check .`：通过。
- 本地执行 `make web-build`：通过。
- 本地检索 `apps/web` 自动化测试文件：当前没有 `*.test.*` / `*.spec.*`。
- 补充阅读了 `README.md`、`apps/research/README.md`、`apps/web/README.md`、`apps/trader/control_plane.py`、`migrations/README.md`、`tests/integration/test_api_market_endpoints.py`、`tests/integration/test_research_cli.py`、`apps/web/package.json`。

## 当前结论

- 当前仓库已经不处于“修红灯”阶段；后端测试、lint 和前端构建都已是绿灯。
- 旧 todo 里的大部分 P0 / P1 事项已经完成，不建议继续把“已完成项”放在主待办里。
- 当前 P0 已完成；接下来最值得做的是补前端测试基线，并继续修正文档漂移。

## P0：已完成

- [x] done：统一数据库 schema 的唯一来源到 Alembic。
  已完成内容：新增控制面表迁移，`trader_controls`、`trader_account_leases`、`trader_runtime_status` 现在由 Alembic 创建；`apps/trader/control_plane.py` 的 `ensure_schema()` 改为校验并在缺失迁移时明确报错，不再静默建表。

- [x] done：让集成 / E2E 初始化默认走真实 Alembic 迁移。
  已完成内容：新增共享 migration helper，集成 / smoke / E2E 相关测试默认通过 `alembic upgrade head` 初始化测试库；空库只读 API 测试也额外锁定了“不会因 service 初始化自动创建 control-plane 表”的行为。

## P1：下一步最值得补齐

- [ ] 给 `apps/web` 建立最小自动化测试基线，并接入 CI。
  现状：`apps/web/package.json` 只有 `dev`、`build`、`preview`、`check-types`，仓库里也没有前端测试文件。
  建议最小范围：先补 `src/lib/api.ts` 的数据适配、`use-market-data` / `use-dashboard-data` 的回退逻辑、symbol/timeframe 切换，以及 1 到 2 个关键视图渲染测试。

- [ ] 修正文档漂移，优先同步根 README 的 research 说明。
  现状：`README.md` 仍写“当前回测能力以 Python API 形式提供，而不是独立 CLI”，但 `apps/research/README.md`、`Makefile` 和 `tests/integration/test_research_cli.py` 已明确支持 `python -m apps.research` / `make research ARGS="..."`。
  建议结果：把根 README 的 research 章节、常用命令和输出说明更新到与现状一致；后续若控制面表迁入 Alembic，也一并改掉“运行时自动补齐控制面表”的描述。

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
