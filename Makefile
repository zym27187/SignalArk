.PHONY: install format lint test test-unit test-migrations test-integration test-e2e api trader collector research mcp web-install web web-test web-build web-preview dev up

VENV ?= .venv
WEB_DIR := apps/web
PYTHON := $(VENV)/bin/python
PIP := $(PYTHON) -m pip
PYTEST := $(PYTHON) -m pytest
RUFF := $(VENV)/bin/ruff
UVICORN := $(VENV)/bin/uvicorn
NPM := npm --prefix $(WEB_DIR)

install:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

format:
	$(RUFF) format .

lint:
	$(RUFF) check .

test:
	$(PYTEST)

test-unit:
	$(PYTEST) tests/unit -q

test-migrations:
	$(PYTEST) tests/integration/test_db_persistence.py tests/integration/test_oms_persistence_flow.py tests/integration/test_paper_execution_flow.py tests/smoke/test_alembic_upgrade_smoke.py -q

test-integration:
	$(PYTEST) tests/integration tests/smoke -q

test-e2e:
	$(PYTEST) tests/e2e -q

api:
	$(UVICORN) apps.api.main:app --factory --host 0.0.0.0 --port 8000 --reload

trader:
	$(PYTHON) -m apps.trader.main

collector:
	$(PYTHON) -m apps.collector.main

research:
	$(PYTHON) -m apps.research $(ARGS)

mcp:
	$(PYTHON) -m apps.mcp $(ARGS)

web-install:
	$(NPM) install

web:
	$(NPM) run dev -- --host 127.0.0.1 --port 5173

web-test:
	$(NPM) run test

web-build:
	$(NPM) run build

web-preview:
	$(NPM) run preview -- --host 127.0.0.1 --port 4173

dev:
	bash ./scripts/run_dev_stack.sh

up:
	SIGNALARK_INCLUDE_TRADER=1 bash ./scripts/run_dev_stack.sh
