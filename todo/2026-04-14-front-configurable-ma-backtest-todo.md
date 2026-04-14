# SignalArk 前端可配置均线规则回测待办

生成时间：2026-04-14

## 目标

- 让用户可以在前端直接设置一套简单买卖规则，然后对过去几年历史数据做回测，并查看收益、回撤、交易次数和逐笔决策原因。
- 第一版先聚焦你给的典型场景：`60 日均线 - 5% 买入，60 日均线 + 10% 卖出`。
- 保持与当前 `research/backtest` 主链路一致，继续复用现有的策略、下单、paper execution、账本、T+1、手续费和滑点语义。

## 推荐方案

推荐先做“单模板规则回测”，不要一上来做任意表达式 DSL。

- 模板名固定为 `moving_average_band_v1`
- 规则固定为“相对均线偏离触发买卖”
- 前端先暴露这些参数：
  - `symbol`
  - `timeframe`，第一版必须补 `1d`
  - `historyYears` 或直接换算后的 `limit`
  - `maWindow`
  - `buyBelowMaPct`
  - `sellAboveMaPct`
  - `targetPosition`
  - `initialCash`
- 后端新增一个专用 `POST` research 接口，避免把复杂参数硬塞进现有 `GET /v1/research/snapshot`

这样做的原因：

- 当前系统已经支持策略对象注入 `build_default_backtest_runner(...)`，新规则可以走旁路接入，而不必改乱现有 baseline/AI 主流程。
- “60 日均线”天然更适合 `1d`，而当前前端研究页只有 `15m / 1h`，所以第一优先级是补 daily 回测入口，而不是做复杂条件编辑器。
- 用固定模板先把端到端链路跑通，后续再扩到 EMA、双均线、止损止盈、多个规则组合会更稳。

## 第一版范围

- 仅支持单标的、单策略、只做多
- 仅支持一条均线
- 仅支持“低于均线一定百分比买入，高于均线一定百分比卖出”
- 仅支持固定目标仓位，不做资金占比仓位
- 继续保留 A 股 `T+1`
- 不做数据库持久化，不保存用户自定义策略模板
- 不做任意条件表达式、拖拽式规则编排、多指标组合

## 建议请求契约

建议新增 `POST /v1/research/rule-snapshot`

请求体示例：

```json
{
  "symbol": "600036.SH",
  "timeframe": "1d",
  "limit": 750,
  "initialCash": 100000,
  "slippageBps": 5,
  "ruleTemplate": "moving_average_band_v1",
  "ruleConfig": {
    "maWindow": 60,
    "buyBelowMaPct": 0.05,
    "sellAboveMaPct": 0.10,
    "targetPosition": 400
  }
}
```

响应体建议继续复用现有 `ResearchSnapshot`，不要新造第二套前端展示契约。

## AI 友好拆分

### Task 1：冻结 MVP 契约与参数语义

- [ ] 明确第一版只支持 `moving_average_band_v1`
- [ ] 明确 `maWindow=60` 指的是 `1d` 下的 60 根日线，而不是 60 个任意 timeframe bar
- [ ] 明确 `buyBelowMaPct=0.05` 表示 `close <= ma * (1 - 0.05)` 才买入
- [ ] 明确 `sellAboveMaPct=0.10` 表示 `close >= ma * (1 + 0.10)` 才卖出
- [ ] 明确 `targetPosition` 继续沿用当前系统的“股数”语义

触达文件：

- `apps/api/main.py`
- `apps/web/src/types/research.ts`
- `apps/web/src/lib/api.ts`
- `apps/research/README.md`

完成标准：

- 新旧 research 接口的语义边界清楚
- 不会把“60 日均线”误实现成“当前 timeframe 的 60 根均线”

### Task 2：新增后端请求模型与路由

