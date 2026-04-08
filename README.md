# SignalArk

SignalArk 是一个面向 A 股场景的事件驱动 `paper trading` 仓库。当前代码已经不再只是脚手架，而是具备了从行情采集、策略触发、风控、OMS、模拟成交、持久化、控制面 API、对账保护到最小研究回测的一条闭环。

项目当前聚焦 V1 固定边界：

- 市场：`cn_equity`
- 交易标的：`a_share`
- 执行模式：`paper`
- 主策略：`baseline_momentum_v1`
- 主周期：`15m`
- 触发方式：`closed_bar`
- 数据源：`eastmoney`
- 时区：`Asia/Shanghai`

## 当前已经实现的能力

- 行情采集：
  `Eastmoney` 历史 K 线拉取 + 轮询式实时 K 线流；只向下游输出去重后的 final/closed bar；支持 checkpoint、断线重连和缺口回补。
- Trader 运行时：
  内置 collector -> strategy -> risk -> OMS pipeline；只对唯一 final bar 触发策略；暴露 health/readiness/status 视图。
- 基线策略：
  内置 `baseline_momentum_v1`，根据相对昨收的阈值动量决定持仓目标；参数文件位于 `configs/strategies/baseline_momentum_v1.yaml`。
- 风控与 OMS：
  信号会被标准化为 order intent，再经过 A 股规则、市场状态、新开仓限制、重复意图、最小下单额、单标的/总敞口等预交易风控。
- 执行与持久化：
  内置确定性的 paper execution adapter；持久化 `signals`、`order_intents`、`orders`、`fills`、`positions`、`balance_snapshots`、`event_logs`。
- 控制面：
  提供 FastAPI API 查询运行状态、持仓、活动订单，并支持暂停策略、恢复策略、开启/关闭 kill switch、执行 cancel-all。
- 单活保护：
  同一账户使用 DB-backed lease + fencing token 做 single-active 保护，避免多个 trader 实例同时接管同一账户。
- 对账与保护模式：
  trader 启动时做恢复；随后定时重放 paper facts 对账。出现漂移或关键异常时会进入 `protection_mode`，并撤销非 `reduce_only` 活跃订单。
- 研究与回测：
  `apps/research` 暴露最小事件驱动回测 runner 和 research CLI，复用同一套 strategy、order plan、paper execution 和 portfolio ledger 语义。
- 可观测性：
  使用 `structlog` 输出 JSON 日志；日志和事件链路绑定 `trader_run_id`；可选 Telegram 告警。

## 系统结构

```text
Eastmoney bars
  -> Collector
  -> Trader runtime
  -> Strategy (baseline_momentum_v1)
  -> Pre-trade risk
  -> OMS
  -> Paper execution
  -> PostgreSQL persistence
  -> API / diagnostics / reconciliation / alerts
```

主目录说明：

- `apps/api/`：控制面 API，提供状态、订单、持仓、控制操作和审计事件回放
- `apps/trader/`：交易主运行时，串联 collector、strategy、risk、OMS、对账和保护逻辑
- `apps/collector/`：独立 collector 入口，便于单独观察行情采集行为
- `apps/research/`：研究与最小回测入口
- `src/domain/`：领域模型，包含 market、strategy、risk、execution、portfolio、reconciliation
- `src/infra/`：数据库、行情网关、消息总线、可观测性
- `configs/`：基础配置、开发配置和策略参数
- `migrations/`：Alembic 迁移
- `tests/`：单元、集成和 e2e 测试
- `v1-ai-execution-phases/`：V1 分阶段设计和执行文档

## 运行边界与默认约束

- 仅支持 A 股 `paper trading`，不包含真实券商接入。
- 支持标的固定为 `600036.SH` 和 `000001.SZ`。
- 运行时 `SIGNALARK_SYMBOLS` 只能是上述标的的 1 到 2 个子集。
- `symbol_rules` 和 `paper cost model` 固定从 `configs/base.yaml` 加载，并允许被更高优先级配置覆盖。
- 运行时唯一可恢复事实源是本地持久化状态，不依赖进程内内存态或 adapter 内部态。
- 控制面与 trader 都依赖数据库；默认 runtime 要求显式提供 `SIGNALARK_POSTGRES_DSN`。

## 快速开始

### 1. 安装依赖

仓库默认使用项目本地虚拟环境：

```bash
make install
make web-install
```

### 2. 准备运行配置

复制模板并填写本地环境变量：

```bash
cp .env.example .env
```

至少需要确认：

- `SIGNALARK_POSTGRES_DSN`
- `SIGNALARK_SYMBOLS`
- `SIGNALARK_LOG_LEVEL`

如果开启 Telegram 告警，还需要同时提供：

- `SIGNALARK_TELEGRAM_ENABLED=true`
- `SIGNALARK_TELEGRAM_BOT_TOKEN`
- `SIGNALARK_TELEGRAM_CHAT_ID`

