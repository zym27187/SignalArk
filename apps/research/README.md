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
- `python -m apps.research --input ...`
- `make research ARGS="--input ..."`

对应实现位于：

- `apps/research/backtest.py`
- `apps/research/main.py`
- `apps/research/snapshot.py`
- `src/services/backtest/service.py`

## 使用方式

### 方式一：使用 research CLI

最小示例：

```bash
.venv/bin/python -m apps.research \
  --input ./bars.json \
  --output ./artifacts/backtest-result.json
```

或者通过仓库根目录的 `make` 目标：

```bash
make research ARGS="--input ./bars.json --output ./artifacts/backtest-result.json"
```

如果你还想顺手导出一个更贴近前端研究页契约的快照文件，可以额外传：

```bash
--web-snapshot-output ./artifacts/research-snapshot.json
```

如果你想把参数扫描和滚动评估结果也一起导出来，可以再加一份实验报告：

```bash
.venv/bin/python -m apps.research \
  --input ./bars.json \
  --experiment-output ./artifacts/research-experiments.json \
  --baseline-sweep-grid ./baseline-grid.json \
  --walk-forward-window-bars 96 \
  --walk-forward-step-bars 48
```

CLI 支持这些常用参数：

- `--input`：必填，输入 JSON 文件路径
- `--output`：可选，导出 `BacktestRunResult` JSON；不传时打印到 stdout
- `--web-snapshot-output`：可选，导出前端研究页可直接消费的快照 JSON；真实导出会显式标记 `sourceMode=imported`
- `--experiment-output`：可选，导出参数扫描 / walk-forward 研究报告
- `--initial-cash`：可选，默认 `100000`
- `--slippage-bps`：可选，默认 `5`
- `--slippage-model`：可选，支持 `bar_close_bps` 和 `directional_close_tiered_bps`
- `--baseline-sweep-grid`：可选，JSON/YAML 参数网格文件，用于 baseline 批量参数扫描
- `--walk-forward-window-bars`：可选，滚动评估窗口 bar 数
- `--walk-forward-step-bars`：可选，滚动评估步长；默认等于窗口大小
- `--config-profile` / `--config-file`：可选，允许显式切换配置层
- `--postgres-dsn`：可选，仅用于满足共享 settings 校验；不传时 CLI 会回退到内存 SQLite

如果你想直接从控制面读取一份前端可消费的真实 research 快照，而不是先手工导出文件，也可以通过 API：

```text
GET /v1/research/snapshot?symbol=600036.SH&timeframe=15m&limit=96
```

输入文件需要是以下两种形式之一：

1. 一个 `BarEvent` JSON 数组
2. 一个包含 `bars` 或 `events` 数组字段的 JSON 对象

其中每个 bar 都应满足：

- 至少包含 `BarEvent` 所需字段
- 按 `event_time` 升序排列
- 使用 final/closed bar

### 方式二：直接通过 Python API 调用

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

如果你传了 `--experiment-output`，CLI 还会额外生成一份 `ResearchExperimentReport`，其中至少可能包含：

- `parameter_sweep`：baseline 参数组合的批量回测摘要，支持按同一指标排序比较
- `walk_forward`：按固定窗口和步长滚动得到的阶段结果

研究页现在也会在 baseline 与 AI 两块结果都存在时，补一个标准化对照区，直接比较收益、回撤、交易数和关键决策差异。

## 当前执行假设

当前 research/backtest 在执行层已经显式区分并记录这些假设：

- 固定滑点基线：`bar_close_bps`
- 更保守的分层滑点：`directional_close_tiered_bps`
  会根据 `decision_price` 相对 `previous_close` 的不利方向偏移放大滑点
- 部分成交 / 成交失败：当前结论仍是先保持 `full_fill_only`
  也就是说，回测一旦接受订单，仍按整笔成交处理，不额外模拟部分成交和 missed fill

manifest 和 web snapshot 里现在会同时给出：

- `slippageModel`
- `partialFillModel`
- `unfilledQtyHandling`
- `executionConstraints`

这样在比较策略收益时，可以更清楚地区分哪些结果来自 alpha，哪些仍来自当前执行假设的简化。

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
- `tests/integration/test_research_cli.py`

如果你想了解完整系统上下文，回到仓库根目录的 `README.md`；如果你只关心最小回测入口，从这里开始就够了。