- [ ] 在 API 层新增 `ResearchRuleSnapshotRequest`
- [ ] 新增 `POST /v1/research/rule-snapshot`
- [ ] 参数校验至少覆盖：
  - `timeframe` 不能为空
  - `maWindow >= 2`
  - `buyBelowMaPct` 在 `[0, 1)` 内
  - `sellAboveMaPct` 在 `[0, 1)` 内
  - `targetPosition > 0`
  - `limit > maWindow`
- [ ] 保持错误响应继续走现有 `ApiError/detail` 风格

触达文件：

- `apps/api/main.py`
- `tests/integration/test_api_research_snapshot.py`

完成标准：

- 可以用一条 POST 请求触发规则回测
- 非法参数返回 400，并带清晰错误信息

### Task 3：实现自定义均线规则策略类

- [ ] 新增一个专门的研究侧规则策略实现，建议命名 `MovingAverageBandStrategy`
- [ ] 输出结构继续兼容现有 `Signal` / `StrategyDecisionAudit`
- [ ] 预热阶段需要显式记录“均线样本不足”的跳过原因
- [ ] 决策原因必须可读，例如：
  - 当前收盘价
  - MA60 值
  - 偏离比例
  - 为什么买 / 为什么卖 / 为什么跳过
- [ ] `backtest_metadata()` 中要带出规则模板和参数快照

建议新增文件：

- `src/domain/strategy/rule_based.py`

可能需要改动：

- `src/domain/strategy/__init__.py`
- `src/domain/strategy/signal.py`

完成标准：

- 给定一组固定 bars，可以稳定地产生 `BUY / SELL / SKIP`
- 研究页最终能看到清楚的原因摘要，而不是只有机器字段

### Task 4：把新策略接进 research runner

- [ ] 通过 `build_default_backtest_runner(..., strategy=...)` 注入自定义策略
- [ ] 不改动当前 baseline 和 AI research 入口行为
- [ ] 复用现有 `build_web_snapshot_payload(...)`
- [ ] 保证 `manifest.strategyId`、`description`、`parameterSnapshot` 正确反映这套规则

触达文件：

- `apps/api/control_plane.py`
- `apps/research/backtest.py`
- `apps/research/snapshot.py`

完成标准：

- 自定义规则回测返回结果和当前研究页现有结构完全兼容
- 前端不需要为“自定义规则结果”额外写第二套展示组件

### Task 5：补 daily timeframe 与多年样本入口

- [ ] 把前端研究页 timeframe 选项扩展到 `1d`
- [ ] 评估默认 years -> limit 的换算方式
- [ ] 推荐第一版直接提供：
  - 1 年
  - 3 年
  - 5 年
- [ ] 后端保持 `limit` 驱动，不强耦合 years

触达文件：

- `apps/web/src/App.tsx`
- `apps/web/src/components/views/ResearchView.tsx`
- `apps/web/src/lib/api.ts`

完成标准：

- 前端能发起 `1d` 规则回测
- 至少可以方便测试“过去几年”的样本，而不是只停留在短样本

### Task 6：新增前端请求类型、API 方法和 hook

- [ ] 新增 `ResearchRuleSnapshotRequest`
- [ ] 新增 `postResearchRuleSnapshot(...)`
- [ ] 新增独立 hook，建议命名 `useRuleResearchData`
- [ ] 保持 loading / error / fetchedAt / refresh 语义与现有 hook 一致

触达文件：

- `apps/web/src/types/research.ts`
- `apps/web/src/lib/api.ts`
- `apps/web/src/lib/api.test.ts`
- `apps/web/src/hooks/use-rule-research-data.ts`

完成标准：

- 前端侧有独立、稳定、可测试的规则回测调用层
- 不把自定义规则逻辑硬塞进现有 `useResearchData` 和 `useAiResearchData`

### Task 7：在研究页新增“规则回测”配置面板

- [ ] 新增一个专门的前端表单区域
- [ ] 字段建议：
  - 均线周期
  - 低于均线买入比例
  - 高于均线卖出比例
  - 目标仓位
  - 初始资金
  - 样本区间
