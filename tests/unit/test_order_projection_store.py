from pathlib import Path

from smartcrypto.infra.database import SQLiteDatabase
from smartcrypto.state.migrations import apply_migrations
from smartcrypto.state.order_projections import OrderProjectionStore


def test_order_projection_store_replaces_planned_and_pending(tmp_path: Path) -> None:
    db = SQLiteDatabase(str(tmp_path / "projection.sqlite"))
    with db.connect() as conn:
        apply_migrations(conn)

    store = OrderProjectionStore(db, lambda: "2026-03-24T12:00:00+00:00")
    orders = [
        {
            "side": "buy",
            "order_type": "limit",
            "price_brl": 5.1,
            "qty_usdt": 10.0,
            "brl_value": 51.0,
            "reason": "entry",
            "status": "planned",
        }
    ]

    store.replace_planned_orders(orders)

    planned = db.read_sql("select side, order_type, reason from planned_orders")
    pending = db.read_sql("select side, order_type, reason from pending_orders")

    assert planned.to_dict(orient="records") == [{"side": "buy", "order_type": "limit", "reason": "entry"}]
    assert pending.to_dict(orient="records") == [{"side": "buy", "order_type": "limit", "reason": "entry"}]
