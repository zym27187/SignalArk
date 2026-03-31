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
- 为后续 strategy / risk / OMS 链路预留清晰接入点

## 本次不要做

- 不引入 `Redis Streams`
- 不拆远程微服务
- 不实现复杂调度系统
- 不提前实现完整控制面

## 完成标准

- trader 能稳定消费标准事件
- 模块之间已通过统一事件流衔接
- 不依赖 Redis 也能跑通主链路

## 最低验证要求

- 至少有测试覆盖事件分发
- 至少有测试覆盖 trader 收到 bar 事件后的处理路径

## 本次交付时必须汇报

- 主循环如何启动
- 事件如何分发
- 后续 strategy / risk / OMS 的接入点在哪里

## 可直接复制给 AI 的执行提示词

```text
你现在负责本项目的 Phase 4：Trader 主循环与 Event Bus。

请先阅读：
- ./00-master-plan.md
- ./phase-4-trader-loop-and-event-bus.md
- ./phase-3-collector-and-market-gateway.md

本次只允许修改：
- apps/trader/
- src/infra/messaging/
- 与事件订阅分发直接相关的少量代码
- tests/unit/
- tests/integration/

本次必须完成：
- 建立 trader 主进程或等价入口
- 建立进程内 dispatcher 或 asyncio queue
- 建立事件订阅和处理机制
- 让 BarEvent 可以进入 trader
- 为 strategy / risk / OMS 预留清晰接入点

严格不要做：
- 不引入 Redis Streams
- 不拆远程微服务
- 不实现复杂调度系统

完成后请输出：
1. 已修改文件
2. 主循环启动方式
3. 事件分发机制
4. 测试结果
5. 是否可以进入 Phase 5
```
