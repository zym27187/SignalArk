# Phase 0：范围与配置骨架

这份文件用于 AI 单次执行 `Phase 0`。

## 本次目标

固定 V1 的业务边界、运行模式和基础配置骨架，让后续实现不再朝“通用平台”扩散。

## 前置依赖

- 无

## 必读上下文

- `./00-master-plan.md`
- `./testing-standards.md`
- `./implementation-decisions.md`
- `../archive/ai-quant-trading-architecture.md`

## 允许修改范围

- `configs/`
- `src/config/`
- `src/shared/` 中少量与配置直接相关的代码
- 根目录的 `.env.example` 或等价环境变量样例文件
- 范围说明文档
- `README.md` 中与启动配置直接相关的少量内容

## 本次必须完成的任务

- 固定市场数据源、市场类型、股票标的、周期、运行模式，以及 A 股执行边界
- 明确 `paper trading` 是 V1 唯一执行模式
- 建立基础配置结构，例如 `base`、`dev`
- 建立环境变量读取或等价设置方式
- 明确关键配置与 secret 的必填/选填契约，例如 `.env.example` 或等价说明
- 对关键配置做 fail-fast 校验，缺失或非法时启动即报错
- 建立最小日志配置
- 写清楚最小运行单元共用的配置入口约定
- 写清楚默认边界：单市场数据源、单账户、单策略、Bar 驱动
- 写清楚每个支持 symbol 的 A 股交易规则配置约定，例如 `lot_size / qty_step / price_tick / min_qty / allow_odd_lot_sell / t_plus_one_sell / price_limit_pct`
- 写清楚用于 A 股价格边界、交易时段和停牌判断的最小 market state 输入契约，例如 `trade_date / previous_close / upper_limit_price / lower_limit_price / trading_phase / suspension_status`
- 写清楚 paper 模式的最小成本模型配置约定，例如 `commission / transfer_fee / stamp_duty_sell`
- 写清楚 `paper` 模式下本地持久化状态是唯一可恢复事实源，内存状态只作为运行缓存
- 写清楚 `trader_run_id` 会在 trader 启动时生成，并进入日志 / 审计上下文

## 本次不要做

- 不接交易所 API
- 不建立数据库表
- 不定义完整策略实现
- 不实现 trader 主循环
- 不引入 Redis、消息系统、监控平台

## 完成标准

- 项目中已经存在清晰的配置骨架
- V1 范围被固定在配置或文档中
- 必填配置、缺省策略和 secret 契约已经明确
- 缺失关键配置时会明确失败而不是静默使用错误值
- 后续 AI 不需要再猜“第一版到底做多大”
- `paper` 模式事实源边界和运行时标识约定已经明确

## 最低验证要求

- 能成功读取配置
- 配置项有默认值或明确缺省策略
- 缺失关键配置时有明确报错或校验失败
- 至少有 1 个简单测试覆盖配置加载

## Phase 0 固定结果

- 市场边界固定为 `cn_equity`
- 市场类型固定为 `a_share`
- 执行模式固定为 `paper`
- 执行方向固定为 A 股 `long-only` 普通股票；V1 不做融资融券，不支持当日买入当日卖出
- 账户固定为 `paper_account_001`
- 主策略固定为 `baseline_momentum_v1`
- V1 支持股票标的固定为 `600036.SH`、`000001.SZ`，`dev` 默认只激活 `600036.SH`
- 主周期固定为 `15m`
- `time_in_force` 固定为 `DAY`
- `order_type = MARKET` 仅表示 paper execution 下的市价风格指令，不预设交易所原生市价单一定可用；V1 默认策略下单路径固定为连续竞价时段的 `MARKET` 风格指令
- 如果后续要启用 `LIMIT`，必须同时具备用于价格有效性、涨跌停和交易时段校验的最小 market state 契约；缺失这些输入时不允许静默放开 `LIMIT`
- 每个支持 symbol 都必须在配置中声明 A 股交易规则，至少包含 `lot_size / qty_step / price_tick / min_qty / allow_odd_lot_sell / t_plus_one_sell / price_limit_pct`
- `risk.min_order_notional_cny` 属于内部风控配置，不属于 A 股 symbol trading rules
- A 股运行时 market state 至少要能表达 `trade_date / previous_close / upper_limit_price / lower_limit_price / trading_phase / suspension_status`
- paper 模式成本模型至少包含 `commission / transfer_fee / stamp_duty_sell`
- 交易、存储与日志统一使用 `Asia/Shanghai` 时间标准
- 市场输入边界固定为 `Bar`，策略触发边界固定为 `closed_bar`
- 最小运行单元的共用配置入口固定为 `src.config.get_settings()`
- 配置加载顺序固定为 `configs/base.yaml -> configs/dev.yaml -> .env -> 进程环境变量`
- `paper` 模式下只有本地持久化状态可以作为恢复依据；交易所、内存缓存、paper adapter 内部态都不是可恢复事实源
- `trader_run_id` 约定为 trader 启动时生成 `uuid4`，日志和后续审计事实必须统一使用字段名 `trader_run_id`

## env / secret 契约

- `SIGNALARK_POSTGRES_DSN`：必填，代表 V1 paper 模式的本地持久化事实源连接契约
- `SIGNALARK_TELEGRAM_ENABLED`：可选，默认 `false`
- `SIGNALARK_TELEGRAM_BOT_TOKEN`、`SIGNALARK_TELEGRAM_CHAT_ID`：默认可选；当 `SIGNALARK_TELEGRAM_ENABLED=true` 时必须同时提供
- 市场边界、市场类型、执行模式、账户、主策略、周期等 V1 固定边界允许出现在 `.env.example` 中，但不应在 Phase 0 中被改成别的语义

## 本次交付时必须汇报

- 新增或修改了哪些配置文件
- V1 范围是如何被固定下来的
- 哪些 env / secret 为必填，哪些可选
- `paper` 模式事实源和 `trader_run_id` 约定是如何固定下来的
- 还有哪些决策仍需人工确认

## 可直接复制给 AI 的执行提示词

```text
你现在负责本项目的 Phase 0：范围与配置骨架。

请先阅读：
- ./00-master-plan.md
- ./testing-standards.md
- ./implementation-decisions.md
- ./phase-0-scope-and-config.md
- ../archive/ai-quant-trading-architecture.md

本次只允许修改：
- configs/
- src/config/
- src/shared/ 中与配置直接相关的少量代码
- 根目录的 .env.example 或等价环境变量样例文件
- 范围说明文档
- README.md 中与启动配置直接相关的少量内容

本次必须完成：
- 固定市场数据源、市场类型、股票标的、周期、运行模式，以及 A 股执行边界
- 明确 V1 只做 paper trading
- 建立基础配置结构和最小日志配置
- 明确关键配置和 secret 的必填/选填契约
- 对关键配置做 fail-fast 校验
- 写清楚最小运行单元共用的配置入口约定
- 把单市场数据源、单账户、单策略、Bar 驱动边界写清楚
- 写清楚每个支持 symbol 的 A 股交易规则配置约定，以及 `DAY / T+1 / price limit` 等固定执行边界
- 写清楚 paper 模式下本地持久化状态是唯一可恢复事实源
- 写清楚 trader_run_id 的生成和日志 / 审计接入约定

严格不要做：
- 不接交易所
- 不建数据库表
- 不实现策略逻辑

完成后请输出：
1. 已修改文件
2. 已完成能力
3. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
4. env / secret 契约说明
5. paper 模式事实源与运行时标识约定
6. 未解决风险
7. 是否可以进入 Phase 1
```
