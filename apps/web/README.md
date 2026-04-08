# SignalArk Web Console

`apps/web/` 是面向 SignalArk 控制面的前端控制台骨架。

当前技术栈：

- `Vite`
- `React`
- `TypeScript`
- `Vitest + Testing Library`

当前页面已经预留并对接这些后端能力：

- `/v1/status`
- `/v1/positions`
- `/v1/orders/active`
- `/v1/orders/history`
- `/v1/fills/history`
- `/v1/market/bars`
- `/v1/portfolio/equity-curve`
- `/v1/diagnostics/replay-events`
- `/v1/research/snapshot`
- `/v1/controls/*`

## 快速开始

```bash
make web-install
make web-test
make web
```

默认会请求：

```text
http://127.0.0.1:8000
```

如果你的 API 地址不同，可以修改：

```bash
VITE_SIGNALARK_API_BASE_URL=http://127.0.0.1:8000
```

如果你想从仓库根目录同时启动 API 和前端：

```bash
make dev
```

如果你想把前端、API 和 trader 一起拉起来：

```bash
make up
```

`make up` 默认会给 trader 注入本地 fixture 行情，方便在没有 Eastmoney 实时链路时也能把控制台跑起来。

如果你只想先跑前端自动化测试：

```bash
make web-test
```

## 当前定位

这是一个控制台骨架，不是最终视觉稿。它已经包含：

- 运行态总览 Hero
- 控制按钮区
- 持仓表
- 活动订单表
- 历史订单表
- 历史成交表
- 执行 / 诊断共享筛选器
- 最近事件时间线
- 基础轮询刷新与分区错误处理
- 市场页与研究页的 symbol/timeframe 切换

特别说明：

- 前端仍保留分区级容错；后端在空数据库上会为核心只读接口返回空结果
- 运维页现在可以直接查看历史订单和历史成交；`symbol`、`trader_run_id`、时间窗与条数会联动事件回放，订单状态和 `order_id` 也已分别接入历史订单 / 历史成交筛选
- 市场页优先读取真实 K 线与权益接口，若当前环境暂无足够数据则自动回退到本地 fixture
- `/v1/portfolio/equity-curve` 当前固定表示“账户组合权益曲线”；会基于余额快照、全账户成交与多标的历史价格共同重建
- 研究页现在优先读取 `/v1/research/snapshot` 返回的真实 backtest snapshot，不再固定停留在本地 fixture 页面
- 市场页与研究页会共享当前选中的 symbol，上下文在两种视图间切换时会保留
- 当前已补最小前端测试基线：覆盖 API 请求适配、dashboard / market hook 容错回退、主视图切换与关键组件渲染
- 第一版控制台固定采用 `REST 轮询 + 手动刷新`，默认轮询间隔为 `15s`
- 当前结论是不在 V1 引入 WebSocket 或 SSE；如果后续需要更低延迟的盘中监控、追加式事件流或更细粒度 runtime 反馈，再重新评估
- 如果未来确实需要浏览器侧推送，默认先评估 `SSE`，只有出现明显双向会话需求时再考虑 `WebSocket`
