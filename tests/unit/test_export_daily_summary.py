from __future__ import annotations

import json
from pathlib import Path

from scripts.export_daily_summary import build_daily_summary, export_daily_summary
from smartcrypto.infra.database import SQLiteDatabase
from smartcrypto.runtime.ai_observability import record_ai_observation
from smartcrypto.runtime.audit import record_cycle_audit, record_runtime_event
from smartcrypto.runtime.runtime_manifest import persist_runtime_manifest
from smartcrypto.state.store import StateStore


def _cfg(tmp_path: Path) -> dict:
    db_path = tmp_path / "summary.sqlite"
    return {
        "__config_path": str(tmp_path / "config" / "config.yml"),
        "__run_id": "run-123",
        "storage": {"db_path": str(db_path)},
        "market": {"symbol": "USDT/BRL", "timeframe": "1m"},
        "execution": {"mode": "paper"},
        "runtime": {"retention_days": 7, "export_dir": str(tmp_path / "exports")},
        "__operational_manifest": {
            "run_id": "run-123",
            "boot_timestamp": "2026-03-26T00:00:00+00:00",
            "mode": "paper",
        },
    }


def test_build_daily_summary_contains_run_id(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    db_path = Path(cfg["storage"]["db_path"])
    database = SQLiteDatabase(str(db_path))
    store = StateStore(str(db_path), database=database)
    store.add_snapshot(
        last_price_brl=5.0,
        equity_brl=1000.0,
        cash_brl=1000.0,
        pos_value_brl=0.0,
        realized_pnl_brl=0.0,
        unrealized_pnl_brl=0.0,
        drawdown_pct=0.0,
        regime="range",
        meta={},
    )
    persist_runtime_manifest(cfg, cfg["__operational_manifest"], database=database)
    record_cycle_audit(
        cfg,
        database,
        cycle_id="cycle-1",
        started_at="2026-03-26T00:01:00+00:00",
        finished_at="2026-03-26T00:01:05+00:00",
        status="ok",
        event="tick_completed",
        details={},
    )
    record_runtime_event(cfg, database, event="bot_tick_error", level="ERROR", details={"run_id": "run-123"})
    record_ai_observation(
        cfg,
        database,
        cycle_id="cycle-1",
        baseline_decision={"is_real": True, "entry_gate": True, "position_action": "wait"},
        ai_decision={"stage": "shadow", "effective_entry_gate": False, "position_action": "wait"},
        context={},
    )
    summary = build_daily_summary(cfg)
    assert summary["run_id"] == "run-123"
    assert summary["cycles"] == 1
    assert summary["critical_events"] == 1
    assert summary["ai_decisions"] == 1


def test_export_daily_summary_writes_file(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    output, _summary = export_daily_summary(cfg)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["run_id"] == "run-123"
