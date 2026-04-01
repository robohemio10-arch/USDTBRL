from __future__ import annotations

from pathlib import Path

import pytest

from smartcrypto.infra.database import SQLiteDatabase
from smartcrypto.runtime.ai_observability import recent_ai_observations
from smartcrypto.runtime.audit import read_recent_cycle_audit, read_recent_runtime_events
from smartcrypto.runtime.lifecycle import CycleResult, run_loop
from smartcrypto.runtime.single_instance import DuplicateInstanceBlockedError
from smartcrypto.state.store import StateStore


class _StoreStub:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict | None]] = []
        self.flags: dict[str, object] = {}

    def add_event(self, level: str, event: str, details: dict | None = None) -> None:
        self.events.append((level, event, details))

    def set_flag(self, key: str, value: object) -> None:
        self.flags[key] = value

    def get_flag(self, key: str, default: object = None) -> object:
        return self.flags.get(key, default)


def test_run_loop_records_cycle_audit_ai_observability_and_flags(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.sqlite"
    database = SQLiteDatabase(str(db_path))
    store = _StoreStub()
    cfg = {
        "__run_id": "run-test-001",
        "runtime": {
            "max_iterations": 1,
            "instance_lock_path": str(tmp_path / "lock.json"),
        },
        "__operational_manifest": {"run_id": "run-test-001"},
    }

    def _tick_once() -> CycleResult:
        return CycleResult(
            cycle_id="cycle-1",
            event="tick_completed",
            status="ok",
            started_at="2026-03-26T12:00:00Z",
            finished_at="2026-03-26T12:00:10Z",
            ai_decision={"stage": "shadow", "effective_entry_gate": False, "position_action": "wait"},
            baseline_decision={"is_real": True, "entry_gate": True, "position_action": "wait"},
        )

    completed = run_loop(
        cfg,
        database=database,
        store=store,
        tick_once=_tick_once,
        sleep_fn=lambda _value: None,
    )

    cycles = read_recent_cycle_audit(database, limit=5)
    ai_rows = recent_ai_observations(database, limit=5)

    assert completed == 1
    assert len(cycles) == 1
    assert len(ai_rows) == 1
    assert store.flags["runtime_cycle_count"] == 1
    assert store.flags["runtime_last_cycle_id"] == "cycle-1"


def test_run_loop_records_unexpected_shutdown_on_keyboard_interrupt(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.sqlite"
    database = SQLiteDatabase(str(db_path))
    store = _StoreStub()
    cfg = {
        "__run_id": "run-test-001",
        "runtime": {
            "max_iterations": 1,
            "instance_lock_path": str(tmp_path / "lock.json"),
        },
    }

    def _tick_once() -> CycleResult:
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        run_loop(
            cfg,
            database=database,
            store=store,
            tick_once=_tick_once,
            sleep_fn=lambda _value: None,
        )

    events = read_recent_runtime_events(database, limit=5)
    assert events.iloc[0]["event"] == "unexpected_shutdown"


def test_run_loop_surfaces_duplicate_instance_block(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.sqlite"
    database = SQLiteDatabase(str(db_path))
    cfg = {
        "__run_id": "run-test-001",
        "runtime": {
            "max_iterations": 1,
            "instance_lock_path": str(tmp_path / "lock.json"),
        },
    }

    store = StateStore(str(db_path), database=database)
    Path(cfg["runtime"]["instance_lock_path"]).write_text("busy", encoding="utf-8")

    def _tick_once() -> CycleResult:
        return CycleResult(
            cycle_id="cycle-1",
            event="tick_completed",
            status="ok",
            started_at="2026-03-26T12:00:00Z",
            finished_at="2026-03-26T12:00:01Z",
        )

    with pytest.raises(DuplicateInstanceBlockedError):
        run_loop(
            cfg,
            database=database,
            store=store,
            tick_once=_tick_once,
            sleep_fn=lambda _value: None,
        )