from smartcrypto.state.store import StateStore


def test_reserved_balances_from_active_dispatch_locks(tmp_path):
    db = str(tmp_path / "test.sqlite")
    store = StateStore(db)

    store.upsert_dispatch_lock(
        bot_order_id="b1",
        side="buy",
        reason="entry",
        order_type="limit",
        status="pending_submit",
        requested_brl_value=100.0,
    )
    store.upsert_dispatch_lock(
        bot_order_id="s1",
        side="sell",
        reason="exit",
        order_type="limit",
        status="submitted",
        requested_qty_usdt=2.5,
    )

    r = store.get_reserved_balances()
    assert r["BRL"] == 100.0
    assert r["USDT"] == 2.5
