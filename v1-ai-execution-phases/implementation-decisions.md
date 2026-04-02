# V1 工程模板与技术栈固定决策

这份文档用于把 V1 在“如何落代码”这一层再固定一遍，避免后续 AI 在工程模板、依赖选择和基础实现风格上反复猜测。

如果本文件与历史架构草案存在冲突，以本文件和 `00-master-plan.md` 为准。

---

## 1. 当前固定技术栈

V1 默认采用下面这套技术栈：

- 语言：`Python 3.12`
- 依赖与虚拟环境：`uv`
- API：`FastAPI`
- 配置与数据校验：`Pydantic v2 + pydantic-settings`
- 数据库访问：`SQLAlchemy 2.0`
- Migration：`Alembic`
- PostgreSQL 驱动：`psycopg 3`
- HTTP 客户端：`httpx`
- 重试：`tenacity`
- 结构化日志：`structlog + logging`
- 测试：`pytest + pytest-asyncio`
- 并发模型：标准 `asyncio`

V1 当前不默认引入：

- `Django`
- `Celery`
- `Redis` 作为必选依赖
- `Kafka`
- `Prometheus / Grafana`
- `mypy` 作为阻塞门槛

说明：

- 如果后续 phase 需要新增库，优先在现有栈上补齐，不要轻易换框架
- 如果某个能力可以直接通过 `FastAPI / Pydantic / SQLAlchemy / asyncio` 完成，不应额外引入同类重型框架

---

## 2. 当前固定业务默认值

除非在 `Phase 0` 中被明确重新固定，否则 V1 默认采用下面的业务基线：

- 市场边界：`cn_equity`
- 市场类型：`a_share`
- 执行模式：`paper`
- 账户标识：`paper_account_001`
- 主策略：`baseline_momentum_v1`
- 默认股票标的：`600036.SH`、`000001.SZ`
- 默认主周期：`15m`
- 运行环境：`dev`
- 交易时区：`Asia/Shanghai`
- 时间标准：交易、存储和日志统一使用 `Asia/Shanghai`
- 市场输入边界：`Bar`
- 策略触发边界：`closed_bar`
- 执行方向：A 股 `long-only` 普通股票，不做融资融券 / 做空 / 当日回转卖出
- 默认订单有效期：`DAY`

说明：

- `Phase 0` 固定后的 V1 运行范围为 `cn_equity + a_share + paper + paper_account_001 + baseline_momentum_v1 + 15m + closed_bar`
- `600036.SH`、`000001.SZ` 是 V1 唯一支持的 symbol 边界，`dev` profile 默认只激活 `600036.SH`
- `trading.exchange` 字段保留为统一市场边界标识，固定值为 `cn_equity`；具体上市 venue 继续编码在 symbol 后缀中，例如 `.SH` / `.SZ`
- 每个支持 symbol 都必须显式配置 A 股交易规则，至少包含 `lot_size`、`qty_step`、`price_tick`、`min_qty`、`allow_odd_lot_sell`、`t_plus_one_sell`、`price_limit_pct`
- `order_type = MARKET` 仅表示 paper execution 下的市价风格指令，不应被实现成“交易所原生市场单一定存在”的假设；V1 默认策略下单路径不要求启用 `LIMIT`
- 如果后续确实要启用 `LIMIT`、涨跌停检查或交易时段检查，运行时还必须提供最小 market state 输入，例如 `trade_date`、`previous_close`、`upper_limit_price`、`lower_limit_price`、`trading_phase`、`suspension_status`
- 这些值是当前 V1 的固定边界；如果后续确实要改，必须显式更新 phase 文档和配置契约，而不是在实现时临时漂移

---

## 3. 当前固定工程模板

仓库根目录默认采用下面结构：

```text
apps/
  api/
  trader/
  collector/
  research/

configs/
migrations/

src/
  config/
  domain/
    events/
    strategy/
    risk/
    portfolio/
    execution/
    reconciliation/
  infra/
    db/
    exchanges/
    messaging/
    observability/
  services/
    backtest/
  shared/

tests/
  unit/
  integration/
  e2e/
```

入口约定：

- `apps/api/main.py`
- `apps/trader/main.py`
- `apps/collector/main.py`

说明：

- 当前入口文件只需要提供最小可运行骨架或占位
- 具体业务实现仍按 phase 顺序进入对应目录

---

## 4. 配置与 Secret 契约

V1 默认采用：

- `.env` / 环境变量 作为运行时必填 secret 的注入方式
- `configs/base.yaml` 和 `configs/dev.yaml` 作为配置结构模板和后续 profile 分层入口
- `src/config/settings.py` 中的 `get_settings()` 作为进程内统一配置入口

加载顺序固定为：

- `configs/base.yaml`
- `configs/dev.yaml`
- `.env`
- 进程环境变量

Secret 原则：

- 数据库连接串、Telegram token/chat id 等 secret 只放环境变量
- 不把 secret 写进版本库内的 YAML

