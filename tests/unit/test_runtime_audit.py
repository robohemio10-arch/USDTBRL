from pathlib import Path

from smartcrypto.infra.database import SQLiteDatabase
from smartcrypto.runtime.audit import recent_critical_events, record_cycle_audit, record_runtime_event, summarize_runtime_session


def test_runtime_audit_tracks_session_and_critical_events(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.sqlite"
    database = SQLiteDatabase(str(db_path))
    cfg = {
        "__run_id": "run-test-001",
        "__boot_timestamp": "2026-03-26T12:00:00Z",
        "__operational_manifest": {"run_id": "run-test-001", "boot_timestamp": "2026-03-26T12:00:00Z"},
    }

    record_runtime_event(cfg, database, event="preflight_failed", level="ERROR", details={"reason": "unit"})
    record_cycle_audit(
        cfg,
        database,
        cycle_id="cycle-1",
        started_at="2026-03-26T12:00:00Z",
        finished_at="2026-03-26T12:00:10Z",
        status="ok",
        event="tick_completed",
        details={"run_id": "run-test-001"},
    )

    critical = recent_critical_events(database, run_id="run-test-001", limit=5)
    summary = summarize_runtime_session(
        database,
        run_id="run-test-001",
        boot_timestamp="2026-03-26T12:00:00Z",
    )

    assert critical[0]["event"] == "preflight_failed"
    assert summary["run_id"] == "run-test-001"
    assert summary["cycle_count"] == 1
    assert summary["critical_event_count"] == 1