# Phase 2：数据库与核心持久化

这份文件用于 AI 单次执行 `Phase 2`。

默认推荐先执行下面的子任务文件，再回到 `Phase 2` 主实现：

- `./phase-2a-db-schema-and-migration-draft.md`

如果需要更细的数据库实现说明，也请继续阅读：

- `./phase-2a-db-schema-and-migration-draft.md`

## 本次目标

建立交易系统的本地事实源，让订单、成交、持仓、余额等状态不依赖内存存活。

## 前置依赖

- `Phase 1：事件模型与领域对象`

## 必读上下文

- `./00-master-plan.md`
- `./testing-standards.md`
- `./implementation-decisions.md`
- `./phase-1-domain-model.md`
- `./phase-2a-db-schema-and-migration-draft.md`

## 允许修改范围

- `src/infra/db/`
- `src/domain/execution/` 中与持久化接口相关的少量代码
- `src/domain/portfolio/` 中与持久化接口相关的少量代码
- `migrations/` 或等价目录
- `tests/unit/`
- `tests/integration/`

## 本次必须完成的任务

- 建立数据库连接与 migration 机制
- 为 `Signal`、`OrderIntent`、`Order`、`Fill`、`Position`、`BalanceSnapshot` 建表
- 建立事件日志表或等价审计表
- 建立 repository / DAO 抽象
- 支持幂等更新或幂等写入
- 支持重启后的核心状态恢复基础能力

## 本次不要做

- 不接行情
- 不写策略运行时
- 不写复杂查询优化
- 不为了通用性提前引入太多抽象层

## 完成标准

- 核心交易状态可独立写入和查询
- 重启后可恢复必要状态
- 状态更新具备基本幂等保护

## 最低验证要求

- 至少有 1 组集成测试覆盖建表和基本读写
- 至少有 1 组测试覆盖幂等更新场景

## 本次交付时必须汇报

- 建了哪些表
- 哪些对象已经可持久化
- 当前恢复能力能恢复到什么程度

## 可直接复制给 AI 的执行提示词

```text
你现在负责本项目的 Phase 2：数据库与核心持久化。

请先阅读：
- ./00-master-plan.md
- ./testing-standards.md
- ./implementation-decisions.md
- ./phase-2-db-and-persistence.md
- ./phase-1-domain-model.md
- ./phase-2a-db-schema-and-migration-draft.md

本次只允许修改：
- src/infra/db/
- migrations/ 或等价目录
- src/domain/execution/ 中与持久化接口相关的少量代码
- src/domain/portfolio/ 中与持久化接口相关的少量代码
- tests/unit/
- tests/integration/

本次必须完成：
- 建立数据库连接与 migration 机制
- 为 Signal、OrderIntent、Order、Fill、Position、BalanceSnapshot 建表
- 建立事件日志或审计表
- 建立 repository / DAO 抽象
- 支持幂等更新和基础恢复能力

严格不要做：
- 不接行情
- 不写策略运行时
- 不做复杂查询优化

完成后请输出：
1. 已修改文件
2. 已完成能力
3. 新增表结构
4. 已可持久化对象
5. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
6. 未解决风险
7. 是否可以进入 Phase 3
```