- [ ] 给每个字段补白话提示
- [ ] 提供一个“快速填充示例”按钮，直接带入：
  - MA 60
  - 买入 -5%
  - 卖出 +10%
  - 目标仓位 400
- [ ] 点击按钮后直接运行规则回测

触达文件：

- `apps/web/src/components/views/ResearchView.tsx`
- `apps/web/src/styles.css`

完成标准：

- 用户不需要改 YAML 或后端配置，就能发起这套规则回测
- 第一眼就能理解每个输入框是干什么的

### Task 8：把自定义规则结果挂到现有 research 展示区

- [ ] 自定义规则结果继续展示：
  - 资金曲线
  - 回测指标
  - 决策表
  - 策略说明
- [ ] 策略说明区要明确显示：
  - 模板名
  - MA 周期
  - 买卖阈值
  - 目标仓位
- [ ] 决策表里的原因摘要要能读懂“为什么今天没有买 / 没有卖”

触达文件：

- `apps/web/src/components/views/ResearchView.tsx`
- `apps/web/src/components/BacktestDecisionTable.tsx`
- `apps/web/src/lib/research-copy.ts`

完成标准：

- 自定义规则结果看起来和 baseline / AI 一样完整
- 不会出现“策略能跑，但页面不知道怎么解释”的断层

### Task 9：补单元测试与集成测试

- [ ] 给 `MovingAverageBandStrategy` 补单元测试
- [ ] 覆盖场景至少包括：
  - 均线预热不足
  - 跌到买入阈值触发买入
  - 涨到卖出阈值触发卖出
  - 区间内不满足条件时保持不动
  - A 股 `T+1` 导致当天买入后不能立即卖出
- [ ] 给 API 补 integration test
- [ ] 给前端表单和 hook 补测试

建议测试文件：

- `tests/unit/test_moving_average_band_strategy.py`
- `tests/integration/test_api_research_snapshot.py`
- `apps/web/src/lib/api.test.ts`
- `apps/web/src/components/BacktestDecisionTable.test.tsx`
- `apps/web/src/App.test.tsx`

完成标准：

- 端到端最小闭环可测
- 不靠手点页面才能知道有没有回归

### Task 10：补文档与示例

- [ ] 在 `apps/research/README.md` 增加规则回测接口说明
- [ ] 增加一段 curl 或 fetch 示例
- [ ] 明确第一版限制：
  - 只做多
  - 单均线
  - 固定仓位
  - A 股 T+1
- [ ] 明确“过去几年”建议优先使用 `1d`

完成标准：

- 新同学不看实现细节，也知道这个功能怎么调

## Phase 2，可后续再做

- [ ] 支持 EMA / 双均线 / 金叉死叉
- [ ] 支持止损、止盈、最大持有天数
- [ ] 支持与 baseline 自动对照
- [ ] 支持保存前端预设
- [ ] 支持多个规则模板切换
- [ ] 支持更通用的条件表达式或规则编排器

## 暂不建议现在做

- 任意表达式 DSL
- 多标的组合回测
- 多指标可视化编排器
- 策略模板持久化到数据库
- 和 runtime 实盘配置完全打通

## 推荐实施顺序

1. 先补 `POST /v1/research/rule-snapshot` 与 `MovingAverageBandStrategy`
2. 再补前端 `1d` 与规则表单
3. 然后把结果接回现有 research 展示区
4. 最后补测试、文档和后续扩展点

## 交付验收样例

以 `600036.SH + 1d + 近 3 年 + MA60/-5%/+10%` 为例，最终应该满足：

- 用户可以在前端填完参数后直接运行
- 页面会返回一份完整的 `ResearchSnapshot`
- 指标区能看到净收益、回撤、交易次数
- 决策表能看到每次买卖或跳过的中文原因
- 策略说明区能清楚显示“MA60、低于均线 5% 买、高于均线 10% 卖、目标仓位 400”
- 结果继续遵守当前 A 股 `T+1` 和成本模型
