from decimal import Decimal

from smartcrypto.execution.sizing import cap_quote_size, cycle_quote_budget, fixed_quote_size


def test_fixed_quote_size() -> None:
    assert fixed_quote_size(Decimal("300")) == Decimal("300")


def test_cap_quote_size() -> None:
    assert cap_quote_size(Decimal("500"), cycle_cap=Decimal("400")) == Decimal("400")


def test_cycle_quote_budget() -> None:
    assert cycle_quote_budget(
        first_buy_brl=Decimal("300"),
        deployed_brl=Decimal("250"),
        cycle_cap_brl=Decimal("400"),
    ) == Decimal("150")
