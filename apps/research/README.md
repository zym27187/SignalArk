# Research

`apps/research/` 当前提供的是一个最小可用的事件驱动回测入口，而不是占位目录。

它的目标是让研究侧复用交易主链路里的核心语义，做最小一致性验证，包括：

- 策略决策：复用 `build_strategy(...)`
- 下单规划：复用 signal -> order intent 的标准化逻辑
- 成交模拟：复用 `PaperExecutionAdapter`
- 持仓与余额：复用 portfolio ledger
- 成本模型：复用 `settings.paper_cost_model`
- A 股约束：复用 `symbol_rules`、T+1、印花税等规则

## 当前入口

主要入口在：

- `apps.research.build_default_backtest_runner(...)`
- `apps.research.ResearchBacktestRunner.run(...)`

对应实现位于：

- `apps/research/backtest.py`
- `src/services/backtest/service.py`

## 使用方式

当前没有单独的 CLI，建议直接通过 Python API 调用。

示例：

```python
from decimal import Decimal

from apps.research import build_default_backtest_runner
from src.config import get_settings

settings = get_settings()
runner = build_default_backtest_runner(
    settings,
    initial_cash=Decimal("100000"),
    slippage_bps=Decimal("5"),
)

result = await runner.run(bars)
```

其中 `bars` 需要是 `Iterable[BarEvent]`，并且应当满足：

- 至少包含一个 bar
- 按 `event_time` 升序排列
- 使用 final/closed bar

## 输出内容

`run(...)` 返回 `BacktestRunResult`，其中包含：

- `manifest`：本次回测的策略、数据集、成本假设摘要
- `performance`：收益率、回撤、成交次数等统计
- `decisions`：逐 bar 的策略与下单决策审计
- `signals`
- `order_intents`
- `orders`
- `fill_events`
- `equity_curve`
- `positions`
- `balance`

## 当前范围

当前 research 能力聚焦“和 trader 主链路保持语义一致”的最小回放，不包含：

- 训练平台
- 因子挖掘框架
- 参数搜索平台
- 在线推理
- 独立的研究数据库或实验管理系统

## 参考

一个完整可运行示例可以直接看：

- `tests/integration/test_research_backtest_runner.py`

如果你想了解完整系统上下文，回到仓库根目录的 `README.md`；如果你只关心最小回测入口，从这里开始就够了。
