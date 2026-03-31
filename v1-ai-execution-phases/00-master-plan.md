# AI 量化交易系统 V1 执行说明

这份文档不是完整架构说明，而是给 AI 或开发助手使用的 `V1 顺序执行文件`。

目标只有一个：

> 按顺序实现一个适合个人项目的、可审计的 `paper trading MVP`。

这里定义的 `V1` 不包含真实小资金实盘，不包含 AI/ML 训练，不包含多交易所，不包含多策略组合。

如果需要把任务进一步拆成适合 AI 单次执行的粒度，请使用本目录下的 phase 文件。

---

## 1. V1 的固定边界

AI 在执行时，必须严格遵守下面的边界，不允许擅自扩展：

- 只支持 `1 个交易所`
- 只支持 `1 个交易账户`
- 只支持 `1-3 个交易对`
- 只支持 `1 个主策略`
- 只支持 `分钟级到小时级` 策略
- 第一版市场输入以 `BarEvent` 为主
- 第一版执行模式只做 `paper trading`
- 第一版监控只做 `结构化日志 + Telegram 告警 + 少量 API`
- 第一版数据库以 `PostgreSQL` 为核心

AI 不应在 V1 中主动引入这些内容：

- `TickEvent`
- `OrderBookEvent`
- 多交易所
- 多账户
- 多策略组合
- `Redis Streams`
- `Kafka`
- `Kubernetes`
- `Prometheus / Grafana`
- 实盘下单
- 模型训练与在线推理

---

## 2. AI 执行规则

AI 必须按阶段顺序执行，不允许跳阶段。

每个阶段都遵守下面规则：

1. 先完成当前阶段，再进入下一阶段。
2. 当前阶段未完成时，不提前实现下个阶段的复杂能力。
3. 如果当前阶段缺少前置决策，先补文档或配置，不要直接猜完整实现。
4. 每完成一个阶段，必须输出：
   - 已修改文件
   - 已完成能力
   - 未解决风险
   - 是否可以进入下一阶段
5. 如果发现某个能力会显著扩大范围，应停在当前阶段并标记为 `后置项`。

---

## 3. V1 完成线

只有当下面这些条件全部成立时，V1 才算完成：

- 可以稳定接入并标准化 `BarEvent`
- 可以运行 `1 个主策略`
- 可以生成 `Signal`
- 所有下单动作都先经过 `Pre-Trade Risk`
- 所有 `OrderIntent` 都先落库，再进入 `paper execution`
- 可以记录 `Order / Fill / Position / Balance`
- 系统重启后可以恢复核心状态
- 可以人工查询状态、启停策略、触发 `kill switch`
- 可以进行最小对账，发现异常时进入保护模式
- 可以跑通一套基线策略的 paper 闭环

---

## 4. 建议目录目标

AI 在执行 V1 时，建议尽量围绕下面的目录落代码：

```text
apps/
  api/
  trader/
  collector/
  research/

src/
  domain/
    events/
    strategy/
    risk/
    portfolio/
    execution/
    reconciliation/
  infra/
    db/
    exchanges/
    messaging/
    observability/
  services/
    backtest/
  config/
  shared/

tests/
  unit/
  integration/
  e2e/
```

如果项目当前还没有完整脚手架，AI 可以先创建最小目录结构，但不要一次性填满所有模块。

---

## 5. 顺序执行计划

下面是 AI 必须遵守的执行顺序。

---

## Phase 0：先定范围和配置骨架

### 目标

把 V1 的业务边界、运行模式和基础配置先固定下来。

### 依赖

无

### 要做的事

- 明确交易所、市场类型、交易对、周期
- 明确 `paper` 是唯一执行模式
- 建立基础配置结构
- 建立环境区分，例如 `dev`
- 建立最小日志配置

### 产出物

- 范围说明文档
- 配置文件骨架
- 应用启动所需的基础设置

### 完成标准

- AI 不再把需求理解成“通用平台”
- 代码中已经能读到固定范围配置

### 禁止扩展

- 不接交易所
- 不建数据库表
- 不实现策略逻辑

---

## Phase 1：标准事件模型和领域对象

