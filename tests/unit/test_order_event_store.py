from pathlib import Path

from smartcrypto.infra.database import SQLiteDatabase
from smartcrypto.state.migrations import apply_migrations
from smartcrypto.state.order_events import OrderEventStore


def test_order_event_store_returns_latest_state_per_order(tmp_path: Path) -> None:
    db = SQLiteDatabase(str(tmp_path / "events.sqlite"))
    with db.connect() as conn:
        apply_migrations(conn)

    store = OrderEventStore(db, lambda: "2026-03-24T12:00:00+00:00")
    store.add(
        bot_order_id="ord-1",
        state="submitted",
        side="buy",
        order_type="limit",
        event_time="2026-03-24T12:00:00+00:00",
    )
    store.add(
        bot_order_id="ord-1",
        state="filled",
        side="buy",
        order_type="limit",
        event_time="2026-03-24T12:01:00+00:00",
    )
    store.add(
        bot_order_id="ord-2",
        state="cancelled",
        side="sell",
        order_type="limit",
        event_time="2026-03-24T12:02:00+00:00",
    )

    frame = store.latest_states_df(limit=10)

    assert frame.to_dict(orient="records")[0]["bot_order_id"] == "ord-2"
    latest_ord_1 = next(row for row in frame.to_dict(orient="records") if row["bot_order_id"] == "ord-1")
    assert latest_ord_1["state"] == "filled"
