# SignalArk

SignalArk 是一个面向个人项目的 `paper trading` V1 仓库。

当前仓库包含两部分内容：

- `v1-ai-execution-phases/`：按阶段拆分的 AI 执行说明
- 最小 Python 工程模板：为后续 `Phase 0 -> Phase 9` 落代码准备目录、依赖和入口骨架

## 基线技术栈

- Python `3.12`
- 项目默认通过仓库内 `.venv` 执行 Python、pytest、ruff 和 uvicorn
- `FastAPI` 作为控制面 API
- `Pydantic v2 + pydantic-settings` 作为配置与数据校验基础
- `SQLAlchemy 2.0 + Alembic + psycopg` 作为 PostgreSQL 持久化基线
- `structlog` 负责结构化日志
- `pytest` 负责单元、集成和 e2e 测试

详细约定见：

- `v1-ai-execution-phases/implementation-decisions.md`

## 当前目录骨架

```text
apps/
  api/
  trader/
  collector/
  research/
configs/
migrations/
src/
tests/
v1-ai-execution-phases/
```

## 推荐起步方式

1. 先阅读 `v1-ai-execution-phases/00-master-plan.md`
2. 再阅读 `v1-ai-execution-phases/testing-standards.md`
3. 再阅读 `v1-ai-execution-phases/implementation-decisions.md`
4. 复制 `.env.example` 为本地 `.env`
5. 执行 `make install`，在仓库内创建 `.venv` 并安装依赖
6. 从 `Phase 0` 开始落代码

如果你在 VS Code 中打开本仓库，工作区会默认使用 `${workspaceFolder}/.venv/bin/python` 作为解释器，并在新终端中自动激活该环境。

## Phase 0 配置约定

- 统一配置入口固定为 `src.config.get_settings()`
- 加载顺序固定为 `configs/base.yaml -> configs/dev.yaml -> .env -> 进程环境变量`
- V1 范围固定为 `cn_equity + a_share + paper + paper_account_001 + baseline_momentum_v1 + 15m + closed_bar`
- V1 支持的股票标的固定为 `600036.SH`、`000001.SZ`，`dev` 默认只激活 `600036.SH`
- 市场数据源固定为 `eastmoney`
- `configs/base.yaml` 固定了每个支持 symbol 的 A 股交易规则：`lot_size / qty_step / price_tick / min_qty / allow_odd_lot_sell / t_plus_one_sell / price_limit_pct`
- `configs/base.yaml` 固定了 paper 成本模型：`commission / transfer_fee / stamp_duty_sell`
- 交易、存储和日志统一使用 `Asia/Shanghai` 时间标准
- `paper` 模式下唯一可恢复事实源是本地持久化状态；Phase 0 先固定为项目本地 PostgreSQL 持久化契约，不把内存态或 paper adapter 内部态视为恢复依据
- `trader_run_id` 约定由 trader 启动时生成 `uuid4`，并以 `trader_run_id` 字段绑定到结构化日志上下文和后续审计链路
- 启动前必须提供 `SIGNALARK_POSTGRES_DSN`；`SIGNALARK_TELEGRAM_BOT_TOKEN` 和 `SIGNALARK_TELEGRAM_CHAT_ID` 只有在 `SIGNALARK_TELEGRAM_ENABLED=true` 时才是必填 secret

## 最小验证

- `make test-unit`：覆盖 `Settings` 基础校验，以及 `load_settings()` / `get_settings()` 的配置加载与缓存行为
- `SIGNALARK_POSTGRES_DSN=... make trader`：输出带 `trader_run_id` 的结构化启动日志
- `make api`：启动最小 FastAPI 控制面骨架
- 未提供 `SIGNALARK_POSTGRES_DSN` 时，运行时会在启动阶段 fail-fast

## 常用命令

```bash
make install
make lint
make format
make test-unit
make api
SIGNALARK_POSTGRES_DSN=postgresql+psycopg://signalark:signalark@localhost:5432/signalark make trader
```

## 说明

- 现在的 `apps/api/main.py`、`apps/trader/main.py`、`apps/collector/main.py` 仅提供最小入口骨架
- 真正的交易语义、数据库、控制面和风控仍应按 phase 文档顺序实现
