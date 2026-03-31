"""Trader scaffold entrypoint."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from src.config import get_settings
from src.shared.logging import configure_logging


def main() -> None:
    """Print a scaffold startup message for the trader runtime."""
    settings = get_settings()
    configure_logging(settings.log_level)

    payload = {
        "service": "trader",
        "env": settings.env,
        "execution_mode": settings.execution_mode,
        "exchange": settings.exchange,
        "symbols": settings.symbols,
        "trader_run_id": str(uuid.uuid4()),
        "started_at": datetime.now(UTC).isoformat(),
        "note": "Implement event loop and OMS wiring in Phase 4 and Phase 5.",
    }
    print(json.dumps(payload, ensure_ascii=True))


if __name__ == "__main__":
    main()

