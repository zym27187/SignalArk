# SignalArk Web Console

`apps/web/` 是面向 SignalArk 控制面的前端控制台骨架。

当前技术栈：

- `Vite`
- `React`
- `TypeScript`

当前页面已经预留并对接这些后端能力：

- `/v1/status`
- `/v1/positions`
- `/v1/orders/active`
- `/v1/market/bars`
- `/v1/portfolio/equity-curve`
- `/v1/diagnostics/replay-events`
- `/v1/controls/*`

## 快速开始

```bash
make web-install
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

## 当前定位

这是一个控制台骨架，不是最终视觉稿。它已经包含：

- 运行态总览 Hero
- 控制按钮区
- 持仓表
- 活动订单表
- 最近事件时间线
- 基础轮询刷新与分区错误处理
- 市场页与研究页的 symbol/timeframe 切换骨架

特别说明：

- 前端仍保留分区级容错；后端在空数据库上会为核心只读接口返回空结果
- 市场页优先读取真实 K 线与权益接口，若当前环境暂无足够数据则自动回退到本地 fixture
- 市场页与研究页会共享当前选中的 symbol，上下文在两种视图间切换时会保留
- 第一版采用 REST 轮询，不依赖 WebSocket 或 SSE
