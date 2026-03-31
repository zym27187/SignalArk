# Phase 6A：Pre-Trade Risk Rules

这份文件用于把 `Phase 6` 进一步拆成更适合 AI 单次编码的子任务。

## 本次目标

先把最基础、最关键的 `pre-trade risk` 规则做出来，并接入统一下单闸门。

## 前置依赖

- `Phase 5：OMS 与 Paper Execution`

## 必读上下文

- `./00-master-plan.md`
- `./testing-standards.md`
- `./implementation-decisions.md`
- `./phase-6-risk-and-control-plane.md`
- `./phase-5-oms-and-paper-execution.md`

## 允许修改范围

- `src/domain/risk/`
- `apps/trader/`
- `tests/unit/`
- `tests/integration/`

## 本次必须完成的任务

- 实现最大仓位检查
- 实现最大名义价值检查
- 实现重复下单防护
- 实现行情过期检查
- 实现最小下单量和 A 股基础交易规则检查
- 在 `kill switch` 或 `protection mode` 下，拒绝新开仓 / 增仓，但允许减仓 / 平仓保护单通过统一风险闸门；如实现中保留 `reduce_only` 字段，它只作为兼容标记
- 让所有下单动作先经过统一风险闸门

## 本次不要做

- 不做 in-trade / post-trade 复杂风控
- 不做复杂自适应风控
- 不做完整控制面

## 规则默认定义

### 1. 仓位与名义价值检查

建议默认同时检查：

- 结果持仓名义价值：`abs(resulting_position_qty) * decision_price`
- 账户总开放名义价值：所有非零持仓的名义价值之和

默认拒绝条件：

- 单 symbol 结果持仓名义价值超过 `risk.max_single_symbol_notional_cny`
- 更新后账户总开放名义价值超过 `risk.max_total_open_notional_cny`
- `decision_price` 缺失、非法或非正数

### 2. 重复下单防护

建议默认采用两层保护：

1. `order_intents.idempotency_key` 唯一约束
2. 对 active 订单意图做近重复检查

近重复检查建议至少比较下面字段：

- `account_id`
- `symbol`
- `side`
- `order_type`
- `qty`
- `decision_price` 或 `price`
- 减仓 / 平仓保护标记（如果实现中保留 `reduce_only` 字段，则比较该字段）

如果相同组合在最近 `60s` 内已存在且状态仍为非终态，应拒绝为重复单。

### 3. 行情过期检查

如果不存在最近一根可接受的 `final / closed bar`，应直接拒单。

建议默认拒绝条件：

- 最新可用 final bar 不存在
- `now - latest_final_bar.event_time > max(2 * timeframe_seconds, risk.market_stale_threshold_seconds)`

如果实现里保留 `LIMIT` 单、涨跌停检查或交易时段检查，建议额外要求：

- 当前订单对应的最小 market state 可用，至少包含 `trade_date / previous_close / upper_limit_price / lower_limit_price / trading_phase / suspension_status`
- 缺失上述字段时，对需要这些上下文的校验路径直接拒单，不做静默放行

### 4. 最小下单量、余股与交易规则检查

在 V1 中，symbol 交易规则建议至少包含：

- `lot_size`
- `qty_step`
- `price_tick`
- `min_qty`
- `allow_odd_lot_sell`
- `t_plus_one_sell`
- `price_limit_pct`

默认处理原则：

- 缺少 symbol 规则时拒单，不做静默兜底
- `time_in_force` 固定为 `DAY`
- `risk.min_order_notional_cny` 只作为内部风控下限，不属于交易所规则
- 买单和标准卖单先按 `lot_size / qty_step / price_tick` 归一化 `qty / price`
- 当 `0 < sellable_qty < lot_size` 且 `allow_odd_lot_sell = true` 时，允许 `SELL qty == sellable_qty` 走一次性余股卖出例外
- 除余股卖出例外外，归一化后若 `qty < min_qty` 或不满足手数步进，应拒单
- 归一化后 `qty <= 0` 时拒单
- 卖单除满足归一化外，还必须满足 `qty <= sellable_qty`
- 归一化后订单名义价值低于 `risk.min_order_notional_cny` 时拒单
- `LIMIT` 单只有在最小 market state 可用时才允许；价格超出 A 股当日涨跌停边界时拒单
- 标的处于停牌状态时拒单
- V1 默认只支持连续竞价；集合竞价、盘后固定价格申报或当前 V1 不支持的交易阶段都应显式拒单