配置原则：

- 缺失关键配置时应启动即失败
- `paper` 是唯一允许的执行模式
- `1-3` 个 symbol 是固定边界，不允许悄悄扩到更多
- `time_in_force` 虽可保留字段，但 V1 A 股语义固定为 `DAY`
- symbol 交易规则必须显式配置，不允许在运行时对 `lot_size / tick / T+1 / odd-lot sell / price limit` 做静默兜底
- 如果策略下单路径保留 `LIMIT`、涨跌停或交易时段检查，最小 market state 契约也必须显式固定，不允许在缺失 `previous_close / price band / trading_phase / suspension` 信息时静默放行
- paper execution 与 backtest 共享的成本模型至少包含 `commission`、`transfer_fee`、`stamp_duty_sell`；不允许先把成交成本隐式固定为 `0`，再到 `Phase 8` 才第一次补上
- `SIGNALARK_POSTGRES_DSN` 是当前 Phase 0 唯一必填 secret 契约
- `SIGNALARK_TELEGRAM_BOT_TOKEN` 与 `SIGNALARK_TELEGRAM_CHAT_ID` 只在启用 Telegram 告警时变为必填

---

## 5. 数据库与持久化基线

V1 默认采用：

- 数据库：`PostgreSQL`
- ORM / query layer：`SQLAlchemy 2.0`
- migration：`Alembic`

持久化基线：

- `paper` 模式下，本地持久化状态是唯一可恢复事实源
- 当前 V1 的本地持久化基线固定为项目内使用的 `PostgreSQL` 契约
- `orders / fills / positions / balance_snapshots` 是恢复主线
- 关键事实需要能关联 `trader_run_id`

---

## 6. 可观测性基线

V1 默认采用：

- 控制面以 `FastAPI` 暴露最小 API
- 日志以 JSON 风格结构化日志为主
- 告警先接 `Telegram`

V1 当前不追求：

- 完整 dashboard
- 指标平台化
- tracing 平台

### 6.1 控制台刷新传输基线

V1 控制台当前固定采用：

- 前端通过 `REST polling` 获取状态、持仓、订单、事件和市场只读快照
- 默认轮询间隔保持在 `15s`
- 同时保留手动刷新入口

当前明确不在 V1 中引入：

- `WebSocket`
- `SSE`

原因固定为：

- 当前控制台读取的是少量粗粒度快照，而不是高频增量流
- 操作面核心需求仍是“值守、复核、人工控制”，不是毫秒级盘中推送
- 当前后端还没有为浏览器维护长连接、订阅生命周期、回放位点和断线恢复的额外复杂度预留专门边界
- 现有 `REST + 分区级容错 + 手动刷新` 已足够覆盖 V1 操作面需求

后续只有在满足下列任一条件时，才重新评估推送式刷新：

- 操作员要求明显低于 `15s` 的状态可见延迟
- 事件时间线需要持续追加，而不是整段重新拉取
- 需要把盘中监控做成接近实时的长时间盯盘视图
- 前端开始消费更高频、更细粒度的 runtime / diagnostics / alert 数据

如果未来需要升级传输方式，默认优先顺序固定为：

1. 先评估 `SSE`
2. 只有在需要双向订阅协商、浏览器主动回传流控或更复杂会话语义时，再评估 `WebSocket`

原因：

- 当前控制台的数据流主要是服务端单向推送到浏览器
- `SSE` 更贴合状态流、事件流和告警流这类 append-only 视图
- 在保留现有 REST 控制动作的前提下，引入 `SSE` 的改动面通常比 `WebSocket` 更小

---

## 7. 测试与质量基线

V1 默认采用：

- `pytest tests/unit -q`
- `pytest tests/integration -q`
- `pytest tests/e2e -q`
- `ruff check .`
- `ruff format .`

质量原则：

- 优先保证核心交易语义的稳定，而不是追求覆盖率数字
- 如果环境缺少 PostgreSQL 或外部依赖，允许先交付单元测试，但必须显式说明验证缺口

---

## 8. Phase 6 默认参数基线

如果 `Phase 6` 中没有额外配置覆盖，建议默认采用：

- `risk.max_single_symbol_notional_cny = 200000`
- `risk.max_total_open_notional_cny = 500000`
- `risk.min_order_notional_cny = 1000`
- `risk.market_stale_threshold_seconds = 120`
- `controls.lease_ttl_seconds = 15`
- `controls.lease_heartbeat_interval_seconds = 5`
- `alerts.telegram.enabled = false`

这些值的目的不是拟合收益，而是先给 V1 一个保守、易解释的安全边界。

---

## 9. 当前非目标

在没有用户明确要求前，后续 AI 不应主动把工程模板扩成下面这些内容：

- 微服务拆分
- 多账户配置矩阵
- 完整权限系统
- 通用插件平台
- 实盘适配器
- 复杂部署编排
