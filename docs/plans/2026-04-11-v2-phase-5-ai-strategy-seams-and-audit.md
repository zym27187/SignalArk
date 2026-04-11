# V2 Phase 5 AI Strategy Seams And Audit Implementation Plan

> **For implementer:** Keep this scoped to stable AI strategy seams, deterministic fallback, and one shared audit summary that research, trader, API, and frontend can all consume without inventing a second contract.

**Goal:** Land a stable AI provider seam with deterministic fallback, unify baseline and AI decision audit summaries, and surface the latest AI decision explanation through research snapshots and operator-facing runtime status.

**Architecture:** Reuse the existing `ai_bar_judge_v1` strategy and research comparison flow, add a normalized `strategy_decision_audit_summary` contract, persist the latest runtime decision summary through `trader_runtime_status`, and render the same summary shape in research and operations surfaces.

**Tech Stack:** Python, FastAPI, SQLAlchemy, Alembic, React 19, TypeScript, pytest, Vitest

---

### Task 1: Normalize strategy decision audit summaries

**Files:**
- Modify: `src/domain/strategy/audit.py`
- Modify: `src/domain/strategy/baseline.py`
- Modify: `src/domain/strategy/ai.py`
- Modify: `src/services/backtest/service.py`
- Modify: `src/services/backtest/models.py`
- Test: `tests/unit/test_ai_strategy.py`

**Step 1: Write the failing tests**
- Assert AI strategy audit summaries expose `provider_id`, `model_or_policy_version`, `decision`, `confidence`, `reason_summary`
- Assert deterministic policies such as baseline also emit the same summary shape

**Step 2: Run test — confirm it fails**
Command: `.venv/bin/python -m pytest tests/unit/test_ai_strategy.py -q`

**Step 3: Write minimal implementation**
- Add the shared audit summary model + serializers
- Attach the summary to baseline and AI audits
- Carry the summary through backtest decision records

**Step 4: Run test — confirm it passes**
Command: `.venv/bin/python -m pytest tests/unit/test_ai_strategy.py -q`

---

### Task 2: Add deterministic AI fallback and expose audit through research

**Files:**
- Modify: `src/domain/strategy/ai.py`
- Modify: `apps/api/control_plane.py`
- Modify: `apps/research/snapshot.py`
- Test: `tests/integration/test_api_research_snapshot.py`

**Step 1: Write the failing tests**
- Assert `openai_compatible` research requests fall back to deterministic heuristic output on provider failure
- Assert AI research decisions expose the normalized audit summary
- Assert AI and baseline comparison still share the same comparison contract

**Step 2: Run test — confirm it fails**
Command: `.venv/bin/python -m pytest tests/integration/test_api_research_snapshot.py -q`

**Step 3: Write minimal implementation**
- Wrap external providers with deterministic fallback
- Stamp fallback reason into the normalized audit summary
- Serialize the audit summary into research decision payloads

**Step 4: Run test — confirm it passes**
Command: `.venv/bin/python -m pytest tests/integration/test_api_research_snapshot.py -q`

---

### Task 3: Persist the latest runtime strategy audit and expose it to operators

**Files:**
- Modify: `apps/trader/runtime.py`
- Modify: `apps/trader/service.py`
- Modify: `apps/trader/control_plane.py`
- Modify: `apps/trader/oms.py`
- Modify: `apps/api/control_plane.py`
- Add: `migrations/versions/20260411_230500_runtime_strategy_audit_summary.py`
- Test: `tests/integration/test_trader_operator_runtime.py`
- Test: `tests/integration/test_api_operator_controls.py`

**Step 1: Write the failing tests**
- Assert trader runtime records the latest strategy audit even when the strategy decides to hold
- Assert `/v1/status` exposes the persisted latest strategy audit summary
- Assert OMS event payloads keep the normalized audit summary next to the detailed snapshots

**Step 2: Run test — confirm it fails**
Command: `.venv/bin/python -m pytest tests/integration/test_trader_operator_runtime.py tests/integration/test_api_operator_controls.py -q`

**Step 3: Write minimal implementation**
- Persist `last_strategy_audit` in `trader_runtime_status`
- Record non-signal decisions into runtime state without bypassing the risk/OMS path
- Surface the summary through the control-plane status payload

**Step 4: Run test — confirm it passes**
Command: `.venv/bin/python -m pytest tests/integration/test_trader_operator_runtime.py tests/integration/test_api_operator_controls.py -q`

---

### Task 4: Render the shared audit summary in research and operations UIs

**Files:**
- Modify: `apps/web/src/types/research.ts`
- Modify: `apps/web/src/types/api.ts`
- Modify: `apps/web/src/components/BacktestDecisionTable.tsx`
- Modify: `apps/web/src/components/StatusHero.tsx`
- Modify: `apps/web/src/styles.css`
- Test: `apps/web/src/components/BacktestDecisionTable.test.tsx`
- Test: `apps/web/src/components/StatusHero.test.tsx`

**Step 1: Write the failing tests**
- Assert research decision rows show provider/confidence/fallback details from the normalized audit summary
- Assert operations status hero shows the latest runtime strategy decision summary

**Step 2: Run test — confirm it fails**
Command: `npm --prefix apps/web test -- --run src/components/BacktestDecisionTable.test.tsx src/components/StatusHero.test.tsx`

**Step 3: Write minimal implementation**
- Extend frontend types with the normalized audit summary
- Render the summary in both research and operations surfaces
- Keep copy understandable for operator-facing usage

**Step 4: Run test — confirm it passes**
Command: `npm --prefix apps/web test -- --run src/components/BacktestDecisionTable.test.tsx src/components/StatusHero.test.tsx`

---

### Task 5: Verify and commit the Phase 5 change set

**Step 1: Run validation**
Command: `.venv/bin/ruff check src/domain/strategy/audit.py src/domain/strategy/ai.py src/domain/strategy/baseline.py src/services/backtest/models.py src/services/backtest/service.py apps/trader/runtime.py apps/trader/service.py apps/trader/control_plane.py apps/trader/oms.py apps/api/control_plane.py apps/research/snapshot.py tests/unit/test_ai_strategy.py tests/integration/test_api_research_snapshot.py tests/integration/test_trader_operator_runtime.py tests/integration/test_api_operator_controls.py`

Command: `.venv/bin/python -m pytest tests/unit/test_ai_strategy.py tests/integration/test_api_research_snapshot.py tests/integration/test_trader_operator_runtime.py tests/integration/test_api_operator_controls.py -q`

Command: `npm --prefix apps/web test -- --run src/components/BacktestDecisionTable.test.tsx src/components/StatusHero.test.tsx`

Command: `npm --prefix apps/web run check-types`

**Step 2: Commit**
`git add <phase-5 files> && git commit -m "feat: 完成 V2 Phase 5 AI 接缝与统一审计"`
