from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from smartcrypto.infra.binance_adapter import ExchangeAdapter
from smartcrypto.state.store import StateStore


@dataclass(frozen=True)
class ReconcileResult:
    needs_action: bool
    reason: str


def is_live_mode(cfg: dict[str, Any]) -> bool:
    return str(cfg.get("execution", {}).get("mode", "paper")).lower() == "live"


def live_reconcile_pause_on_mismatch(cfg: dict[str, Any]) -> bool:
    return bool(cfg.get("runtime", {}).get("reconcile_pause_on_mismatch", True))


def live_reconcile_qty_tolerance(
    cfg: dict[str, Any], exchange: ExchangeAdapter | None = None
) -> float:
    configured = float(cfg.get("runtime", {}).get("reconcile_qty_tolerance_usdt", 0.0001) or 0.0001)
    if exchange is None:
        return configured
    try:
        return max(configured, float(exchange._min_qty(for_market=False) or 0.0))
    except Exception:
        return configured


def live_reconcile_allow_extra_base_asset_balance(cfg: dict[str, Any]) -> bool:
    return bool(cfg.get("runtime", {}).get("reconcile_allow_extra_base_asset_balance", False))


def bot_managed_open_order_refs(store: StateStore, limit: int = 500) -> tuple[set[str], set[str]]:
    try:
        frame = store.latest_order_states_df(limit=limit)
    except Exception:
        return set(), set()
    if frame is None or getattr(frame, "empty", True):
        return set(), set()

    active_states = {"submitted", "open_on_exchange", "partial", "recovered_open"}
    active = frame[frame["state"].isin(active_states)].copy()
    if active.empty:
        return set(), set()

    exchange_ids = {
        str(value).strip()
        for value in active.get("exchange_order_id", pd.Series(dtype=str)).dropna().tolist()
        if str(value).strip()
    }
    client_ids = {
        str(value).strip()
        for value in active.get("client_order_id", pd.Series(dtype=str)).dropna().tolist()
        if str(value).strip()
    }
    return exchange_ids, client_ids


def is_bot_managed_exchange_order(
    order: dict[str, Any],
    *,
    known_exchange_ids: set[str],
    known_client_ids: set[str],
) -> bool:
    exchange_order_id = str(order.get("exchange_order_id") or order.get("order_id") or "").strip()
    client_order_id = str(order.get("client_order_id") or "").strip()
    if exchange_order_id and exchange_order_id in known_exchange_ids:
        return True
    if client_order_id and client_order_id in known_client_ids:
        return True
    return client_order_id.startswith("SC")


def map_exchange_order_state(snapshot: dict[str, Any] | None) -> str:
    if not snapshot:
        return "unknown"
    status = str(snapshot.get("status", "")).upper()
    executed_qty = float(snapshot.get("executed_qty_usdt", 0.0) or 0.0)
    if status == "NEW":
        return "open_on_exchange"
    if status == "PARTIALLY_FILLED":
        return "partial"
    if status == "FILLED":
        return "filled"
    if status == "CANCELED":
        return "partial_canceled" if executed_qty > 0 else "canceled"
    if status == "EXPIRED":
        return "partial_expired" if executed_qty > 0 else "expired"
    if status == "REJECTED":
        return "rejected"
    return status.lower() if status else "unknown"


def _material_qty_mismatch(local_qty: float, exchange_qty_total: float, tolerance: float) -> bool:
    return abs(float(exchange_qty_total) - float(local_qty)) > float(tolerance)


def reconcile_live_exchange_state(
    cfg: dict[str, Any],
    store: StateStore,
    exchange: ExchangeAdapter,
    *,
    last_price: float,
) -> ReconcileResult:
    if not is_live_mode(cfg):
        return ReconcileResult(needs_action=False, reason="mode_not_live")

    balances = exchange.get_account_balances()
    base_asset = exchange.base_asset_symbol()
    exchange_qty_total = float((balances.get(base_asset) or {}).get("total") or 0.0)
    all_open_orders = exchange.get_open_orders()
    tolerance = live_reconcile_qty_tolerance(cfg, exchange)
    local = store.get_position()

    known_exchange_ids, known_client_ids = bot_managed_open_order_refs(store)
    bot_open_orders = [
        order
        for order in all_open_orders
        if is_bot_managed_exchange_order(
            order,
            known_exchange_ids=known_exchange_ids,
            known_client_ids=known_client_ids,
        )
    ]
    unmanaged_open_orders = [
        order
        for order in all_open_orders
        if not is_bot_managed_exchange_order(
            order,
            known_exchange_ids=known_exchange_ids,
            known_client_ids=known_client_ids,
        )
    ]
    bot_open_order_count = len(bot_open_orders)
    local_qty = float(local.qty_usdt or 0.0)
    allow_extra_balance = live_reconcile_allow_extra_base_asset_balance(cfg)

    mismatch_reason = None
    if unmanaged_open_orders:
        mismatch_reason = "unmanaged_open_orders_present"
    elif local.status == "flat":
        if bot_open_order_count > 0:
            mismatch_reason = "bot_open_orders_exist_while_local_flat"
        elif exchange_qty_total > tolerance and not allow_extra_balance:
            mismatch_reason = "exchange_position_exists_while_local_flat"
    elif _material_qty_mismatch(local_qty, exchange_qty_total, tolerance):
        mismatch_reason = "exchange_qty_diverges_from_local_position"

    audit_details = {
        "tolerance_usdt": tolerance,
        "price_brl": last_price,
        "base_asset": base_asset,
        "exchange_qty_total": exchange_qty_total,
        "local_qty_usdt": local_qty,
        "allow_extra_balance": allow_extra_balance,
        "bot_open_orders": bot_open_orders,
        "unmanaged_open_orders": unmanaged_open_orders,
        "known_exchange_ids": sorted(known_exchange_ids),
        "known_client_ids": sorted(known_client_ids),
    }

    if mismatch_reason:
        store.add_reconciliation_audit(
            action="mismatch",
            local_status=local.status,
            local_qty_usdt=local_qty,
            exchange_qty_usdt=exchange_qty_total,
            exchange_open_orders=bot_open_order_count,
            details={**audit_details, "reason": mismatch_reason},
        )
        store.set_flag("live_reconcile_required", True)
        if live_reconcile_pause_on_mismatch(cfg):
            store.set_flag("paused", True)
            store.add_event(
                "ERROR",
                "live_reconcile_mismatch",
                {**audit_details, "reason": mismatch_reason},
            )
        return ReconcileResult(needs_action=True, reason=mismatch_reason)

    store.add_reconciliation_audit(
        action="ok",
        local_status=local.status,
        local_qty_usdt=local_qty,
        exchange_qty_usdt=exchange_qty_total,
        exchange_open_orders=bot_open_order_count,
        details=audit_details,
    )
    store.set_flag("live_reconcile_required", False)
    return ReconcileResult(needs_action=False, reason="ok")
