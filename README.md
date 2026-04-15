# SignalArk

SignalArk 是一个面向 A 股场景的事件驱动 `paper trading` 仓库。当前版本已经具备一条可运行的最小闭环：从行情采集、策略触发、风控与 OMS、模拟成交、持久化、控制面 API、前端控制台，到研究回测与诊断工具都已有可用实现。

如果你想先判断这个仓库“现在到底能做什么”，可以直接看下面这张功能地图。

## 功能地图

| 模块 | 当前已实现能力 | 入口 |
| --- | --- | --- |
| Trader 运行时 | 串联 `collector -> strategy -> risk -> OMS -> paper execution -> persistence`，只消费唯一 `final/closed bar`，支持恢复、对账和保护模式 | `make trader` |
| Market Data | 支持 `eastmoney` 和 `fixture` 数据源；collector 具备 checkpoint、断线重连、缺口回补、去重输出 | `make collector` |
| 控制面 API | 状态、readiness、订单、成交、持仓、账户摘要、行情、runtime bars、研究快照、事件回放、控制指令 | `make api` |
| Web 控制台 | 运行监控、账户与订单值守、行情核验、权益曲线、研究快照、规则回测、AI 研究设置 | `make web` / `make dev` / `make up` |
| Research | 最小事件驱动回测、参数扫描、walk-forward、规则回测、AI 研究快照 | `make research` / `/v1/research/*` |
| MCP Server | 面向诊断和研究流程的只读 MCP 工具集 | `make mcp` |

## 现在能直接体验到的功能

### 1. 一个可值守的 paper trader

- `apps/trader` 已经不是占位入口，而是完整运行时。
- 默认主链路会把行情事件送入策略、预交易风控、OMS、paper execution，再写入数据库。
- 支持 `pause`、`resume`、`kill switch`、`cancel-all` 这些操作控制。
- 同一账户有 DB-backed lease + fencing token 的单活保护，避免多个 trader 实例同时接管。
- trader 启动时会做恢复，运行中会定时重放 paper facts 做对账；发现严重漂移时会进入 `protection_mode`。

### 2. 可核验的行情采集和运行审计

- 支持 `eastmoney` 和 `fixture` 两种数据源，方便本地演示和联调。
- collector 只向下游输出去重后的 closed/final bar。
- API 能区分“现在重新拉取的市场数据”和“runtime 当时实际看到并用于决策的 bar”。
- 前端市场页可以把 K 线、账户权益曲线、runtime bar audit 和 degraded mode 诊断放在同一上下文里查看。

### 3. 面向操作和值守的控制面

- API 和前端可以查看 `status`、`readiness`、`control_state`、`lease`、`latest_final_bar_time` 等运行信息。
- 可以查看账户摘要、当前持仓、活动订单、订单流水、成交流水和事件时间线。
- 支持 symbol inspect，区分“输入过”“系统支持”“当前 runtime 已启用”三个层级。
- 支持 runtime symbol request，为运行范围调整提供显式记录入口。

### 4. 一个已经能用的研究面

- `apps/research` 复用了主交易链路里的策略、下单规划、paper execution、portfolio ledger 和成本模型语义。
- `GET /v1/research/snapshot` 支持四种模式：
  - `preview`
  - `evaluation`
  - `parameter_scan`
  - `walk_forward`
- `POST /v1/research/rule-snapshot` 已支持第一版可配置规则回测模板 `moving_average_band_v1`。
- `GET/PUT /v1/research/ai-settings` 和 `POST /v1/research/ai-snapshot` 已支持 AI 研究设置和 AI 研究快照。

### 5. 一个可直接联调的前端控制台

前端当前分成三个主视图：

- `Operations`：运行状态、控制指令、筛选器、标的检查、账户摘要、持仓、订单、成交、事件流。
- `Market`：价格主图、权益曲线、runtime 行情核验、degraded mode 诊断。
- `Research`：研究快照、回测指标、参数说明、决策明细、规则回测和 AI 研究入口。

### 6. 一个只读的 MCP 接口层

`apps/mcp` 当前提供 stdio MCP server，适合把仓库已有诊断与研究能力接到外部 agent/workflow 中。已覆盖的只读能力包括：

- 当前状态与共享契约
- 持仓、活动订单、订单历史、成交历史
- 审计事件回放
- 市场 bars 与 runtime bars
- 研究快照

## 默认边界

SignalArk 当前聚焦的是一个边界明确的 V1：

