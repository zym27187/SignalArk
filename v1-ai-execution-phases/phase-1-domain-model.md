# Phase 1：事件模型与领域对象

这份文件用于 AI 单次执行 `Phase 1`。

## 本次目标

定义 V1 统一交易语义，让 collector、trader、paper execution、backtest 可以共用同一套核心对象。

## 前置依赖

- `Phase 0：范围与配置骨架`

## 必读上下文

- `./00-master-plan.md`
- `./testing-standards.md`
- `../archive/ai-quant-trading-architecture.md`

## 允许修改范围

- `src/domain/events/`
- `src/domain/strategy/`
- `src/domain/execution/`
- `src/domain/portfolio/`
- `src/shared/` 中与基础类型相关的少量代码
- `tests/unit/`

## 本次必须完成的任务

- 定义 `BarEvent`
- 定义 `Signal`
- 定义 `OrderIntent`
- 定义 `Order`
- 定义 `Fill`
- 定义 `Position`
- 定义 `BalanceSnapshot`
- 定义统一时间字段和 ID 字段
- 定义订单状态枚举和流转规则
- 明确 `Signal` 与订单的边界
- 明确 `Signal.target_position` 和 `OrderIntent.qty` 的单位与语义，固定 sizing contract
- 明确 `BarEvent` 的时间窗口、稳定唯一键和 `closed / final` 语义

## 本次不要做

- 不接数据库
- 不写交易所适配器
- 不实现真实执行逻辑
- 不引入 `TickEvent` 和 `OrderBookEvent`

## 完成标准

- 所有核心对象拥有稳定 schema
- `OrderIntent` 和 `Order` 区分清楚
- 订单状态机有清晰定义
- `Signal` 到下单量的语义转换已经固定，不需要后续阶段再猜字段含义
- `BarEvent` 的 finality 和去重语义已经固定，不需要后续阶段再猜

## 最低验证要求

- 至少有单元测试覆盖订单状态机
- 至少有单元测试覆盖核心对象构造或校验

## 本次交付时必须汇报

- 定义了哪些核心对象
- 哪些字段被定为必填
- `BarEvent` 的时间窗口、唯一键和 finality 语义是什么
- `target_position / qty / price` 的语义分别是什么
- 订单状态流转规则是什么

## 可直接复制给 AI 的执行提示词

```text
你现在负责本项目的 Phase 1：事件模型与领域对象。

请先阅读：
- ./00-master-plan.md
- ./testing-standards.md
- ./phase-1-domain-model.md
- ./phase-0-scope-and-config.md
- ../archive/ai-quant-trading-architecture.md

本次只允许修改：
- src/domain/events/
- src/domain/strategy/
- src/domain/execution/
- src/domain/portfolio/
- src/shared/ 中与基础类型相关的少量代码
- tests/unit/

本次必须完成：
- 定义 BarEvent、Signal、OrderIntent、Order、Fill、Position、BalanceSnapshot
- 统一时间字段和 ID 字段
- 定义订单状态枚举和状态流转规则
- 明确 Signal 不是订单、OrderIntent 先于 Order
- 明确 Signal.target_position 与 OrderIntent.qty 的 sizing contract
- 明确 BarEvent 的时间窗口、唯一键和 closed/final 语义

严格不要做：
- 不接数据库
- 不接交易所
- 不实现真实执行逻辑
- 不引入 Tick / OrderBook

完成后请输出：
1. 已修改文件
2. 已完成能力
3. 新增的核心对象和字段
4. BarEvent 时间窗口 / 唯一键 / finality 语义说明
5. target_position / qty / price 语义说明
6. 订单状态机说明
7. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
8. 未解决风险
9. 是否可以进入 Phase 2
```
