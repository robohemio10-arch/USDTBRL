from __future__ import annotations

from pathlib import Path

from smartcrypto.infra.database import SQLiteDatabase
from smartcrypto.runtime.audit import recent_critical_events
from smartcrypto.runtime.single_instance import DuplicateInstanceBlockedError, acquire_single_instance, release_single_instance


def _cfg(tmp_path: Path) -> tuple[dict, SQLiteDatabase]:
    db_path = tmp_path / "instance.sqlite"
    cfg = {
        "__run_id": "run-1",
        "storage": {"db_path": str(db_path)},
        "runtime": {"instance_lock_path": str(tmp_path / "runtime.lock.json"), "single_instance_enabled": True},
        "execution": {"mode": "paper"},
        "market": {"symbol": "USDT/BRL", "timeframe": "1m"},
    }
    return cfg, SQLiteDatabase(str(db_path))


def test_acquire_and_release_single_instance(tmp_path: Path) -> None:
    cfg, database = _cfg(tmp_path)
    payload = acquire_single_instance(cfg, database=database)
    assert Path(cfg["runtime"]["instance_lock_path"]).exists()
    assert payload["run_id"] == "run-1"
    release_single_instance(cfg, database=database)
    assert not Path(cfg["runtime"]["instance_lock_path"]).exists()


def test_duplicate_instance_is_blocked(tmp_path: Path) -> None:
    cfg, database = _cfg(tmp_path)
    acquire_single_instance(cfg, database=database)
    try:
        try:
            acquire_single_instance(cfg, database=database)
            assert False
        except DuplicateInstanceBlockedError:
            events = recent_critical_events(database, run_id="run-1", limit=10)
            assert any(event["event"] == "duplicate_instance_blocked" for event in events)
    finally:
        release_single_instance(cfg, database=database)