- 市场：A 股 `cn_equity`
- 执行模式：`paper`
- 主周期：`15m`
- 数据源：`eastmoney` 或 `fixture`
- 默认主策略：`baseline_momentum_v1`
- 运行时区：`Asia/Shanghai`

这意味着它现在适合本地演示、交易链路验证、控制面联调、研究快照和 paper trading 值守，不包含真实券商接入。

## 快速体验

### 方式一：直接用 Docker 拉起整套栈

如果你想最快看到已有功能，优先使用 Docker：

```bash
make docker-up
```

默认体验入口：

- 前端控制台：`http://127.0.0.1:5173`
- 前端会通过同源 `/api/...` 反向代理访问容器内 API

补充说明：

- Docker 默认读取仓库根目录的 `.env.docker`
- `.env.docker` 默认把 `SIGNALARK_MARKET_DATA_SOURCE` 设为 `fixture`
- 停止容器：`make docker-down`
- 查看日志：`make docker-logs`

### 方式二：本地虚拟环境运行

仓库默认使用项目本地 `.venv`。

1. 安装后端与前端依赖

```bash
make install
make web-install
```

2. 准备环境变量

```bash
cp .env.example .env
```

至少确认这些配置：

- `SIGNALARK_POSTGRES_DSN`
- `SIGNALARK_SYMBOLS`
- `SIGNALARK_LOG_LEVEL`

3. 初始化数据库

```bash
.venv/bin/alembic -c migrations/alembic.ini upgrade head
```

4. 启动服务

```bash
make dev
```

如果你想把 trader 一起拉起来：

```bash
make up
```

如果你只想本地演示控制台而不依赖 Eastmoney，可以显式使用 fixture：

```bash
SIGNALARK_MARKET_DATA_SOURCE=fixture make up
```

## 常用入口

```bash
make api
make web
make dev
make up
make trader
make collector
make research ARGS="--input ./bars.json --output ./artifacts/backtest-result.json"
make mcp
make test
make test-unit
make test-integration
make test-e2e
make docker-up
make docker-down
```

## 代表性 API

默认 API 地址为 `http://127.0.0.1:8000`。

| Method | Path | 用途 |
| --- | --- | --- |
| `GET` | `/health/live` | 进程和数据库基本存活检查 |
| `GET` | `/health/ready` | readiness、lease、行情 freshness |
| `GET` | `/v1/status` | trader 运行状态和控制态总览 |
| `GET` | `/v1/balance/summary` | 账户摘要 |
| `GET` | `/v1/positions` | 当前持仓 |
| `GET` | `/v1/orders/active` | 活动订单 |
| `GET` | `/v1/orders/history` | 订单历史 |
| `GET` | `/v1/fills/history` | 成交历史 |
| `GET` | `/v1/market/bars` | 读取市场 bars |
| `GET` | `/v1/market/runtime-bars` | 读取 runtime 实际记录的 bars |
| `GET` | `/v1/portfolio/equity-curve` | 账户权益曲线 |
| `GET` | `/v1/research/snapshot` | 标准研究快照 |
| `POST` | `/v1/research/rule-snapshot` | 规则回测快照 |
| `POST` | `/v1/research/ai-snapshot` | AI 研究快照 |
| `GET` | `/v1/diagnostics/replay-events` | 审计事件回放 |
| `POST` | `/v1/controls/strategy/pause` | 暂停自动策略 |
| `POST` | `/v1/controls/strategy/resume` | 恢复自动策略 |
| `POST` | `/v1/controls/kill-switch/enable` | 开启 kill switch |
| `POST` | `/v1/controls/kill-switch/disable` | 关闭 kill switch |
| `POST` | `/v1/controls/cancel-all` | 撤销当前活跃订单 |

## 目录速览

- `apps/trader/`：交易主运行时
- `apps/collector/`：行情采集入口
- `apps/api/`：控制面 API
- `apps/web/`：前端控制台
- `apps/research/`：研究与回测入口
- `apps/mcp/`：只读 MCP 服务
- `src/domain/`：领域模型、策略、风控、执行、组合与对账
- `src/infra/`：数据库、市场数据网关、可观测性
- `configs/`：基础配置、环境配置、策略参数
- `migrations/`：Alembic 迁移
- `tests/`：单元、集成、e2e 与 smoke 测试

## 一句话总结

这个仓库当前最有价值的地方，不是“准备以后做交易系统”，而是已经把 A 股 `paper trading` 的关键功能面做成了可运行、可观察、可回放、可研究、可控制的一套最小产品。
