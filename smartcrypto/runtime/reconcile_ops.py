from __future__ import annotations

from typing import Any

from smartcrypto.execution.reconcile import (
    bot_managed_open_order_refs as execution_bot_managed_open_order_refs,
    is_bot_managed_exchange_order as execution_is_bot_managed_exchange_order,
    live_reconcile_allow_extra_base_asset_balance as execution_live_reconcile_allow_extra_base_asset_balance,
    live_reconcile_pause_on_mismatch as execution_live_reconcile_pause_on_mismatch,
    live_reconcile_qty_tolerance as execution_live_reconcile_qty_tolerance,
    map_exchange_order_state as execution_map_exchange_order_state,
    reconcile_live_exchange_state as execution_reconcile_live_exchange_state,
)
from smartcrypto.execution.recovery import (
    active_dispatch_lock_present as execution_active_dispatch_lock_present,
    inflight_order_lock_seconds as execution_inflight_order_lock_seconds,
    mark_dispatch_unknown as execution_mark_dispatch_unknown,
    recover_dispatch_locks as execution_recover_dispatch_locks,
)
from smartcrypto.infra.binance_adapter import ExchangeAdapter
from smartcrypto.state.store import StateStore


def inflight_order_lock_seconds(cfg: dict[str, Any]) -> int:
    return execution_inflight_order_lock_seconds(cfg)


def live_reconcile_pause_on_mismatch(cfg: dict[str, Any]) -> bool:
    return execution_live_reconcile_pause_on_mismatch(cfg)


def live_reconcile_qty_tolerance(
    cfg: dict[str, Any], exchange: ExchangeAdapter | None = None
) -> float:
    return execution_live_reconcile_qty_tolerance(cfg, exchange)


def live_reconcile_allow_extra_base_asset_balance(cfg: dict[str, Any]) -> bool:
    return execution_live_reconcile_allow_extra_base_asset_balance(cfg)


def bot_managed_open_order_refs(store: StateStore, limit: int = 500) -> tuple[set[str], set[str]]:
    return execution_bot_managed_open_order_refs(store, limit=limit)


def is_bot_managed_exchange_order(
    order: dict[str, Any],
    *,
    known_exchange_ids: set[str],
    known_client_ids: set[str],
) -> bool:
    return execution_is_bot_managed_exchange_order(
        order,
        known_exchange_ids=known_exchange_ids,
        known_client_ids=known_client_ids,
    )


def mark_dispatch_unknown(
    store: StateStore,
    *,
    bot_order_id: str,
    side: str,
    reason: str,
    order_type: str,
    requested_price: float | None,
    requested_qty_usdt: float | None,
    requested_brl_value: float | None,
    client_prefix: str,
    error: Exception,
) -> None:
    execution_mark_dispatch_unknown(
        store,
        bot_order_id=bot_order_id,
        side=side,
        reason=reason,
        order_type=order_type,
        requested_price=requested_price,
        requested_qty_usdt=requested_qty_usdt,
        requested_brl_value=requested_brl_value,
        client_prefix=client_prefix,
        error=error,
    )


def recover_dispatch_locks(
    cfg: dict[str, Any], store: StateStore, exchange: ExchangeAdapter
) -> None:
    execution_recover_dispatch_locks(cfg, store, exchange)


def active_dispatch_lock_present(cfg: dict[str, Any], store: StateStore) -> bool:
    return execution_active_dispatch_lock_present(cfg, store)


def reconcile_live_exchange_state(
    cfg: dict[str, Any], store: StateStore, exchange: ExchangeAdapter, *, last_price: float
):
    return execution_reconcile_live_exchange_state(cfg, store, exchange, last_price=last_price)


def map_exchange_order_state(snapshot: dict[str, Any] | None) -> str:
    return execution_map_exchange_order_state(snapshot)