### 5. kill switch / protection mode 下的放行边界

在 `kill_switch` 或 `protection_mode` 下，只有下面动作仍可放行：

- 明确用于减仓或平仓的保护单；如果实现里保留 `reduce_only = true`，它只作为该语义的兼容标记
- `SELL` 且 `qty <= sellable_qty`，并且确实减少当前绝对持仓的订单

默认拒绝：

- 新开仓
- 增仓
- 所有 `BUY`
- 超过 `sellable_qty` 的卖单
- 会把绝对持仓从更小值推向更大值的订单

如果当前仓位为零，则所有会建立新方向敞口的订单都应被拒绝。

### 6. 风险拒绝原因格式

建议统一输出结构化结果，至少包含：

- `risk_decision`
- `reason_code`
- `reason_message`
- `rule_name`
- `details`

其中：

- `risk_decision` 建议固定为 `ALLOW / REJECT`
- `reason_code` 用稳定枚举，例如 `MAX_POSITION_EXCEEDED`、`MARKET_DATA_STALE`、`SELLABLE_QTY_EXCEEDED`、`PRICE_LIMIT_EXCEEDED`、`LIMIT_REQUIRES_MARKET_STATE`、`SECURITY_SUSPENDED`、`TRADING_SESSION_UNSUPPORTED`、`ODD_LOT_SELL_RULE_VIOLATION`
- `details` 建议为可序列化 JSON 对象，便于日志、告警和 API 透传

## 完成标准

- 风险规则能明确放行或拒绝
- 拒绝原因可解释
- trader 下单前已经过统一风控入口
- 控制状态与风控闸门的关系清晰：安全状态下只保留减仓 / 平仓路径

## 最低验证要求

- 至少有测试覆盖放行与拒绝
- 至少有测试覆盖重复单或过期行情
- 至少验证一次 `kill switch` 或 `protection mode` 下开仓被拒绝但减仓被放行
- 至少验证一次 A 股交易规则场景，例如 `T+1`、可卖数量不足、余股卖出、涨跌停价格、停牌、`LIMIT` 缺少 market state 或集合竞价拒单

## 本次交付时必须汇报

- 已实现哪些 pre-trade risk 规则
- 风险拒绝原因采用什么格式
- 在 `kill switch / protection mode` 下，哪些单会被拒绝，哪些单仍可放行
- 哪些 API、控制面或告警能力仍留给 `Phase 6B / 6C`

## 可直接复制给 AI 的执行提示词

```text
你现在负责本项目的 Phase 6A：Pre-Trade Risk Rules。

请先阅读：
- ./00-master-plan.md
- ./testing-standards.md
- ./implementation-decisions.md
- ./phase-6-risk-and-control-plane.md
- ./phase-6a-pretrade-risk-rules.md
- ./phase-5-oms-and-paper-execution.md

本次只允许修改：
- src/domain/risk/
- apps/trader/
- tests/unit/
- tests/integration/

本次必须完成：
- 实现最大仓位、最大名义价值、重复下单、行情过期、最小下单量，以及 A 股 `lot / tick / T+1 / sellable_qty / odd-lot sell / price limit / trading session / suspension / LIMIT requires market state` 等规则
- 在 kill switch 或 protection mode 下，拒绝新开仓 / 增仓，但允许减仓 / 平仓保护单通过统一风险闸门；如实现中保留 `reduce_only` 字段，它只作为兼容标记
- 让所有下单动作先经过统一风险闸门

严格不要做：
- 不做复杂自适应风控
- 不做完整控制面
- 不做 in-trade/post-trade 复杂规则

完成后请输出：
1. 已修改文件
2. 已完成能力
3. 已实现的风险规则
4. 风险拒绝原因格式
5. kill switch / protection mode 下的放行与拒绝边界
6. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
7. 未解决风险
8. 是否可以进入 Phase 6B
```
