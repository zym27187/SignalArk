# V2 Phase 3 Diagnostics And Degraded Mode Implementation Plan

> **For implementer:** Keep this scoped to the Phase 3 contract. Prefer reusing existing control-plane payloads over inventing a new diagnostics aggregation layer.

**Goal:** Make degraded mode and diagnostics semantics explicit and consistent across API, MCP, frontend, and trader-facing status views.

**Architecture:** Add one canonical `degraded_mode` payload in `ApiControlPlaneService`, embed it into status/runtime bar/replay payloads, expose dedicated HTTP + MCP read paths, and render the resulting fact directly in existing frontend surfaces.

**Tech Stack:** FastAPI, MCP stdio server, React 19, TypeScript, pytest, Vitest

---

### Task 1: Add the degraded-mode API contract

**Files:**
- Modify: `apps/api/control_plane.py`
- Modify: `apps/api/main.py`
- Modify: `src/config/shared_contracts.py`
- Modify: `apps/web/src/types/api.ts`
- Modify: `apps/web/src/lib/api.ts`
- Test: `tests/integration/test_api_empty_db_responses.py`
- Test: `tests/integration/test_api_market_endpoints.py`
- Test: `tests/integration/test_reconciliation_api_diagnostics.py`
- Test: `tests/unit/test_shared_contracts.py`
- Test: `apps/web/src/lib/api.test.ts`

**Step 1: Write the failing tests**
- Assert a dedicated `/v1/diagnostics/degraded-mode` endpoint exists
- Assert `status`, `runtime-bars`, and `replay-events` payloads embed the same `degraded_mode`
- Assert degraded mode distinguishes `fixture`, `missing`, and stale scenarios

**Step 2: Run test — confirm it fails**
Command: `.venv/bin/python -m pytest tests/integration/test_api_empty_db_responses.py tests/integration/test_api_market_endpoints.py tests/integration/test_reconciliation_api_diagnostics.py tests/unit/test_shared_contracts.py -q`

**Step 3: Write minimal implementation**
- Add one reusable degraded-mode builder
- Add `/v1/diagnostics/degraded-mode`
- Update shared contract and TS types

**Step 4: Run test — confirm it passes**
Command: `.venv/bin/python -m pytest tests/integration/test_api_empty_db_responses.py tests/integration/test_api_market_endpoints.py tests/integration/test_reconciliation_api_diagnostics.py tests/unit/test_shared_contracts.py -q`

---

### Task 2: Align MCP diagnostics tools

**Files:**
- Modify: `apps/mcp/server.py`
- Test: `tests/unit/test_signalark_mcp_server.py`

**Step 1: Write the failing tests**
- Assert `tools/list` contains `get_runtime_bars` and `get_degraded_mode`
- Assert both tools return the same payload shape as the API control-plane service

**Step 2: Run test — confirm it fails**
Command: `.venv/bin/python -m pytest tests/unit/test_signalark_mcp_server.py -q`

**Step 3: Write minimal implementation**
- Add typed MCP tool arguments
- Delegate directly to `market_runtime_bars_payload` and `degraded_mode_payload`

**Step 4: Run test — confirm it passes**
Command: `.venv/bin/python -m pytest tests/unit/test_signalark_mcp_server.py -q`

---

### Task 3: Expose diagnostics in the frontend without silent fallback

**Files:**
- Modify: `apps/web/src/components/StatusHero.tsx`
- Modify: `apps/web/src/components/EventTimeline.tsx`
- Modify: `apps/web/src/components/views/MarketView.tsx`
- Modify: `apps/web/src/hooks/use-market-data.ts`
- Modify: `apps/web/src/lib/format.ts`
- Test: `apps/web/src/components/StatusHero.test.tsx`
- Test: `apps/web/src/hooks/use-market-data.test.tsx`
- Test: `apps/web/src/App.test.tsx`

**Step 1: Write the failing tests**
- `StatusHero` should show degraded mode conclusion, impact, and action
- `MarketView` / app-level rendering should surface degraded source state explicitly
- replay timeline should render `reason_code` when available

**Step 2: Run test — confirm it fails**
Command: `npm --prefix apps/web test -- --run src/components/StatusHero.test.tsx src/hooks/use-market-data.test.tsx src/App.test.tsx`

**Step 3: Write minimal implementation**
- Render degraded mode in `StatusHero`
- Render explicit data-source / degraded messaging in market view
- Show replay-event `reason_code`

**Step 4: Run test — confirm it passes**
Command: `npm --prefix apps/web test -- --run src/components/StatusHero.test.tsx src/hooks/use-market-data.test.tsx src/App.test.tsx`

---

### Task 4: Verify and commit Phase 3 change set

**Step 1: Run validation**
Command: `.venv/bin/python -m pytest tests/integration/test_api_empty_db_responses.py tests/integration/test_api_market_endpoints.py tests/integration/test_reconciliation_api_diagnostics.py tests/unit/test_signalark_mcp_server.py tests/unit/test_shared_contracts.py -q`

Command: `npm --prefix apps/web test -- --run src/lib/api.test.ts src/components/StatusHero.test.tsx src/hooks/use-market-data.test.tsx src/App.test.tsx`

Command: `npm --prefix apps/web run check-types`

**Step 2: Commit**
`git add <phase-3 files> && git commit -m "feat: 完成 V2 Phase 3 诊断统一与降级模式表达"`
