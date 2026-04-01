from pathlib import Path
from typing import Any

from smartcrypto.runtime.audit import read_recent_cycle_audit, summarize_runtime_session
from smartcrypto.runtime.lifecycle import CycleResult, run_loop


class _StoreStub:
    def __init__(self) -> None:
        self.flags: dict[str, Any] = {}
        self.events: list[tuple[str, str, dict[str, Any] | None]] = []

    def set_flag(self, key: str, value: Any) -> None:
        self.flags[key] = value

    def get_flag(self, key: str, default: Any = None) -> Any:
        return self.flags.get(key, default)

    def add_event(self, level: str, event: str, details: dict[str, Any] | None = None) -> None:
        self.events.append((level, event, details))


class _Database:
    def __init__(self, path: str) -> None:
        from smartcrypto.infra.database import SQLiteDatabase

        self._db = SQLiteDatabase(path)

    def connect(self):
        return self._db.connect()


def test_runtime_tick_cycle_records_session_summary(tmp_path: Path) -> None:
    database = _Database(str(tmp_path / "runtime.sqlite"))
    store = _StoreStub()
    cfg = {
        "__run_id": "run-test-001",
        "__operational_manifest": {
            "run_id": "run-test-001",
            "boot_timestamp": "2026-03-26T12:00:00Z",
        },
        "runtime": {
            "max_iterations": 1,
            "instance_lock_path": str(tmp_path / "runtime.lock.json"),
        },
        "market": {"symbol": "USDT/BRL", "timeframe": "1m"},
        "execution": {"mode": "paper"},
        "runtime": {
            "max_iterations": 1,
            "instance_lock_path": str(tmp_path / "runtime.lock.json"),
        },
    }

    def _tick_once() -> CycleResult:
        return CycleResult(
            cycle_id="cycle-1",
            event="tick_completed",
            status="ok",
            started_at="2026-03-26T12:00:00Z",
            finished_at="2026-03-26T12:00:01Z",
            price_brl=5.0,
            equity_brl=1000.0,
        )

    completed = run_loop(
        cfg,
        database=database,
        store=store,
        tick_once=_tick_once,
        sleep_fn=lambda _value: None,
    )

    cycles = read_recent_cycle_audit(database, limit=10)
    summary = summarize_runtime_session(
        database,
        run_id="run-test-001",
        boot_timestamp="2026-03-26T12:00:00Z",
    )

    assert completed == 1
    assert len(cycles) == 1
    assert summary["cycle_count"] == 1
    assert summary["run_id"] == "run-test-001"
    assert store.flags["runtime_last_cycle_id"] == "cycle-1"