### 3. 初始化数据库

先执行 Alembic 迁移创建核心交易表：

```bash
.venv/bin/alembic -c migrations/alembic.ini upgrade head
```

说明：

- 迁移负责创建核心持久化表和控制面表，如 `signals`、`orders`、`fills`、`positions`、`event_logs`、`trader_controls`、`trader_account_leases`、`trader_runtime_status`
- `trader` / API 启动前应先完成迁移；运行时不会再静默补表

### 4. 启动服务

启动 API：

```bash
make api
```

启动前端控制台：

```bash
make web
```

一条命令同时启动 API 和前端：

```bash
make dev
```

一条命令同时启动前端、API 和 trader：

```bash
make up
```

说明：

- `make dev` 会同时拉起 `http://127.0.0.1:8000` 和 `http://127.0.0.1:5173`
- `make up` 会在 `make dev` 的基础上额外拉起 `trader`
- 如果 `.env` 或进程环境里没有 `SIGNALARK_POSTGRES_DSN`，`make dev` 会先 fail-fast
- 如果前端依赖还没安装，`make dev` 会提示先执行 `make web-install`

启动 trader 主运行时：

```bash
make trader
```

`make trader` 已经内置 collector，不需要再额外启动一个 collector 才能交易。

如果你只想单独观察 Eastmoney K 线采集和 checkpoint 行为，可以单独运行：

```bash
make collector
```

## 常用命令

```bash
make install
make format
make lint
make test
make test-unit
make test-integration
make test-e2e
make api
make web
make web-test
make web-build
make web-preview
make web-install
make dev
make up
make trader
make collector
.venv/bin/python -m apps.research --input ./bars.json --output ./artifacts/backtest-result.json
make research ARGS="--input ./bars.json --output ./artifacts/backtest-result.json"
.venv/bin/python -m apps.mcp
make mcp
.venv/bin/alembic -c migrations/alembic.ini upgrade head
.venv/bin/python scripts/replay_events.py --limit 50
```

## API 概览

默认 API 地址为 `http://127.0.0.1:8000`。

| Method | Path | 说明 |
| --- | --- | --- |
| `GET` | `/` | 服务基础信息 |
| `GET` | `/health/live` | 进程存活和数据库连通性 |
| `GET` | `/health/ready` | readiness、lease、市场数据新鲜度 |
| `GET` | `/v1/status` | trader 状态、控制态、运行实例信息 |
| `GET` | `/v1/positions` | 当前持仓 |
| `GET` | `/v1/orders/active` | 当前活动订单 |
| `GET` | `/v1/orders/history` | 按 symbol / trader_run_id / 时间窗筛选历史订单 |
| `GET` | `/v1/fills/history` | 按 symbol / order_id / trader_run_id / 时间窗筛选历史成交 |
| `GET` | `/v1/market/bars` | 选中 symbol/timeframe 的历史 K 线快照 |
| `GET` | `/v1/market/runtime-bars` | trader runtime 实际看到 / 实际送入策略的 bar 审计快照 |
| `GET` | `/v1/portfolio/equity-curve` | 按选中周期重建的账户组合权益曲线 |
| `GET` | `/v1/diagnostics/replay-events` | 按时间、`trader_run_id`、账户、symbol 回放审计事件 |
| `GET` | `/v1/research/snapshot` | 基于真实历史 K 线即时生成 research 回测快照 |
| `POST` | `/v1/controls/strategy/pause` | 暂停策略触发 |
| `POST` | `/v1/controls/strategy/resume` | 恢复策略触发 |
| `POST` | `/v1/controls/kill-switch/enable` | 打开 kill switch，只允许减仓/平仓方向动作 |
| `POST` | `/v1/controls/kill-switch/disable` | 关闭 kill switch |
| `POST` | `/v1/controls/cancel-all` | 取消可取消的活动订单 |

几个常用示例：

```bash
curl http://127.0.0.1:8000/v1/status
curl http://127.0.0.1:8000/v1/orders/active
curl "http://127.0.0.1:8000/v1/orders/history?symbol=600036.SH&limit=20"
curl "http://127.0.0.1:8000/v1/fills/history?trader_run_id=<run-id>&limit=20"
curl "http://127.0.0.1:8000/v1/market/runtime-bars?symbol=600036.SH&timeframe=15m"
curl -X POST http://127.0.0.1:8000/v1/controls/strategy/pause
curl -X POST http://127.0.0.1:8000/v1/controls/kill-switch/enable
curl "http://127.0.0.1:8000/v1/diagnostics/replay-events?limit=50"
```

## MCP Server

仓库现在提供一个本地只读 MCP server，方便让 AI agent 直接查询当前 SignalArk 状态、历史执行结果和 research 快照，而不是手工查表或拼 curl。

启动方式：

