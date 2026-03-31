"""Checkpoint helpers for collector recovery and historical backfill."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.domain.events import BarEvent
from src.domain.market import build_bar_stream_key, timeframe_to_timedelta
from src.shared.types import SHANGHAI_TIMEZONE, shanghai_now

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CHECKPOINT_PATH = ROOT_DIR / ".runtime" / "collector-bar-checkpoints.json"


def _ensure_shanghai_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("checkpoint datetimes must be timezone-aware")
    return parsed.astimezone(SHANGHAI_TIMEZONE)


class FileCollectorCheckpointStore:
    """Persist the last emitted final bar per stream to a local JSON file."""

    def __init__(self, path: Path = DEFAULT_CHECKPOINT_PATH) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def load_state(self) -> dict[str, dict[str, Any]]:
        if not self._path.exists():
            return {}

        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("collector checkpoint file must contain an object")

        return {
            str(stream_key): dict(value)
            for stream_key, value in payload.items()
            if isinstance(value, dict)
        }

    def next_start_time(self, exchange: str, symbol: str, timeframe: str) -> datetime | None:
        state = self.load_state()
        stream_key = build_bar_stream_key(exchange, symbol, timeframe)
        entry = state.get(stream_key)
        if entry is None:
            return None

        last_bar_start_time = entry.get("last_bar_start_time")
        if not isinstance(last_bar_start_time, str):
            return None

        return _ensure_shanghai_datetime(last_bar_start_time) + timeframe_to_timedelta(timeframe)

    def record(self, event: BarEvent) -> None:
        state = self.load_state()
        stream_key = build_bar_stream_key(event.exchange, event.symbol, event.timeframe)
        state[stream_key] = {
            "exchange": event.exchange,
            "symbol": event.symbol,
            "timeframe": event.timeframe,
            "last_bar_key": event.bar_key,
            "last_bar_start_time": event.bar_start_time.isoformat(),
            "last_bar_end_time": event.bar_end_time.isoformat(),
            "updated_at": shanghai_now().isoformat(),
        }

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(state, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
