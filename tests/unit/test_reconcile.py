from smartcrypto.execution.reconcile import (
    is_bot_managed_exchange_order,
    live_reconcile_qty_tolerance,
    map_exchange_order_state,
)


def test_map_exchange_order_state_partial_canceled() -> None:
    assert (
        map_exchange_order_state({"status": "CANCELED", "executed_qty_usdt": 1.0})
        == "partial_canceled"
    )


def test_is_bot_managed_exchange_order_by_prefix() -> None:
    assert is_bot_managed_exchange_order(
        {"client_order_id": "SC-123"},
        known_exchange_ids=set(),
        known_client_ids=set(),
    )


def test_live_reconcile_qty_tolerance_without_exchange() -> None:
    cfg = {"runtime": {"reconcile_qty_tolerance_usdt": 0.1234}}

    assert live_reconcile_qty_tolerance(cfg) == 0.1234
