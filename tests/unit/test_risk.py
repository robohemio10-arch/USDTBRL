from decimal import Decimal

from smartcrypto.domain.risk import clamp_notional, estimate_exit_pnl_brl, min_profit_exit_price


def test_clamp_notional() -> None:
    assert clamp_notional(Decimal("5"), Decimal("10"), Decimal("20")) == Decimal("10")


def test_min_profit_exit_price_positive() -> None:
    assert min_profit_exit_price(
        qty_usdt=100.0,
        brl_spent=500.0,
        fee_rate=0.001,
        desired_profit_brl=1.0,
    ) > 5.0


def test_estimate_exit_pnl_brl() -> None:
    pnl = estimate_exit_pnl_brl(
        qty_usdt=100.0,
        brl_spent=500.0,
        price_brl=5.05,
        fee_rate=0.001,
    )

    assert pnl > 0
