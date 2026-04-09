#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ALEMBIC_CMD=("$ROOT_DIR/.venv/bin/alembic" "-c" "$ROOT_DIR/migrations/alembic.ini" "upgrade" "head")
API_CMD=("$ROOT_DIR/.venv/bin/uvicorn" "apps.api.main:app" "--factory" "--host" "0.0.0.0" "--port" "8000" "--reload")
TRADER_CMD=("$ROOT_DIR/.venv/bin/python" "-m" "apps.trader.main")
WEB_CMD=("npm" "--prefix" "$ROOT_DIR/apps/web" "run" "dev" "--" "--host" "127.0.0.1" "--port" "5173")
INCLUDE_TRADER="${SIGNALARK_INCLUDE_TRADER:-0}"
PIDS=()

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM

  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done

  wait "${PIDS[@]:-}" 2>/dev/null || true
  exit "$exit_code"
}

require_ready_stack() {
  if [[ ! -x "$ROOT_DIR/.venv/bin/alembic" ]]; then
    echo "Missing $ROOT_DIR/.venv/bin/alembic. Run 'make install' first." >&2
    exit 1
  fi

  if [[ ! -x "$ROOT_DIR/.venv/bin/uvicorn" ]]; then
    echo "Missing $ROOT_DIR/.venv/bin/uvicorn. Run 'make install' first." >&2
    exit 1
  fi

  if [[ ! -f "$ROOT_DIR/apps/web/package.json" ]]; then
    echo "Missing apps/web/package.json. The frontend app is not available." >&2
    exit 1
  fi

  if [[ ! -d "$ROOT_DIR/apps/web/node_modules" ]]; then
    echo "Missing apps/web/node_modules. Run 'make web-install' first." >&2
    exit 1
  fi

  if [[ -z "${SIGNALARK_POSTGRES_DSN:-}" ]] && ! grep -Eq '^\s*SIGNALARK_POSTGRES_DSN=' "$ROOT_DIR/.env" 2>/dev/null; then
    echo "Missing SIGNALARK_POSTGRES_DSN in the environment or .env. The API will fail-fast without it." >&2
    exit 1
  fi
}

apply_migrations() {
  echo "Applying database migrations"
  "${ALEMBIC_CMD[@]}"
}

wait_for_first_exit() {
  while true; do
    for pid in "${PIDS[@]}"; do
      if ! kill -0 "$pid" 2>/dev/null; then
        wait "$pid"
        return $?
      fi
    done
    sleep 1
  done
}

main() {
  require_ready_stack

  trap cleanup EXIT INT TERM
  cd "$ROOT_DIR"
  apply_migrations

  echo "Starting SignalArk API on http://127.0.0.1:8000"
  "${API_CMD[@]}" &
  PIDS+=("$!")

  echo "Starting SignalArk web console on http://127.0.0.1:5173"
  "${WEB_CMD[@]}" &
  PIDS+=("$!")

  if [[ "$INCLUDE_TRADER" == "1" ]]; then
    echo "Starting SignalArk trader runtime"
    "${TRADER_CMD[@]}" &
    PIDS+=("$!")
  fi

  wait_for_first_exit
}

main "$@"
