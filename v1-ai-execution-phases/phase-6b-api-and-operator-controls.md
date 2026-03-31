# Phase 6B：API 与操作控制

这份文件用于把 `Phase 6` 进一步拆成更适合 AI 单次编码的子任务。

## 本次目标

提供最小控制面，让操作者可以查询状态、启停策略并执行保命动作。

## 前置依赖

- `Phase 5：OMS 与 Paper Execution`
- `Phase 6A：Pre-Trade Risk Rules`

## 必读上下文

- `./00-master-plan.md`
- `./testing-standards.md`
- `./implementation-decisions.md`
- `./phase-6-risk-and-control-plane.md`
- `./phase-6a-pretrade-risk-rules.md`

## 允许修改范围

- `apps/api/`
- `apps/trader/`
- `src/infra/db/` 中与单活 trader 保护直接相关的少量代码
- `src/domain/risk/` 中与控制状态衔接相关的少量代码
- `tests/unit/`
- `tests/integration/`

## 本次必须完成的任务

- 提供状态查询接口
- 提供策略启停能力
- 提供 `kill switch`
- 提供 `cancel all`
- 提供健康检查与就绪检查
- 限制同一交易账户只允许 `1 个 active trader` 实例
- 基于 `PostgreSQL` lease 实现单活保护，至少明确 `owner_instance_id / lease_expires_at / last_heartbeat_at / fencing_token`
- lease 丢失或过期时，让实例降级为 `not ready` 并停止提交新订单
- 让 `kill switch` 激活后进入减仓 / 平仓保护状态：拒绝新开仓 / 增仓，但允许 `cancel all`、减仓和平仓；如实现中保留 `reduce_only` 字段，它只作为兼容标记
- 让这些控制动作能影响 trader 运行状态

## 本次不要做

- 不做完整 dashboard
- 不做复杂 RBAC
- 不做运营后台

## 默认实现细节

### 1. 健康检查与就绪检查

建议默认定义如下：

- `live`：进程存活、事件循环可推进、基础配置已加载
- `ready`：具备继续提交新订单的资格

`ready = true` 建议至少同时满足：

- PostgreSQL 可连接
- 当前实例持有未过期 lease
- 当前实例持有的 `fencing_token` 仍然有效
- 最新 final bar 未过期
- 当前执行模式所需的最小 market state 可用
- trader 不处于致命错误状态

如果 lease 丢失、过期或 fencing 失效，应在一个主循环周期内降级为 `not ready`。

### 2. PostgreSQL lease 默认规则

建议默认规则：

- `lease_ttl_seconds = 15`
- `heartbeat_interval_seconds = 5`
- lease 为账户级，而不是全局进程级
- lease 记录至少包含 `owner_instance_id / lease_expires_at / last_heartbeat_at / fencing_token`

建议默认行为：

- 启动时先抢占或续租 lease，再进入可下单状态
- heartbeat 续租采用 compare-and-swap 或等价乐观并发方式
- 每次成功续租时保留当前 `fencing_token`
- 当实例重新抢到 lease 时，`fencing_token` 必须递增或更新

### 3. fencing 规则

默认要求：

- 所有“提交新订单”的路径都要带上当前 `fencing_token`
- 如果写入时发现 token 已过期或与当前 lease 不一致，应拒绝提交
- 老实例即使线程恢复，也不能继续生成新的 `OrderIntent`

### 4. 控制动作与 trader 行为

建议默认行为：

- `strategy pause`：停止产生新的 signal / order intent，但不影响查询和风控状态读取
- `strategy resume`：恢复策略驱动
- `kill switch enable`：进入减仓 / 平仓保护状态
- `kill switch disable`：只解除操作者闸门，不自动退出 `protection_mode`
- `cancel all`：只取消当前非终态挂单，不应清空历史事实
- `cancel all` 在保护状态下仍需保留减仓 / 平仓路径，不应误取消用于减仓的保护挂单

### 5. API 请求与响应约定

