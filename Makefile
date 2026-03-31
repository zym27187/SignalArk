.PHONY: install format lint test test-unit test-integration test-e2e api trader collector

install:
	uv sync --all-extras

format:
	uv run ruff format .

lint:
	uv run ruff check .

test:
	uv run pytest

test-unit:
	uv run pytest tests/unit -q

test-integration:
	uv run pytest tests/integration -q

test-e2e:
	uv run pytest tests/e2e -q

api:
	uv run uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload

trader:
	uv run python -m apps.trader.main

collector:
	uv run python -m apps.collector.main

