import json
from pathlib import Path

from smartcrypto.infra.database import SQLiteDatabase
from smartcrypto.state.bot_events import BotEventStore
from smartcrypto.state.migrations import apply_migrations
from smartcrypto.state.reconciliation_audit import ReconciliationAuditStore
from smartcrypto.state.snapshots import SnapshotStore


def test_snapshot_and_audit_stores_write_rows(tmp_path: Path) -> None:
    db = SQLiteDatabase(str(tmp_path / "snapshot.sqlite"))
    with db.connect() as conn:
        apply_migrations(conn)

    snapshots = SnapshotStore(db, lambda: "2026-03-24T12:00:00+00:00")
    bot_events = BotEventStore(db, lambda: "2026-03-24T12:01:00+00:00")
    audit = ReconciliationAuditStore(db, lambda: "2026-03-24T12:02:00+00:00")

    snapshots.add(
        last_price_brl=5.2,
        equity_brl=1002.5,
        cash_brl=950.0,
        pos_value_brl=52.5,
        realized_pnl_brl=1.0,
        unrealized_pnl_brl=2.5,
        drawdown_pct=0.3,
        regime="bullish",
        meta={"source": "unit"},
    )
    bot_events.add("info", "snapshot_written", {"snapshot_id": 1})
    audit.add(
        action="noop",
        local_status="flat",
        local_qty_usdt=0.0,
        exchange_qty_usdt=0.0,
        exchange_open_orders=0,
        details={"reason": "clean"},
    )

    snapshot_row = db.read_sql("select regime, meta_json from snapshots").to_dict(orient="records")[0]
    event_row = db.read_sql("select level, event, details_json from bot_events").to_dict(orient="records")[0]
    audit_row = db.read_sql("select action, details_json from reconciliation_audit").to_dict(orient="records")[0]

    assert snapshot_row["regime"] == "bullish"
    assert json.loads(snapshot_row["meta_json"]) == {"source": "unit"}
    assert event_row["event"] == "snapshot_written"
    assert json.loads(event_row["details_json"]) == {"snapshot_id": 1}
    assert audit_row["action"] == "noop"
    assert json.loads(audit_row["details_json"]) == {"reason": "clean"}
