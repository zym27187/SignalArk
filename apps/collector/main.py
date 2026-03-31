"""Collector scaffold entrypoint."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from src.config import get_settings
from src.shared.logging import configure_logging


def main() -> None:
    """Print a scaffold startup message for the collector runtime."""
    settings = get_settings()
    configure_logging(settings.log_level)

    payload = {
        "service": "collector",
        "env": settings.env,
        "exchange": settings.exchange,
        "symbols": settings.symbols,
        "started_at": datetime.now(UTC).isoformat(),
        "note": "Implement exchange adapters in Phase 3.",
    }
    print(json.dumps(payload, ensure_ascii=True))


if __name__ == "__main__":
    main()

