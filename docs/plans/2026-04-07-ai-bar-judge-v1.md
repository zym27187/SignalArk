# AI Bar Judge V1 Plan

## Goal

Add a minimal `ai_bar_judge_v1` strategy skeleton that plugs into the existing
strategy factory, research runner, and trader wiring without changing the
default `baseline_momentum_v1` runtime behavior.

## Scope

- Add a new strategy config file under `configs/strategies/`
- Add an AI-ready strategy implementation with a provider seam
- Keep the default provider deterministic and safe for local validation
- Extend `build_strategy(...)` and `Settings.primary_strategy_id`
- Add focused unit coverage for the new strategy and wiring

## Task Breakdown

1. Add a shared strategy audit model so multiple strategy implementations can
   expose the same decision-audit contract.
2. Implement `ai_bar_judge_v1` with:
   - lookback buffer per symbol
   - provider protocol for future LLM integration
   - safe heuristic stub provider for now
   - confidence gating and hold-to-`None` behavior
3. Add repo-local strategy config for `ai_bar_judge_v1`.
4. Extend strategy exports and factory wiring.
5. Extend settings typing to allow selecting `ai_bar_judge_v1`.
6. Add targeted unit tests for:
   - lookback warm-up
   - confidence filtering
   - signal/audit mapping
   - factory and trader autowiring
7. Run targeted validation and commit the task-only change set.
