# Phase 4：Trader 主循环与 Event Bus

这份文件用于 AI 单次执行 `Phase 4`。

## 本次目标

建立最小 trader 主循环，让标准事件可以在系统内流动并进入策略运行时。

## 前置依赖

- `Phase 1：事件模型与领域对象`
- `Phase 2：数据库与核心持久化`
- `Phase 3：Collector 与 Market Gateway`

## 必读上下文

- `./00-master-plan.md`
- `./testing-standards.md`
- `./phase-3-collector-and-market-gateway.md`

## 允许修改范围

- `apps/trader/`
- `src/infra/messaging/`
- `src/domain/events/` 中与订阅分发相关的少量代码
- `tests/unit/`
- `tests/integration/`

## 本次必须完成的任务

- 建立 trader 主进程或等价入口
- 建立进程内 dispatcher 或 `asyncio queue`
- 建立事件订阅和处理机制
- 让 `BarEvent` 可以被 trader 消费
- 让 trader 主循环具备清晰的启动、停止和退出边界
- 为后续 `health / readiness` 与单活保护预留运行状态接入点
- 为后续 strategy / risk / OMS 链路预留清晰接入点
- 在 trader 启动时生成 `trader_run_id`，并让日志上下文、运行状态和后续关键事件都能读取该值
- 在策略触发边界忽略重复或非 `final` 的 `BarEvent`

## 本次不要做

- 不引入 `Redis Streams`
- 不拆远程微服务
- 不实现复杂调度系统
- 不提前实现完整控制面

## 完成标准

- trader 能稳定消费标准事件
- 模块之间已通过统一事件流衔接
- 主循环生命周期边界清晰，便于后续控制面接管
- 不依赖 Redis 也能跑通主链路
- 当前运行中的 `trader_run_id` 已对后续审计、回放和控制面可见
- 重复或非 `final` 的 `BarEvent` 不会重复触发策略与下单路径

## 最低验证要求

- 至少有测试覆盖事件分发
- 至少有测试覆盖 trader 收到 bar 事件后的处理路径
- 至少验证一次主循环生命周期状态变化或等价运行状态暴露
- 至少验证一次重复或非 `final` bar 被忽略

## 本次交付时必须汇报

- 主循环如何启动
- 事件如何分发
- 运行状态和生命周期如何暴露给后续控制面
- `trader_run_id` 如何生成和向后传递
- 重复 / 非 `final` bar 在 trader 侧如何处理
- 后续 strategy / risk / OMS 的接入点在哪里

## 可直接复制给 AI 的执行提示词

```text
你现在负责本项目的 Phase 4：Trader 主循环与 Event Bus。

请先阅读：
- ./00-master-plan.md
- ./testing-standards.md
- ./phase-4-trader-loop-and-event-bus.md
- ./phase-3-collector-and-market-gateway.md

本次只允许修改：
- apps/trader/
- src/infra/messaging/
- src/domain/events/ 中与订阅分发相关的少量代码
- tests/unit/
- tests/integration/

本次必须完成：
- 建立 trader 主进程或等价入口
- 建立进程内 dispatcher 或 asyncio queue
- 建立事件订阅和处理机制
- 让 BarEvent 可以进入 trader
- 让主循环具备清晰的启动、停止和退出边界
- 为 health / readiness 与单活保护预留运行状态接入点
- 为 strategy / risk / OMS 预留清晰接入点
- 在 trader 启动时生成 trader_run_id，并接入日志上下文、运行状态和关键事件
- 在策略触发边界忽略重复或非 final 的 BarEvent

严格不要做：
- 不引入 Redis Streams
- 不拆远程微服务
- 不实现复杂调度系统

完成后请输出：
1. 已修改文件
2. 已完成能力
3. 主循环启动方式
4. 事件分发机制
5. 生命周期与运行状态接入点
6. trader_run_id 生成与传递方式
7. 重复 / 非 final bar 处理边界
8. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
9. 未解决风险
10. 是否可以进入 Phase 5
```
