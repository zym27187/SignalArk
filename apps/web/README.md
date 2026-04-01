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
- `/v1/diagnostics/replay-events`
- `/v1/controls/*`

## 快速开始

```bash
cd apps/web
cp .env.example .env.local
npm install
npm run dev
```

默认会请求：

```text
http://127.0.0.1:8000
```

如果你的 API 地址不同，可以修改：

```bash
VITE_SIGNALARK_API_BASE_URL=http://127.0.0.1:8000
```

## 当前定位

这是一个控制台骨架，不是最终视觉稿。它已经包含：

- 运行态总览 Hero
- 控制按钮区
- 持仓表
- 活动订单表
- 最近事件时间线
- 基础轮询刷新与分区错误处理

特别说明：

- 当前后端某些读接口在空数据库上可能返回错误，因此前端做了分区级容错
- 第一版采用 REST 轮询，不依赖 WebSocket 或 SSE

