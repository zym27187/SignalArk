.PHONY: install format lint test test-unit test-integration test-e2e api trader collector web-install web web-build web-preview dev

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

test-integration:
	$(PYTEST) tests/integration -q

test-e2e:
	$(PYTEST) tests/e2e -q

api:
	$(UVICORN) apps.api.main:app --host 0.0.0.0 --port 8000 --reload

trader:
	$(PYTHON) -m apps.trader.main

collector:
	$(PYTHON) -m apps.collector.main

web-install:
	$(NPM) install

web:
	$(NPM) run dev -- --host 127.0.0.1 --port 5173

web-build:
	$(NPM) run build

web-preview:
	$(NPM) run preview -- --host 127.0.0.1 --port 4173

dev:
	bash ./scripts/run_dev_stack.sh
