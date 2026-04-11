# V2 Phase 4 Research Standardization And Comparison Implementation Plan

> **For implementer:** Keep this scoped to stable research contracts and operator-facing comparison semantics. Prefer reusing existing backtest runner and snapshot serializers over adding a second reporting stack.

**Goal:** Standardize research modes, manifest, experiment summaries, and baseline-vs-candidate comparison so API, CLI, and frontend can explain research results directly.

**Architecture:** Extend the existing research snapshot contract with `mode`, `summary`, `experiments`, and `comparison`; keep sample semantics in `apps/research/analysis.py`; reuse experiment helpers for parameter scan and walk-forward; surface research readiness in symbol inspection.

**Tech Stack:** FastAPI, React 19, TypeScript, pytest, Vitest

---

### Task 1: Fix the Phase 4 research contract

**Files:**
- Modify: `apps/research/analysis.py`
- Modify: `apps/research/experiments.py`
- Modify: `apps/research/snapshot.py`
- Modify: `apps/research/main.py`
- Test: `tests/integration/test_research_cli.py`
- Test: `tests/integration/test_research_experiments_cli.py`

**Step 1: Write the failing tests**
- Assert exported research snapshots carry `mode`, `summary`, and standardized manifest fields
- Assert CLI experiment helpers still work after the new mode/summary helpers land

**Step 2: Run test — confirm it fails**
Command: `.venv/bin/python -m pytest tests/integration/test_research_cli.py tests/integration/test_research_experiments_cli.py -q`

**Step 3: Write minimal implementation**
- Add `ResearchMode`
- Add default parameter-scan grid and walk-forward window resolution
- Add snapshot serializers for summary / experiments / comparison

**Step 4: Run test — confirm it passes**
Command: `.venv/bin/python -m pytest tests/integration/test_research_cli.py tests/integration/test_research_experiments_cli.py -q`

---

### Task 2: Expose standardized research modes from the API

**Files:**
- Modify: `apps/api/control_plane.py`
- Modify: `apps/api/main.py`
- Test: `tests/integration/test_api_research_snapshot.py`

**Step 1: Write the failing tests**
- Assert `/v1/research/snapshot` supports `preview`, `evaluation`, `parameter_scan`, `walk_forward`
- Assert parameter scan returns experiment summary plus best-variant comparison
- Assert AI snapshot returns the same comparison contract shape

**Step 2: Run test — confirm it fails**
Command: `.venv/bin/python -m pytest tests/integration/test_api_research_snapshot.py -q`

**Step 3: Write minimal implementation**
- Map API mode to preview/evaluation sample purpose
- Keep one baseline run result as canonical snapshot root
- Attach experiment summary and comparison only when needed

**Step 4: Run test — confirm it passes**
Command: `.venv/bin/python -m pytest tests/integration/test_api_research_snapshot.py -q`

---

### Task 3: Make research readiness and mode semantics visible in the frontend

**Files:**
- Modify: `apps/web/src/types/research.ts`
- Modify: `apps/web/src/types/api.ts`
- Modify: `apps/web/src/lib/api.ts`
- Modify: `apps/web/src/hooks/use-research-data.ts`
- Modify: `apps/web/src/components/views/ResearchView.tsx`
- Modify: `apps/web/src/components/SymbolInspectorPanel.tsx`
- Test: `apps/web/src/hooks/use-research-data.test.tsx`
- Test: `apps/web/src/hooks/use-ai-research-data.test.tsx`
- Test: `apps/web/src/components/SymbolInspectorPanel.test.tsx`
- Test: `apps/web/src/App.test.tsx`

**Step 1: Write the failing tests**
- Assert research mode selection passes the correct API `mode`
- Assert research page can render standardized comparison and experiment summaries
- Assert symbol inspector shows research readiness explicitly

**Step 2: Run test — confirm it fails**
Command: `npm --prefix apps/web test -- --run src/hooks/use-ai-research-data.test.tsx src/hooks/use-research-data.test.tsx src/components/SymbolInspectorPanel.test.tsx src/App.test.tsx`

**Step 3: Write minimal implementation**
- Promote baseline sample toggle to a four-mode research toggle
- Render API-provided `summary`, `experiments`, and `comparison`
- Add `research_status` to symbol inspection rendering

**Step 4: Run test — confirm it passes**
Command: `npm --prefix apps/web test -- --run src/hooks/use-ai-research-data.test.tsx src/hooks/use-research-data.test.tsx src/components/SymbolInspectorPanel.test.tsx src/App.test.tsx`

---

### Task 4: Verify and commit the Phase 4 change set

**Step 1: Run validation**
Command: `.venv/bin/ruff check apps/research/analysis.py apps/research/experiments.py apps/research/snapshot.py apps/research/main.py apps/api/control_plane.py apps/api/main.py tests/integration/test_api_research_snapshot.py tests/integration/test_api_operator_controls.py tests/integration/test_research_cli.py`

Command: `.venv/bin/python -m pytest tests/integration/test_api_research_snapshot.py tests/integration/test_api_operator_controls.py tests/integration/test_research_cli.py tests/integration/test_research_experiments_cli.py tests/unit/test_backtest_service.py -q`

Command: `npm --prefix apps/web test -- --run src/hooks/use-ai-research-data.test.tsx src/lib/api.test.ts src/hooks/use-research-data.test.tsx src/components/SymbolInspectorPanel.test.tsx src/App.test.tsx`

Command: `npm --prefix apps/web run check-types`

**Step 2: Commit**
`git add <phase-4 files> && git commit -m "feat: 完成 V2 Phase 4 research 标准化与对照能力"`