如果当前没有既定接口规范，建议控制类接口默认返回：

- `accepted`
- `control_state`
- `trader_run_id`
- `instance_id`
- `effective_at`
- `message`

`cancel all` 响应建议额外包含：

- `requested_order_count`
- `cancelled_order_count`
- `skipped_order_count`

### 6. kill switch 与 cancel all 的边界

默认语义应固定为：

- `kill switch` 是交易闸门，不等于“清空系统状态”
- `cancel all` 是订单操作，不等于“允许重新开仓”
- `kill switch` 激活后，仍允许操作者执行 `cancel all`
- `cancel all` 执行完成后，如果 `kill switch` 仍为激活状态，系统依旧必须维持减仓 / 平仓保护状态

## 完成标准

- 操作者可以查询系统关键状态
- 操作者可以主动阻止系统继续开新仓
- 控制动作与 trader 状态有明确连接
- 操作者可以判断系统是否健康与就绪
- 同一交易账户不会被多个 active trader 实例同时接管
- 旧实例即使恢复执行，也会因为 fencing 失效而无法继续提交新订单
- `kill switch` 激活后，系统仍保留减仓、平仓和 `cancel all` 的操作路径

## 最低验证要求

- 至少有测试覆盖状态查询
- 至少有测试覆盖 `kill switch` 或策略暂停
- 至少有测试覆盖健康检查或就绪检查
- 至少验证一次重复 trader 启动被拦截或等价保护路径
- 至少验证一次 `kill switch` 拦截开仓但允许减仓或平仓

## 本次交付时必须汇报

- 暴露了哪些 API 或控制动作
- 健康检查 / 就绪检查如何定义
- 单活 trader 保护采用什么机制
- lease TTL、heartbeat 和 fencing 规则如何定义
- `kill switch` 与 `cancel all` 的动作边界
- trader 如何响应这些控制动作
- 哪些告警与安全运维能力仍留给 `Phase 6C`

## 可直接复制给 AI 的执行提示词

```text
你现在负责本项目的 Phase 6B：API 与操作控制。

请先阅读：
- ./00-master-plan.md
- ./testing-standards.md
- ./implementation-decisions.md
- ./phase-6-risk-and-control-plane.md
- ./phase-6a-pretrade-risk-rules.md
- ./phase-6b-api-and-operator-controls.md

本次只允许修改：
- apps/api/
- apps/trader/
- src/infra/db/ 中与单活 trader 保护直接相关的少量代码
- src/domain/risk/ 中与控制状态衔接相关的少量代码
- tests/unit/
- tests/integration/

本次必须完成：
- 提供状态查询接口
- 提供策略启停
- 提供 kill switch
- 提供 cancel all
- 提供健康检查与就绪检查
- 限制同一交易账户只允许 1 个 active trader 实例
- 基于 PostgreSQL lease 明确 owner_instance_id / lease_expires_at / last_heartbeat_at / fencing_token
- lease 丢失或过期时，让实例降级为 not ready 并停止提交新订单
- 让 kill switch 激活后进入减仓 / 平仓保护状态：拒绝新开仓 / 增仓，但允许 cancel all、减仓和平仓；如实现中保留 `reduce_only` 字段，它只作为兼容标记
- 让控制动作真正影响 trader 状态

严格不要做：
- 不做完整 dashboard
- 不做复杂 RBAC
- 不做运营后台

完成后请输出：
1. 已修改文件
2. 已完成能力
3. 暴露了哪些 API / 控制能力
4. 健康检查 / 就绪检查定义
5. 单活 trader 保护机制
6. lease TTL / heartbeat / fencing 规则
7. kill switch / cancel all 动作边界
8. trader 如何响应这些控制动作
9. 测试情况：
   - 已运行哪些测试
   - 哪些通过
   - 哪些未运行
   - 为什么未运行
   - 当前剩余测试风险
10. 未解决风险
11. 是否可以进入 Phase 6C
```
