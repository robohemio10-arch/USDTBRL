from __future__ import annotations

import time
from typing import Any

from smartcrypto.common.health import health_report
from smartcrypto.state.portfolio import Portfolio
from smartcrypto.state.position_manager import PositionManager
from smartcrypto.state.store import PositionState, StateStore, utc_now


def reentry_remaining_seconds(store: StateStore) -> int:
    value = store.get_flag("reentry_block_until", 0)
    try:
        until_epoch = float(value or 0.0)
    except Exception:
        until_epoch = 0.0
    if until_epoch <= 0:
        return 0
    return max(0, int(until_epoch - time.time()))


def reentry_price_threshold(store: StateStore) -> float:
    value = store.get_flag("reentry_price_below", 0)
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def log_snapshot(
    store: StateStore,
    *,
    price: float,
    position: PositionState | None = None,
    cfg: dict[str, Any],
    regime: str,
    meta: dict[str, Any] | None = None,
) -> None:
    portfolio = Portfolio(store, position_manager=PositionManager(store))
    view = portfolio.runtime_view(
        mark_price_brl=price,
        initial_cash_brl=float(cfg["portfolio"]["initial_cash_brl"]),
    )
    store.add_snapshot(
        last_price_brl=price,
        equity_brl=view.equity_brl,
        cash_brl=view.cash_brl,
        pos_value_brl=view.position_notional_brl,
        realized_pnl_brl=view.realized_pnl_brl,
        unrealized_pnl_brl=view.unrealized_pnl_brl,
        drawdown_pct=view.drawdown_pct,
        regime=regime,
        meta=meta or {},
    )


def status_payload(store: StateStore, price: float, cfg: dict[str, Any]) -> dict[str, Any]:
    manager = PositionManager(store)
    portfolio = Portfolio(store, position_manager=manager)
    view = portfolio.runtime_view(
        mark_price_brl=price,
        initial_cash_brl=float(cfg["portfolio"]["initial_cash_brl"]),
    )
    active_locks = store.list_active_dispatch_locks(limit=5)
    payload = {
        "time": utc_now(),
        "price_brl": round(price, 6),
        "paused": bool(store.get_flag("paused", False)),
        "position": view.position,
        "portfolio": {
            "cash_brl": view.cash_brl,
            "equity_brl": view.equity_brl,
            "position_notional_brl": view.position_notional_brl,
            "invested_brl": view.invested_brl,
            "unrealized_pnl_brl": view.unrealized_pnl_brl,
            "realized_pnl_brl": view.realized_pnl_brl,
            "drawdown_pct": view.drawdown_pct,
        },
        "cash_brl": view.cash_brl,
        "equity_brl": view.equity_brl,
        "flags": {
            "force_sell_requested": store.get_flag("force_sell_requested", False),
            "reset_cycle_requested": store.get_flag("reset_cycle_requested", False),
            "reentry_block_until": store.get_flag("reentry_block_until", 0),
            "reentry_remaining_seconds": reentry_remaining_seconds(store),
            "reentry_price_below": reentry_price_threshold(store),
            "live_reconcile_required": store.get_flag("live_reconcile_required", False),
            "consecutive_error_count": int(store.get_flag("consecutive_error_count", 0) or 0),
        },
        "live_hardening": {
            "active_dispatch_locks": [
                {
                    "bot_order_id": str(row.get("bot_order_id") or ""),
                    "side": str(row.get("side") or ""),
                    "reason": str(row.get("reason") or ""),
                    "status": str(row.get("status") or ""),
                    "updated_at": str(row.get("updated_at") or ""),
                    "client_order_id": str(row.get("client_order_id") or ""),
                }
                for row in active_locks
            ],
            "active_dispatch_lock_count": len(active_locks),
        },
    }
    payload["health"] = health_report(
        cfg, store, interval=str(cfg.get("market", {}).get("timeframe", "15m"))
    )
    return payload
