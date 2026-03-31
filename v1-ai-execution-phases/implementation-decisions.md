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

- 交易所：`binance`
- 市场类型：`spot`
- 执行模式：`paper`
- 账户标识：`paper_account_001`
- 主策略：`baseline_momentum_v1`
- 默认交易对：`BTCUSDT`、`ETHUSDT`
- 默认主周期：`15m`
- 运行环境：`dev`
- 时间标准：存储和日志统一使用 `UTC`

说明：

- 这些值是工程模板的默认值，不是未来不可变的产品真理
- 但在真正开始实现 `Phase 1` 及后续阶段前，应先在 `Phase 0` 中把它们固定下来，避免中途变更语义

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
- `src/config/settings.py` 作为进程内统一配置入口

Secret 原则：

- 数据库连接串、Telegram token/chat id 等 secret 只放环境变量
- 不把 secret 写进版本库内的 YAML

配置原则：

- 缺失关键配置时应启动即失败
- `paper` 是唯一允许的执行模式
- `1-3` 个 symbol 是固定边界，不允许悄悄扩到更多

---

## 5. 数据库与持久化基线

V1 默认采用：

- 数据库：`PostgreSQL`
- ORM / query layer：`SQLAlchemy 2.0`
- migration：`Alembic`

持久化基线：

- `paper` 模式下，`PostgreSQL` 是唯一可恢复事实源
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

- `risk.max_single_symbol_notional_usdt = 5000`
- `risk.max_total_open_notional_usdt = 10000`
- `risk.min_order_notional_usdt = 25`
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

