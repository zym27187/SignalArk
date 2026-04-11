# V2 Phase 1 Frontend Usability Implementation Plan

> **For implementer:** Use TDD throughout. Write failing test first. Watch it fail. Then implement.

**Goal:** Improve the Operations page so first-time users can understand system state and inspect symbol-layer status without changing runtime configuration.

**Architecture:** Keep `OperationsView` as the main landing page, add one read-only API endpoint for symbol inspection, and layer new explanatory UI components on top of the existing dashboard data flow. Avoid any runtime mutation path so Phase 1 stays within the agreed scope.

**Tech Stack:** FastAPI, React 19, TypeScript, Vitest, Testing Library, pytest

---

### Task 1: Add the symbol inspection API contract

**Files:**
- Modify: `apps/api/control_plane.py`
- Modify: `apps/api/main.py`
- Modify: `apps/web/src/types/api.ts`
- Modify: `apps/web/src/lib/api.ts`
- Test: `tests/integration/test_api_operator_controls.py`
- Test: `apps/web/src/lib/api.test.ts`

**Step 1: Write the failing tests**
- Add an API integration test that calls `/v1/symbols/inspect` with:
  - `600036.SH`
  - `000001.SZ`
  - `300750.SZ`
  - invalid input like `abc`
- Add a frontend API helper test that verifies the request path and query string.

**Step 2: Run test — confirm it fails**
Command: `.venv/bin/python -m pytest tests/integration/test_api_operator_controls.py -k symbol_inspect -v`
Expected: FAIL because the endpoint does not exist yet.

Command: `npm --prefix apps/web test -- --run src/lib/api.test.ts`
Expected: FAIL because the helper does not exist yet.

**Step 3: Write minimal implementation**
- Add `inspect_symbol_payload(...)` to `ApiControlPlaneService`
- Add `GET /v1/symbols/inspect`
- Add frontend type and `inspectSymbol(...)` helper

**Step 4: Run test — confirm it passes**
Command: `.venv/bin/python -m pytest tests/integration/test_api_operator_controls.py -k symbol_inspect -v`
Expected: PASS

Command: `npm --prefix apps/web test -- --run src/lib/api.test.ts`
Expected: PASS

### Task 2: Add a symbol inspector panel to the Operations page

**Files:**
- Create: `apps/web/src/components/SymbolInspectorPanel.tsx`
- Modify: `apps/web/src/components/views/OperationsView.tsx`
- Modify: `apps/web/src/App.test.tsx`
- Test: `apps/web/src/components/SymbolInspectorPanel.test.tsx`

**Step 1: Write the failing tests**
- Add a component test covering:
  - input + submit
  - normalized symbol display
  - supported/runtime layer rendering
  - runtime request confirmation text
- Add an app-level test ensuring the Operations page renders the new panel.

**Step 2: Run test — confirm it fails**
Command: `npm --prefix apps/web test -- --run src/components/SymbolInspectorPanel.test.tsx src/App.test.tsx`
Expected: FAIL because the component is missing.

**Step 3: Write minimal implementation**
- Build a form-driven panel with local input state
- Call `inspectSymbol(...)` on submit
- Render layer chips / definitions and the confirmation block
- Mount it into the Operations right rail

**Step 4: Run test — confirm it passes**
Command: `npm --prefix apps/web test -- --run src/components/SymbolInspectorPanel.test.tsx src/App.test.tsx`
Expected: PASS

### Task 3: Add glossary and explanation layers to the Operations page

**Files:**
- Create: `apps/web/src/components/TradingGlossaryPanel.tsx`
- Modify: `apps/web/src/components/StatusHero.tsx`
- Modify: `apps/web/src/components/StatusHero.test.tsx`
- Modify: `apps/web/src/components/views/OperationsView.tsx`

**Step 1: Write the failing tests**
- Extend `StatusHero` tests to assert user-facing impact text
- Add a glossary component test or cover glossary content through app rendering

**Step 2: Run test — confirm it fails**
Command: `npm --prefix apps/web test -- --run src/components/StatusHero.test.tsx src/App.test.tsx`
Expected: FAIL because the new explanation content is not rendered yet.

**Step 3: Write minimal implementation**
- Update `StatusHero` summary to include “can/can’t do” impact language
- Add a glossary panel with fixed beginner-friendly explanations
- Place glossary below the symbol inspector in the rail

**Step 4: Run test — confirm it passes**
Command: `npm --prefix apps/web test -- --run src/components/StatusHero.test.tsx src/App.test.tsx`
Expected: PASS

### Task 4: Improve control-action explanations and empty/degraded hints

**Files:**
- Modify: `apps/web/src/components/ControlPanel.tsx`
- Modify: `apps/web/src/components/ControlPanel.test.tsx`
- Modify: `apps/web/src/lib/format.ts`

**Step 1: Write the failing tests**
- Extend `ControlPanel` tests to assert risk/impact explanation text for dangerous actions
- Add assertions for the result explanation layer

**Step 2: Run test — confirm it fails**
Command: `npm --prefix apps/web test -- --run src/components/ControlPanel.test.tsx`
Expected: FAIL because the explanation text is not present yet.

**Step 3: Write minimal implementation**
- Add impact copy for `kill switch`, `cancel all`, and `protection mode`
- Make confirmation text and result text more user-facing

**Step 4: Run test — confirm it passes**
Command: `npm --prefix apps/web test -- --run src/components/ControlPanel.test.tsx`
Expected: PASS

### Task 5: Style, verify, and commit the Phase 1 change set

**Files:**
- Modify: `apps/web/src/styles.css`
- Modify: `apps/web/README.md` if needed

**Step 1: Run validation**
Command: `.venv/bin/python -m pytest tests/integration/test_api_operator_controls.py`
Expected: PASS

Command: `npm --prefix apps/web test -- --run src/components/SymbolInspectorPanel.test.tsx src/components/ControlPanel.test.tsx src/components/StatusHero.test.tsx src/App.test.tsx src/lib/api.test.ts`
Expected: PASS

Command: `npm --prefix apps/web run check-types`
Expected: PASS

**Step 2: Commit**
`git add <task files> && git commit -m "feat: 完成 V2 Phase 1 前端易用性与股票代码入口"`