```bash
.venv/bin/python -m apps.mcp
make mcp
```

如果你希望显式指定配置层或数据库连接，可以额外传：

```bash
make mcp ARGS="--config-profile dev --postgres-dsn postgresql+psycopg://signalark:signalark@localhost:5432/signalark"
```

当前暴露的工具：

- `get_status`
- `list_positions`
- `list_active_orders`
- `list_order_history`
- `list_fill_history`
- `replay_events`
- `get_market_bars`
- `run_research_snapshot`

设计约束：

- 当前只开放只读工具，不包含 pause / kill switch / cancel-all 之类控制动作。
- `get_market_bars` 和 `run_research_snapshot` 会走现有 Eastmoney 历史行情链路，因此依赖外部市场数据可用。
- 历史订单、成交和事件回放直接复用当前持久化表与控制面 service；若数据库尚未迁移或为空，会返回空结果而不是崩溃。

如果你要在支持 MCP 的客户端里注册它，可以把命令指向项目本地虚拟环境的 Python，例如：

```json
{
  "mcpServers": {
    "signalark": {
      "command": "/absolute/path/to/SignalArk/.venv/bin/python",
      "args": [
        "-m",
        "apps.mcp",
        "--config-profile",
        "dev",
        "--postgres-dsn",
        "postgresql+psycopg://signalark:signalark@localhost:5432/signalark"
      ],
      "cwd": "/absolute/path/to/SignalArk"
    }
  }
}
```

## 配置加载顺序

统一配置入口是 `src.config.get_settings()`，加载顺序固定为：

1. `configs/base.yaml`
2. `configs/<profile>.yaml`
3. `.env`
4. 进程环境变量

默认 profile 是 `dev`，可以通过以下变量覆盖：

- `SIGNALARK_CONFIG_PROFILE`
- `SIGNALARK_CONFIG_FILE`

几个高频配置项：

- `SIGNALARK_POSTGRES_DSN`：runtime 必填
- `SIGNALARK_SYMBOLS`：逗号分隔，如 `600036.SH,000001.SZ`
- `SIGNALARK_API_HOST`
- `SIGNALARK_API_PORT`
- `SIGNALARK_LOG_LEVEL`
- `SIGNALARK_LEASE_TTL_SECONDS`
- `SIGNALARK_LEASE_HEARTBEAT_INTERVAL_SECONDS`
- `SIGNALARK_MARKET_STALE_THRESHOLD_SECONDS`

## 回测与研究

当前回测能力同时提供 Python API、research CLI 和控制面 research snapshot API。典型入口是：

- `apps.research.build_default_backtest_runner(...)`
- `apps.research.ResearchBacktestRunner.run(...)`
- `python -m apps.research --input ...`
- `make research ARGS="--input ... --output ..."`
- `GET /v1/research/snapshot?symbol=...&timeframe=...&limit=...`

CLI 支持读取 `BarEvent` JSON、导出 `BacktestRunResult`，并可选导出前端研究页可直接消费的 web snapshot JSON。控制面 research API 则会直接拉取真实历史 K 线，现场生成一份与前端研究页契约对齐的 snapshot。

控制面市场视图中的 `/v1/portfolio/equity-curve` 现在固定表示“账户组合权益曲线”，而不是单一 symbol 的贡献曲线。它会基于 `balance_snapshots`、全账户 `fills` 和多标的历史价格共同重建整账户权益。

它复用了生产链路中的策略、order plan、paper execution 与持仓账本语义，适合做最小一致性验证。完整用法可以参考：

- `tests/integration/test_research_backtest_runner.py`
- `tests/integration/test_research_cli.py`
- `apps/research/README.md`

## 验证建议

推荐按下面顺序做最小验证：

1. `make test-unit`
2. `make test-integration`
3. `make test-e2e`
4. `make web-test`
5. 启动 `make trader`
6. 用 API 访问 `/v1/status`、`/v1/positions`、`/v1/orders/active`
7. 通过 `/v1/controls/*` 试运行 pause、kill switch、cancel-all

当前测试覆盖的重点包括：

- collector 的历史回补、重连和 final bar 去重
- trader 对唯一 final bar 的触发和运行时状态
- 单账户单活 lease 保护
- pre-trade risk 规则
- paper execution 与持仓/余额账本更新
- API 控制面和审计事件回放
- reconciliation 漂移检测、protection mode 进入与订单保护
- 研究回测最小闭环
- 前端 API 适配、hook 容错回退、主视图切换与关键组件渲染

## 相关文档

- `v1-ai-execution-phases/00-master-plan.md`
- `v1-ai-execution-phases/testing-standards.md`
- `v1-ai-execution-phases/implementation-decisions.md`
- `migrations/README.md`

如果你想了解当前系统“为什么这么设计”，优先看 `v1-ai-execution-phases/`；如果你想直接运行系统，优先看本 README。
