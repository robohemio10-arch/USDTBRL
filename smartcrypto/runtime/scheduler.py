from __future__ import annotations

from datetime import datetime, timedelta, timezone


def next_run_interval(default_seconds: int = 60) -> int:
    return max(1, int(default_seconds))


def next_run_at(*, now: datetime | None = None, interval_seconds: int = 60) -> datetime:
    current = now or datetime.now(timezone.utc)
    return current + timedelta(seconds=next_run_interval(interval_seconds))
