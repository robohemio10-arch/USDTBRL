from __future__ import annotations

from decimal import Decimal


def fixed_quote_size(quote_amount: Decimal) -> Decimal:
    return quote_amount


def cap_quote_size(quote_amount: Decimal, *, cycle_cap: Decimal) -> Decimal:
    return min(quote_amount, cycle_cap)


def cycle_quote_budget(*, first_buy_brl: Decimal, deployed_brl: Decimal, cycle_cap_brl: Decimal) -> Decimal:
    remaining = cycle_cap_brl - deployed_brl
    if remaining <= Decimal("0"):
        return Decimal("0")
    return min(first_buy_brl, remaining)
