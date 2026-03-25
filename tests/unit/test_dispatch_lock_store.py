from pathlib import Path

from smartcrypto.infra.database import SQLiteDatabase
from smartcrypto.state.dispatch_locks import DispatchLockStore
from smartcrypto.state.migrations import apply_migrations


def test_dispatch_lock_store_updates_and_clears_stale_entries(tmp_path: Path) -> None:
    db = SQLiteDatabase(str(tmp_path / "locks.sqlite"))
    with db.connect() as conn:
        apply_migrations(conn)

    store = DispatchLockStore(
        db,
        lambda: "2026-03-24T12:00:00+00:00",
        ("pending_submit", "submit_unknown", "submitted", "recovered_open"),
    )
    store.upsert(
        bot_order_id="ord-1",
        side="buy",
        reason="entry",
        order_type="limit",
        details={"attempt": 1},
    )
    store.update("ord-1", status="submitted", details={"exchange_order_id": "123"})

    current = store.get("ord-1")
    assert current is not None
    assert current["status"] == "submitted"
    assert current["details"]["attempt"] == 1
    assert current["details"]["exchange_order_id"] == "123"

    with db.connect() as conn:
        conn.execute(
            "update order_dispatch_locks set updated_at = ? where bot_order_id = ?",
            ("2020-01-01T00:00:00+00:00", "ord-1"),
        )

    cleared = store.clear_stale(max_age_seconds=1)

    assert cleared == 1
    assert store.get("ord-1")["status"] == "stale"
