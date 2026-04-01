from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from smartcrypto.execution.controls import clear_reentry_price_block
from smartcrypto.execution.reconcile import (
    is_live_mode,
    live_reconcile_qty_tolerance,
    map_exchange_order_state,
)
from smartcrypto.infra.binance_adapter import ExchangeAdapter
from smartcrypto.domain.strategy import compute_exit_targets, strategy_params
from smartcrypto.state.store import StateStore, utc_now


@dataclass(frozen=True)
class RecoveryAction:
    recovered: bool
    message: str


def inflight_order_lock_seconds(cfg: dict[str, Any]) -> int:
    return max(10, int(cfg.get("runtime", {}).get("inflight_order_lock_seconds", 120) or 120))


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
    store.update_dispatch_lock(
        bot_order_id,
        status="submit_unknown",
        client_order_id=f"{client_prefix}-L1" if order_type == "limit" else f"{client_prefix}-M1",
        details={
            "error": str(error),
            "client_order_id_prefix": client_prefix,
            "last_error_at": utc_now(),
        },
    )
    store.add_order_event(
        bot_order_id=bot_order_id,
        side=side,
        order_type=order_type,
        state="submit_unknown",
        reason=reason,
        price_brl=requested_price,
        qty_usdt=requested_qty_usdt,
        executed_qty_usdt=0.0,
        brl_value=requested_brl_value,
        source="bot",
        note=str(error),
    )


def _apply_recovered_fill(
    cfg: dict[str, Any],
    store: StateStore,
    lock: dict[str, Any],
    snapshot: dict[str, Any],
) -> None:
    side = str(lock.get("side") or "")
    reason = str(lock.get("reason") or "")
    regime = str(store.get_position().regime or "sideways")
    fee_rate = float(cfg.get("execution", {}).get("fee_rate", 0.001) or 0.001)
    client_order_id = str(snapshot.get("client_order_id") or "") or None
    exchange_order_id = str(snapshot.get("order_id") or "") or None
    exec_price = float(snapshot.get("price_brl") or 0.0)
    exec_qty = float(snapshot.get("executed_qty_usdt") or snapshot.get("qty_usdt") or 0.0)
    exec_quote = float(snapshot.get("quote_brl") or 0.0)
    order_type = str(lock.get("order_type") or snapshot.get("order_type") or "")
    run_id = str(cfg.get("__run_id", "") or "")

    if exec_price <= 0 or exec_qty <= 0 or exec_quote <= 0:
        return

    if side == "buy":
        position = store.get_position()
        params = strategy_params(cfg, regime)
        new_qty = float(position.qty_usdt) + exec_qty
        new_spent = float(position.brl_spent) + exec_quote + (exec_quote * fee_rate)
        avg_price_brl = new_spent / max(new_qty, 1e-9)
        tp_price_brl, stop_price_brl = compute_exit_targets(
            qty_usdt=new_qty,
            brl_spent=new_spent,
            avg_price_brl=avg_price_brl,
            params=params,
            cfg=cfg,
        )
        store.apply_buy_fill(
            bot_order_id=str(lock.get("bot_order_id") or ""),
            reason=reason,
            regime=regime,
            mode=str(cfg.get("execution", {}).get("mode", "") or ""),
            fee_rate=fee_rate,
            exec_price_brl=exec_price,
            exec_qty_usdt=exec_qty,
            exec_quote_brl=exec_quote,
            tp_price_brl=tp_price_brl,
            stop_price_brl=stop_price_brl,
            order_type=order_type,
            source="exchange_recovery",
            client_order_id=client_order_id,
            exchange_order_id=exchange_order_id,
            run_id=run_id,
        )
        clear_reentry_price_block(store)
        return

    position = store.get_position()
    remaining_qty = max(0.0, float(position.qty_usdt) - exec_qty)
    remaining_spent = max(
        0.0,
        float(position.brl_spent)
        - (float(position.brl_spent) * min(1.0, exec_qty / max(float(position.qty_usdt), 1e-9))),
    )
    remaining_avg = remaining_spent / max(remaining_qty, 1e-9) if remaining_qty > 0 else 0.0
    params = strategy_params(cfg, regime)
    tp_price_brl, stop_price_brl = compute_exit_targets(
        qty_usdt=remaining_qty,
        brl_spent=remaining_spent,
        avg_price_brl=remaining_avg,
        params=params,
        cfg=cfg,
    ) if remaining_qty > 0 else (0.0, 0.0)
    store.apply_sell_fill(
        bot_order_id=str(lock.get("bot_order_id") or ""),
        reason=reason,
        regime=regime,
        mode=str(cfg.get("execution", {}).get("mode", "") or ""),
        fee_rate=fee_rate,
        exec_price_brl=exec_price,
        exec_qty_usdt=exec_qty,
        exec_quote_brl=exec_quote,
        qty_tolerance_usdt=live_reconcile_qty_tolerance(cfg),
        tp_price_brl=tp_price_brl,
        stop_price_brl=stop_price_brl,
        order_type=order_type,
        source="exchange_recovery",
        client_order_id=client_order_id,
        exchange_order_id=exchange_order_id,
        run_id=run_id,
    )


