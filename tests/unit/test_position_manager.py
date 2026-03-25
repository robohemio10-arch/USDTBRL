from pathlib import Path

from smartcrypto.state.position_manager import PositionManager
from smartcrypto.state.store import StateStore


def test_position_manager_open_sync_and_close_cycle(tmp_path: Path) -> None:
    store = StateStore(str(tmp_path / "state.sqlite"))
    manager = PositionManager(store)

    opened = manager.open_position(
        regime="sideways",
        entry_price_brl=5.2,
        qty_usdt=10.0,
        brl_spent=52.0,
        tp_price_brl=5.4,
        stop_price_brl=5.0,
    )

    assert opened.status == "open"
    assert opened.qty_usdt == 10.0
    assert manager.has_open_position() is True

    synced = manager.sync_position(
        qty_usdt=12.0,
        brl_spent=62.4,
        avg_price_brl=5.2,
        safety_count=1,
    )

    assert synced.qty_usdt == 12.0
    assert synced.safety_count == 1

    updated = manager.update_unrealized_pnl(mark_price_brl=5.5)
    assert round(updated.unrealized_pnl_brl, 2) == 3.6

    closed = manager.close_position(
        exit_price_brl=5.6,
        brl_received=67.2,
        fee_brl=0.2,
        exit_reason="tp_hit",
    )

    assert closed.status == "flat"
    assert round(closed.realized_pnl_brl, 2) == 4.6
    cycles = store.read_df("cycles")
    assert cycles.iloc[0]["status"] == "closed"


def test_position_manager_cash_available_and_mark_to_market(tmp_path: Path) -> None:
    store = StateStore(str(tmp_path / "state_cash.sqlite"))
    manager = PositionManager(store)
    manager.open_position(
        regime="sideways",
        entry_price_brl=5.0,
        qty_usdt=10.0,
        brl_spent=50.0,
    )
    store.update_position(realized_pnl_brl=3.0)

    assert manager.cash_available(initial_cash_brl=100.0) == 53.0
    mtm = manager.mark_to_market(mark_price_brl=5.4)
    assert mtm["position_notional_brl"] == 54.0
    assert mtm["unrealized_pnl_brl"] == 4.0
