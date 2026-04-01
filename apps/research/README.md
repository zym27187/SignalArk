# Research App Scaffold

`apps/research/` 预留给后续回测、研究任务和实验脚本。

V1 中建议：

- 回测入口在 `Phase 8` 通过 `build_default_backtest_runner(...)` 和
  `ResearchBacktestRunner.run(...)` 提供最小事件驱动回放
- 不在当前阶段提前实现训练平台或在线推理
