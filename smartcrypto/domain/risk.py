from __future__ import annotations

from decimal import Decimal
from typing import Any


def clamp_notional(notional: Decimal, min_notional: Decimal, max_notional: Decimal) -> Decimal:
    return max(min_notional, min(notional, max_notional))


def effective_cycle_cap(cfg: dict[str, Any], requested_cycle_brl: float) -> float:
    portfolio_brl = float(cfg.get("portfolio", {}).get("initial_cash_brl", 0.0) or 0.0)
    max_open_brl = float(cfg.get("risk", {}).get("max_open_brl", 0.0) or 0.0)
    candidates = [float(requested_cycle_brl)]
    if portfolio_brl > 0:
        candidates.append(portfolio_brl)
    if max_open_brl > 0:
        candidates.append(max_open_brl)
    cycle_cap = min(v for v in candidates if v > 0)
    return max(0.0, cycle_cap)


def min_profit_brl(cfg: dict[str, Any]) -> float:
    return max(0.0, float(cfg.get("strategy", {}).get("min_profit_brl", 0.15) or 0.0))


def min_profit_exit_price(
    *, qty_usdt: float, brl_spent: float, fee_rate: float, desired_profit_brl: float
) -> float:
    if qty_usdt <= 0:
        return 0.0
    net_factor = max(1e-9, 1.0 - float(fee_rate))
    required_gross = (float(brl_spent) + max(0.0, float(desired_profit_brl))) / net_factor
    return required_gross / float(qty_usdt)


def estimate_exit_pnl_brl(
    *, qty_usdt: float, brl_spent: float, price_brl: float, fee_rate: float
) -> float:
    gross = float(qty_usdt) * float(price_brl)
    fee = gross * float(fee_rate)
    return gross - fee - float(brl_spent)