### 目标

先统一交易语义，让后续 collector、trader、backtest、paper execution 都能共用。

### 依赖

- Phase 0

### 要做的事

- 定义 `BarEvent`
- 定义 `Signal`
- 定义 `OrderIntent`
- 定义 `Order`
- 定义 `Fill`
- 定义 `Position`
- 定义 `BalanceSnapshot`
- 定义订单状态枚举和状态流转规则
- 统一时间字段和 ID 字段

### 产出物

- `domain/events`
- `domain/execution`
- `domain/portfolio`
- `domain/strategy` 中的核心类型

### 完成标准

- 核心对象有稳定 schema
- `OrderIntent` 与 `Order` 语义清晰分离
- 订单状态机有单元测试

### 禁止扩展

- 不写真实下单逻辑
- 不接数据库实现细节
- 不引入 Tick / OrderBook 模型

---

## Phase 2：数据库与核心持久化

### 目标

建立交易系统的本地事实源。

### 依赖

- Phase 1

### 要做的事

- 建立数据库连接与 migration 机制
- 为 `Signal / OrderIntent / Order / Fill / Position / BalanceSnapshot` 建表
- 建立事件日志表或等价审计表
- 建立 repository / DAO 抽象
- 支持幂等更新

### 产出物

- `infra/db`
- 数据库 schema
- migration 文件

### 完成标准

- 可以独立写入和查询核心交易状态
- 系统重启后能从数据库恢复必要状态
- 状态更新有幂等保护

### 禁止扩展

- 不接行情
- 不写策略运行时
- 不做复杂查询优化

---

## Phase 3：Collector 与 Market Gateway

### 目标

把外部市场数据转成统一的 `BarEvent`。

### 依赖

- Phase 1
- Phase 2

### 要做的事

- 接入单一交易所的历史 K 线
- 接入单一交易所的实时 K 线或等价 bar 数据
- 统一 `symbol`、时区、精度
- 保存原始 payload
- 输出标准化 `BarEvent`
- 处理断线重连和补数

### 产出物

- `apps/collector`
- `infra/exchanges`
- `domain/market` 或等价模块

### 完成标准

- 可以稳定采集并标准化 bar 数据
- collector 异常恢复后可以继续工作
- 关键市场数据可以写入本地持久层或事件日志

### 禁止扩展

- 不实现 Tick / OrderBook
- 不接多交易所
- 不为追求低延迟引入复杂消息系统

---

## Phase 4：Trader 主循环与进程内 Event Bus

### 目标

把 collector 输出送入统一交易主循环。

### 依赖

- Phase 1
- Phase 2
- Phase 3

### 要做的事

- 建立 trader 主进程
- 建立进程内 dispatcher 或 `asyncio queue`
- 建立事件订阅机制
- 让 `BarEvent` 可以进入策略运行时

### 产出物

- `apps/trader`
- `infra/messaging`

### 完成标准

- trader 能消费标准事件
- 模块之间通过统一事件流衔接
- 不依赖 Redis 也能跑通主链路

### 禁止扩展

- 不引入 `Redis Streams`
- 不拆远程微服务
- 不实现复杂调度系统

---

## Phase 5：OMS、Portfolio State 与 Paper Execution

### 目标

跑通最核心的交易闭环。

### 依赖

- Phase 1
- Phase 2
- Phase 4

### 要做的事

- 实现 `Signal -> OrderIntent`
- 实现 OMS 持久化流程
- 实现 `paper execution adapter`
- 模拟 `ACK / PARTIAL / FILL / REJECT / CANCEL`
- 更新 `Position / Balance / PnL`

### 产出物

- `domain/execution`
- `domain/portfolio`
- `infra/exchanges` 中的 `paper adapter`

### 完成标准

- 可以跑通完整 paper 闭环
- 所有状态变化都可以落库
- 重启后能恢复订单、持仓、余额

### 禁止扩展

- 不接真实 live 下单
- 不做复杂执行算法
- 不做多账户资金分配

---

## Phase 6：Pre-Trade Risk 与最小控制面

### 目标

让系统具备基本安全性和人工介入能力。