def recover_dispatch_locks(
    cfg: dict[str, Any], store: StateStore, exchange: ExchangeAdapter
) -> RecoveryAction:
    if not is_live_mode(cfg):
        return RecoveryAction(recovered=False, message="mode_not_live")
    active = store.list_active_dispatch_locks(limit=20)
    recovered_any = False
    cleared_stale = 0
    for lock in active:
        bot_order_id = str(lock.get("bot_order_id") or "")
        client_order_id = str(lock.get("client_order_id") or "")
        details = dict(lock.get("details") or {})
        prefix = str(details.get("client_order_id_prefix") or "")
        candidates: list[str] = []
        for item in [client_order_id, f"{prefix}-L1" if prefix else "", f"{prefix}-M1" if prefix else ""]:
            if item and item not in candidates:
                candidates.append(item)
        recovered = None
        for candidate in candidates:
            recovered = exchange.get_order(client_order_id=candidate, raise_if_missing=False)
            if recovered:
                break
        if recovered:
            snapshot = exchange._normalize_order_snapshot(recovered)
            recovered_state = map_exchange_order_state(snapshot)
            store.add_order_event(
                bot_order_id=bot_order_id,
                exchange_order_id=str(snapshot.get("order_id") or "") or None,
                client_order_id=str(snapshot.get("client_order_id") or "") or None,
                side=str(lock.get("side") or ""),
                order_type=str(lock.get("order_type") or ""),
                state=recovered_state,
                reason=str(lock.get("reason") or ""),
                price_brl=float(snapshot.get("price_brl") or 0.0) or None,
                qty_usdt=float(snapshot.get("qty_usdt") or 0.0) or None,
                executed_qty_usdt=float(snapshot.get("executed_qty_usdt") or 0.0),
                brl_value=float(snapshot.get("quote_brl") or 0.0) or None,
                source="exchange_recovery",
                note="recovered_from_dispatch_lock",
                payload=snapshot,
                event_time=str(snapshot.get("updated_at") or utc_now()),
            )
            if recovered_state in {"open_on_exchange", "partial"}:
                store.update_dispatch_lock(
                    bot_order_id,
                    status="recovered_open",
                    client_order_id=str(snapshot.get("client_order_id") or ""),
                )
            else:
                _apply_recovered_fill(cfg, store, lock, snapshot)
            recovered_any = True
            continue
        updated_at = pd.to_datetime(lock.get("updated_at"), errors="coerce", utc=True)
        age_seconds = 0.0 if pd.isna(updated_at) else float((pd.Timestamp.utcnow() - updated_at).total_seconds())
        if age_seconds >= inflight_order_lock_seconds(cfg):
            store.clear_dispatch_lock(bot_order_id, terminal_status="stale")
            store.add_event(
                "ERROR",
                "dispatch_lock_stale_cleared",
                {"bot_order_id": bot_order_id, "age_seconds": age_seconds},
            )
            cleared_stale += 1

    if recovered_any:
        return RecoveryAction(recovered=True, message="dispatch_lock_recovered")
    if cleared_stale:
        return RecoveryAction(recovered=True, message="stale_dispatch_locks_cleared")
    return RecoveryAction(recovered=False, message="no_dispatch_lock_action")


def active_dispatch_lock_present(cfg: dict[str, Any], store: StateStore) -> bool:
    active = store.list_active_dispatch_locks(limit=1)
    if not active:
        return False
    lock = active[0]
    updated_at = pd.to_datetime(lock.get("updated_at"), errors="coerce", utc=True)
    if pd.isna(updated_at):
        return True
    return float((pd.Timestamp.utcnow() - updated_at).total_seconds()) < inflight_order_lock_seconds(cfg)
