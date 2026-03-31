.PHONY: install format lint test test-unit test-integration test-e2e api trader collector

VENV ?= .venv
PYTHON := $(VENV)/bin/python
PIP := $(PYTHON) -m pip
PYTEST := $(PYTHON) -m pytest
RUFF := $(VENV)/bin/ruff
UVICORN := $(VENV)/bin/uvicorn

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
