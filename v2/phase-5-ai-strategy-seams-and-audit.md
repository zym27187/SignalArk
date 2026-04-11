# Phase 5：AI 策略接缝与统一审计

这份文件用于在不破坏当前稳定主链路的前提下，把 AI 策略实验接入统一框架。

## 本次目标

为 AI 策略建立稳定 provider seam、统一 audit 契约和 deterministic fallback，使其能在 research 与 trader 中以可解释、可复核的方式接入。

## 前置依赖

- [Phase 0：边界、术语与共享契约](./phase-0-boundaries-and-shared-contracts.md)
- [Phase 4：research 标准化与对照能力](./phase-4-research-standardization-and-comparison.md)

## 必读上下文

- [00-scope-draft.md](./00-scope-draft.md)
- [00-master-plan.md](./00-master-plan.md)
- [phase-0-boundaries-and-shared-contracts.md](./phase-0-boundaries-and-shared-contracts.md)
- [phase-4-research-standardization-and-comparison.md](./phase-4-research-standardization-and-comparison.md)
- [README.md](../README.md)
- [docs/plans/2026-04-07-ai-bar-judge-v1.md](../docs/plans/2026-04-07-ai-bar-judge-v1.md)
- [v1-ai-execution-phases/testing-standards.md](../v1-ai-execution-phases/testing-standards.md)

## 允许修改范围

- `configs/strategies/`
- `src/domain/strategy/`
- `apps/research/`
- `apps/trader/`
- `apps/api/`
- `apps/web/`
- `tests/unit/`
- `tests/integration/`

## 本次必须完成的任务

- 为 AI 策略保留稳定 provider seam。
- 保持 deterministic fallback，使本地验证和 CI 不依赖外部模型。
- 统一 baseline 和 AI 策略的 audit 契约。
- 为 AI 决策保留最小可解释字段，例如：
  - `provider_id`
  - `model_or_policy_version`
  - `decision`
  - `confidence`
  - `reason_summary`
- 让 AI 策略研究结果能与 baseline 在同一 manifest 和指标体系下比较。
- 让前端或 API 至少能读取 AI 决策摘要，而不是只能看到最终信号结果。

## 本次不要做

- 不做在线训练平台
- 不做自动调参平台
- 不做黑盒自治 trader
- 不让 AI 越过现有风控和 OMS 契约

## 默认实现细节

### 1. AI 的角色定位

V2 中 AI 默认是：

- `signal enhancer`
- `reviewer`
- `scorer`

而不是直接替代风控、执行和恢复逻辑。

### 2. 审计建议

AI 审计默认建议同时保留：

- 机器字段
- 面向人的摘要字段

这样前端既能显示结果，也能对金融小白做解释。

### 3. 回退原则

当外部 AI provider 不可用、超时或校验失败时：

- 默认降级到 deterministic fallback
- 不应让系统进入不可解释的隐式状态

## 完成标准

- AI 策略接缝稳定可替换
- baseline 和 AI 策略的 audit 契约统一
- AI 结果可对照、可复核、可解释
- 外部模型不可用时仍可本地验证

## 最低验证要求

- 至少覆盖一次 deterministic fallback
- 至少覆盖一次 AI audit 字段输出
- 至少覆盖一次 AI 与 baseline 的对照结果
- 如 trader 接入 AI 候选路径，至少验证一次其不会绕过现有风控

## 本次交付时必须汇报

- AI provider seam 如何定义
- fallback 如何工作
- 审计字段包含哪些核心内容
- AI 与 baseline 如何比较
- 当前仍有哪些能力故意不纳入 V2
- 是否达到 V2 完成线
