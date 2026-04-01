from pathlib import Path

from smartcrypto.infra.database import SQLiteDatabase
from smartcrypto.runtime.ai_observability import record_ai_observation
from smartcrypto.runtime.audit import record_runtime_event
from smartcrypto.runtime.status import runtime_status_summary, status_payload
from smartcrypto.state.store import StateStore


def test_runtime_status_summary_contains_manifest_preflight_ai_and_critical_events(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.sqlite"
    database = SQLiteDatabase(str(db_path))
    store = StateStore(str(db_path), database=database)
    cfg = {
        "__config_path": str(tmp_path / "config" / "config.yml"),
        "__run_id": "run-test-001",
        "__feature_flags": {"research.shadow_mode_enabled": True},
        "__operational_manifest": {
            "config_path": str(tmp_path / "config" / "config.yml"),
            "mode": "paper",
            "symbol": "USDT/BRL",
            "timeframe": "1m",
            "db_path": str(db_path),
            "feature_flags_present": True,
            "feature_flags": {"research.shadow_mode_enabled": True},
            "build_id": "build-1",
            "run_id": "run-test-001",
            "boot_timestamp": "2026-03-26T12:00:00Z",
            "version": "",
            "config_hash": "abc123",
            "git_commit": "",
            "environment": "local",
            "preflight_status": "ok",
        },
        "__preflight": {"status": "ok"},
        "storage": {"db_path": str(db_path)},
        "market": {"symbol": "USDT/BRL", "timeframe": "1m"},
        "execution": {"mode": "paper"},
        "portfolio": {"initial_cash_brl": 1000.0},
        "dashboard": {"cache_dir": str(tmp_path / "cache")},
    }
    record_runtime_event(cfg, database, event="critical_tick_error", level="ERROR", details={"error": "boom"})
    record_ai_observation(
        cfg,
        database,
        cycle_id="cycle-1",
        ai_decision={"stage": "shadow", "effective_entry_gate": True, "position_action": "wait"},
        context={},
    )

    summary = runtime_status_summary(cfg, store, price=5.0)

    assert summary["manifest"]["mode"] == "paper"
    assert summary["run_id"] == "run-test-001"
    assert summary["preflight"]["status"] == "ok"
    assert summary["ai_summary"]["total"] == 1
    assert summary["critical_events"][0]["event"] == "critical_tick_error"


def test_status_payload_exposes_paper_panel_metrics(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.sqlite"
    database = SQLiteDatabase(str(db_path))
    store = StateStore(str(db_path), database=database)
    cfg = {
        "__config_path": str(tmp_path / "config" / "paper_7d.yml"),
        "storage": {"db_path": str(db_path)},
        "market": {"symbol": "USDT/BRL", "timeframe": "1m"},
        "execution": {"mode": "paper"},
        "portfolio": {"initial_cash_brl": 1000.0},
    }

    store.open_cycle(entry_price_brl=5.0, qty_usdt=10.0, brl_spent=50.0, regime="range")
    store.sync_open_cycle(qty_usdt=10.0, brl_spent=60.0, safety_count=2)
    store.update_position(
        status="open",
        qty_usdt=10.0,
        brl_spent=60.0,
        avg_price_brl=5.0,
        realized_pnl_brl=12.0,
        unrealized_pnl_brl=3.0,
        safety_count=2,
        regime="range",
    )
    store.close_latest_cycle(
        exit_price_brl=5.2,
        brl_received=62.0,
        pnl_brl=2.0,
        pnl_pct=3.33,
        safety_count=2,
        exit_reason="take_profit",
    )

    payload = status_payload(store, 5.3, cfg)
    panel = payload["paper_panel"]

    assert panel["entry_price_brl"] == 5.0
    assert panel["current_price_brl"] == 5.3
    assert panel["ramps_done"] == 2
    assert panel["closed_cycles"] == 1
    assert panel["realized_profit_brl"] == 12.0
    assert panel["total_spent_all_cycles_brl"] == 60.0
