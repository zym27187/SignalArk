# Phase 3：Collector 与 Market Gateway

这份文件用于 AI 单次执行 `Phase 3`。

## 本次目标

把单一交易所的 bar 数据转成统一 `BarEvent`，为 trader 提供稳定输入。

## 前置依赖

- `Phase 1：事件模型与领域对象`
- `Phase 2：数据库与核心持久化`

## 必读上下文

- `./00-master-plan.md`
- `./testing-standards.md`
- `./phase-1-domain-model.md`
- `./phase-2-db-and-persistence.md`

## 允许修改范围

- `apps/collector/`
- `src/infra/exchanges/`
- `src/domain/events/` 中与 bar 事件适配有关的少量代码
- `src/domain/market/` 或等价目录
- `tests/unit/`
- `tests/integration/`

## 本次必须完成的任务

- 接入单一交易所的历史 K 线
- 接入单一交易所的实时 K 线或等价 bar 数据
- 统一 `symbol`、时区、精度
- 将外部数据标准化为 `BarEvent`
- 保留原始 payload 或最小原始记录
- 处理基本断线重连和补数逻辑

## 本次不要做

- 不实现 Tick
- 不实现 OrderBook
- 不接多交易所
- 不为了低延迟引入复杂消息中间件

## 完成标准

- 可以稳定采集并标准化 bar 数据
- collector 异常恢复后可以继续工作
- 关键事件可以写入本地日志或持久层

## 最低验证要求

- 至少有测试覆盖标准化逻辑
- 至少验证一次历史数据到 `BarEvent` 的转换
- 至少验证一次断线或重连后的恢复路径

## 本次交付时必须汇报

- 接入了哪个交易所和哪种 bar 数据
- `BarEvent` 是如何生成的
- 当前补数和恢复能力做到什么程度

## 可直接复制给 AI 的执行提示词

```text
你现在负责本项目的 Phase 3：Collector 与 Market Gateway。

请先阅读：
- ./00-master-plan.md
- ./phase-3-collector-and-market-gateway.md
- ./phase-1-domain-model.md
- ./phase-2-db-and-persistence.md

本次只允许修改：
- apps/collector/
- src/infra/exchanges/
- src/domain/market/ 或等价目录
- 与 BarEvent 标准化直接相关的少量代码
- tests/unit/
- tests/integration/

本次必须完成：
- 接入单一交易所的历史和实时 bar 数据
- 统一 symbol、时区、精度
- 标准化为 BarEvent
- 保留原始 payload 或最小原始记录
- 处理基本断线重连和补数

严格不要做：
- 不实现 Tick
- 不实现 OrderBook
- 不接多交易所
- 不引入复杂消息中间件

完成后请输出：
1. 已修改文件
2. 接入了什么市场数据
3. BarEvent 生成路径
4. 恢复/补数能力
5. 是否可以进入 Phase 4
```