### 依赖

- Phase 5

### 要做的事

- 实现最大仓位检查
- 实现最大名义价值检查
- 实现重复下单防护
- 实现行情过期检查
- 实现最小下单量和交易规则检查
- 实现策略启停
- 实现状态查询 API
- 实现 `kill switch`
- 实现 `cancel all`
- 接入 Telegram 告警

### 产出物

- `domain/risk`
- `apps/api`
- `infra/observability`

### 完成标准

- 所有下单动作必须经过统一风险闸门
- 风险拒绝有明确原因
- 可以通过 API 或控制面人工接管系统

### 禁止扩展

- 不做复杂 RBAC
- 不做完整 dashboard
- 不做复杂动态风控模型

---

## Phase 7：基线策略与端到端 Paper 验证

### 目标

用一套简单可解释的策略验证交易内核。

### 依赖

- Phase 6

### 要做的事

- 实现一套简单规则策略，例如均线或动量
- 记录策略输入快照、输出信号、原因摘要
- 跑通端到端 paper 流程
- 输出最小交易结果摘要

### 产出物

- `domain/strategy`
- 对应测试和示例配置

### 完成标准

- 至少 1 套基线策略能在 paper 模式稳定运行
- 策略能持续产生可审计的信号与订单记录

### 禁止扩展

- 不引入 AI 推理
- 不做多策略调度
- 不做复杂因子库

---

## Phase 8：最小 Backtest 一致性

### 目标

让同一套策略接口能用于研究验证，而不是做两套逻辑。

### 依赖

- Phase 7

### 要做的事

- 建立最小事件驱动回测器
- 复用相同策略接口
- 复用相同订单语义
- 加入手续费和简单滑点
- 输出标准绩效摘要

### 产出物

- `services/backtest`
- `apps/research`

### 完成标准

- 同一策略可以运行在 backtest 和 paper
- 回测结果可复现
- 报表至少包含收益、回撤、交易次数等基础指标

### 禁止扩展

- 不建设完整研究平台
- 不做大规模参数搜索
- 不接 AI/ML pipeline

---

## Phase 9：最小对账与保护模式

### 目标

保证系统出现异常时不会继续带病运行。

### 依赖

- Phase 5
- Phase 6

### 要做的事

- 实现启动恢复
- 实现定时对账
- 检查订单、持仓、余额漂移
- 对账异常时进入保护模式
- 记录诊断信息并发送告警

### 产出物

- `domain/reconciliation`
- 对账脚本或任务入口

### 完成标准

- 能发现状态漂移
- 能阻止系统在异常状态下继续开新仓
- 能留存足够排查信息

### 禁止扩展

- 不追求全自动修复
- 不实现复杂自愈系统

---

## 6. 推荐执行顺序摘要

AI 执行时，只允许按下面顺序前进：

1. `Phase 0`：范围和配置骨架
2. `Phase 1`：事件模型和领域对象
3. `Phase 2`：数据库与核心持久化
4. `Phase 3`：Collector 与 Market Gateway
5. `Phase 4`：Trader 主循环与进程内 Event Bus
6. `Phase 5`：OMS + Portfolio + Paper Execution
7. `Phase 6`：Pre-Trade Risk + 最小控制面
8. `Phase 7`：基线策略 + 端到端 Paper 验证
9. `Phase 8`：最小 Backtest 一致性
10. `Phase 9`：最小对账与保护模式

如果 `Phase 5` 还没有稳定跑通，就不应该进入 `Phase 8` 和 `Phase 9` 之后的扩展工作。

---

## 7. V1 完成后再考虑的内容

只有 V1 完成后，AI 才可以进入这些后续主题：

- 小资金 live trading
- 更完善的对账修复
- 特征工程 pipeline
- 传统 ML 模型
- 在线推理
- 多策略组合
- 多品种扩展
- 更细粒度执行逻辑

---

## 8. 一句话交付定义

如果 AI 最终交付的是下面这个系统，就算 V1 成功：

> 一个单交易所、单账户、单策略、K 线驱动、可审计、可回放、带基础风控与保护模式的 paper trading 系统。
