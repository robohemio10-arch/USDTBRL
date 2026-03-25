import pytest

from pathlib import Path

from smartcrypto.state.portfolio import Portfolio
from smartcrypto.state.position_manager import PositionManager
from smartcrypto.state.store import StateStore


def test_portfolio_snapshot_for_open_position(tmp_path: Path) -> None:
    store = StateStore(str(tmp_path / "portfolio.sqlite"))
    manager = PositionManager(store)
    manager.open_position(
        regime="bullish",
        entry_price_brl=5.0,
        qty_usdt=10.0,
        brl_spent=50.0,
    )
    store.update_position(realized_pnl_brl=2.5)

    portfolio = Portfolio(store, position_manager=manager)
    snapshot = portfolio.snapshot(mark_price_brl=5.4)

    assert snapshot.status == "open"
    assert snapshot.position_notional_brl == 54.0
    assert snapshot.unrealized_pnl_brl == pytest.approx(4.0)
    assert snapshot.realized_pnl_brl == 2.5
    assert snapshot.equity_brl == 56.5


def test_portfolio_snapshot_for_flat_position(tmp_path: Path) -> None:
    store = StateStore(str(tmp_path / "portfolio_flat.sqlite"))
    portfolio = Portfolio(store)

    snapshot = portfolio.snapshot(mark_price_brl=5.4)

    assert snapshot.status == "flat"
    assert snapshot.position_notional_brl == 0.0
    assert snapshot.unrealized_pnl_brl == 0.0
    assert snapshot.equity_brl == 0.0


def test_portfolio_runtime_view_includes_cash_and_equity(tmp_path: Path) -> None:
    store = StateStore(str(tmp_path / "portfolio_runtime.sqlite"))
    manager = PositionManager(store)
    manager.open_position(
        regime="bullish",
        entry_price_brl=5.0,
        qty_usdt=10.0,
        brl_spent=50.0,
    )
    store.update_position(realized_pnl_brl=2.5)

    portfolio = Portfolio(store, position_manager=manager)
    view = portfolio.runtime_view(mark_price_brl=5.4, initial_cash_brl=100.0)

    assert view.cash_brl == pytest.approx(52.5)
    assert view.position_notional_brl == pytest.approx(54.0)
    assert view.equity_brl == pytest.approx(106.5)
    assert view.position["unrealized_pnl_brl"] == pytest.approx(4.0)
