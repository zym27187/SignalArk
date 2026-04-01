"""Replay persisted event logs for minimal reconciliation diagnostics."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from uuid import UUID

from apps.trader.reconciliation import SessionFactoryBackedReconciliationStore
from src.config import get_settings
from src.domain.reconciliation import ReplayEventFilters
from src.infra.db import create_database_engine, create_session_factory
from src.shared.types import SHANGHAI_TIMEZONE


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-time", type=_parse_datetime)
    parser.add_argument("--end-time", type=_parse_datetime)
    parser.add_argument("--trader-run-id", type=UUID)
    parser.add_argument("--account-id")
    parser.add_argument("--symbol")
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    settings = get_settings()
    engine = create_database_engine(settings=settings)
    try:
        session_factory = create_session_factory(engine)
        store = SessionFactoryBackedReconciliationStore(session_factory)
        filters = ReplayEventFilters(
            start_time=args.start_time,
            end_time=args.end_time,
            trader_run_id=args.trader_run_id,
            account_id=args.account_id or settings.account_id,
            symbol=args.symbol,
            limit=args.limit,
        )
        events = store.replay_events(filters)
        print(
            json.dumps(
                {
                    "filters": filters.model_dump(mode="json"),
                    "count": len(events),
                    "events": [event.model_dump(mode="json") for event in events],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        engine.dispose()


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=SHANGHAI_TIMEZONE)
    return parsed.astimezone(SHANGHAI_TIMEZONE)


if __name__ == "__main__":
    main()
