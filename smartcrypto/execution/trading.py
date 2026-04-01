from __future__ import annotations

from typing import Any

from smartcrypto.domain.strategy import compute_exit_targets
from smartcrypto.execution.controls import (
    choose_exit_order_type,
    clear_reentry_price_block,
    entry_fallback_market_enabled,
    is_live_mode,
    post_sell_controls,
)
from smartcrypto.execution.order_identity import client_order_id_prefix, new_bot_order_id
from smartcrypto.execution.reconcile import live_reconcile_qty_tolerance, map_exchange_order_state
from smartcrypto.execution.recovery import mark_dispatch_unknown
from smartcrypto.infra.binance_adapter import ExchangeAdapter
from smartcrypto.runtime.notifications import send_sell_notification
from smartcrypto.state.store import PositionState, StateStore, utc_now


def record_execution_report(
    *,
    store: StateStore,
    bot_order_id: str,
    side: str,
    reason: str,
    requested_order_type: str,
    requested_qty_usdt: float | None = None,
    requested_brl_value: float | None = None,
    report: dict[str, Any] | None = None,
) -> None:
    if not report:
        return
    attempts = list(report.get("attempts") or [])
    for attempt in attempts:
        attempt_no = int(attempt.get("attempt_no", 0) or 0)
        submitted = dict(attempt.get("submitted") or {})
        latest = dict(attempt.get("latest") or {})
        submitted_price = (
            float(submitted.get("price_brl") or latest.get("price_brl") or 0.0) or None
        )
        submitted_qty = float(submitted.get("qty_usdt") or 0.0) or requested_qty_usdt
        submitted_quote = float(submitted.get("quote_brl") or 0.0) or requested_brl_value
        submitted_time = submitted.get("updated_at") or latest.get("updated_at") or utc_now()
        latest_price = float(latest.get("price_brl") or submitted.get("price_brl") or 0.0) or None
        latest_qty = (
            float(latest.get("qty_usdt") or submitted.get("qty_usdt") or 0.0) or requested_qty_usdt
        )
        latest_quote = (
            float(latest.get("quote_brl") or submitted.get("quote_brl") or 0.0)
            or requested_brl_value
        )
        latest_executed = float(latest.get("executed_qty_usdt") or 0.0)
        exchange_order_id = str(latest.get("order_id") or submitted.get("order_id") or "") or None
        client_order_id = (
            str(latest.get("client_order_id") or submitted.get("client_order_id") or "") or None
        )

        store.add_order_event(
            bot_order_id=bot_order_id,
            exchange_order_id=exchange_order_id,
            client_order_id=client_order_id,
            side=side,
            order_type=str(submitted.get("order_type") or requested_order_type),
            state="submitted",
            reason=reason,
            price_brl=submitted_price,
            qty_usdt=submitted_qty,
            executed_qty_usdt=float(submitted.get("executed_qty_usdt") or 0.0),
            brl_value=submitted_quote,
            source="exchange",
            note=f"attempt_{attempt_no}",
            payload=attempt,
            event_time=submitted_time,
        )

        submitted_state = map_exchange_order_state(submitted)
        if submitted_state not in {"unknown", "submitted"}:
            store.add_order_event(
                bot_order_id=bot_order_id,
                exchange_order_id=exchange_order_id,
                client_order_id=client_order_id,
                side=side,
                order_type=str(submitted.get("order_type") or requested_order_type),
                state=submitted_state,
                reason=reason,
                price_brl=submitted_price,
                qty_usdt=submitted_qty,
                executed_qty_usdt=float(submitted.get("executed_qty_usdt") or 0.0),
                brl_value=submitted_quote,
                source="exchange",
                note=f"attempt_{attempt_no}",
                payload=attempt,
                event_time=submitted_time,
            )

        latest_state = map_exchange_order_state(latest)
        latest_time = latest.get("updated_at") or submitted_time
        if latest_state != submitted_state or latest_executed > float(
            submitted.get("executed_qty_usdt") or 0.0
        ):
            store.add_order_event(
                bot_order_id=bot_order_id,
                exchange_order_id=exchange_order_id,
                client_order_id=client_order_id,
                side=side,
                order_type=str(
                    latest.get("order_type") or submitted.get("order_type") or requested_order_type
                ),
                state=latest_state,
                reason=reason,
                price_brl=latest_price,
                qty_usdt=latest_qty,
                executed_qty_usdt=latest_executed,
                brl_value=latest_quote,
                source="exchange",
                note=f"attempt_{attempt_no}",
                payload=attempt,
                event_time=latest_time,
            )




def record_simulated_execution(
    *,
    store: StateStore,
    bot_order_id: str,
    side: str,
    reason: str,
    order_type: str,
    price_brl: float,
    qty_usdt: float,
    brl_value: float,
) -> None:
    store.add_order_event(
        bot_order_id=bot_order_id,
        side=side,
        order_type=order_type,
        state="submitted",
        reason=reason,
        price_brl=price_brl,
        qty_usdt=qty_usdt,
        executed_qty_usdt=0.0,
        brl_value=brl_value,
        source="simulated",
        note="dry_run",
    )
    store.add_order_event(
        bot_order_id=bot_order_id,
        side=side,
        order_type=order_type,
        state="filled",
        reason=reason,
        price_brl=price_brl,
        qty_usdt=qty_usdt,
        executed_qty_usdt=qty_usdt,
        brl_value=brl_value,
        source="simulated",
        note="dry_run",
    )





def execute_buy(
    *,
    store: StateStore,
    position: PositionState,
    exchange: ExchangeAdapter,
    price_brl: float,
    brl_value: float,
    reason: str,
    regime: str,
    cfg: dict[str, Any],
    params: dict[str, Any],
) -> PositionState:
    fee_rate = float(cfg["execution"].get("fee_rate", 0.001))
    order_type = (
        "market"
        if str(cfg.get("execution", {}).get("entry_order_type", "limit")).lower() == "market"
        else "limit"
    )
    fallback_market = entry_fallback_market_enabled(cfg)
    bot_order_id = new_bot_order_id("buy", reason)
    requested_price = None if order_type == "market" else float(price_brl)
    client_prefix = client_order_id_prefix(bot_order_id)
    store.add_order_event(
        bot_order_id=bot_order_id,
        side="buy",
        order_type=order_type,
        state="planned",
        reason=reason,
        price_brl=requested_price,
        qty_usdt=None,
        executed_qty_usdt=0.0,
        brl_value=float(brl_value),
        source="bot",
        note="logical_order_created",
    )
    if is_live_mode(cfg):
        store.upsert_dispatch_lock(
            bot_order_id=bot_order_id,
            side="buy",
            reason=reason,
            order_type=order_type,
            client_order_id=f"{client_prefix}-L1" if order_type == "limit" else f"{client_prefix}-M1",
            status="pending_submit",
            requested_price_brl=requested_price,
            requested_brl_value=float(brl_value),
            details={"client_order_id_prefix": client_prefix, "regime": regime},
        )
        try:
            fill = exchange.execute_entry(
                brl_value=float(brl_value),
                price_brl=float(price_brl),
                order_type=order_type,
                fallback_market=fallback_market,
                client_order_id_prefix=client_prefix,
            )
            store.update_dispatch_lock(
                bot_order_id,
                status="submitted",
                details={"execution_report": dict(fill.get("execution_report") or {}), "regime": regime},
            )
        except Exception as exc:
            mark_dispatch_unknown(
                store,
                bot_order_id=bot_order_id,
                side="buy",
                reason=reason,
                order_type=order_type,
                requested_price=requested_price,
                requested_qty_usdt=None,
                requested_brl_value=float(brl_value),
                client_prefix=client_prefix,
                error=exc,
            )
            raise
        record_execution_report(
            store=store,
            bot_order_id=bot_order_id,
            side="buy",
            reason=reason,
            requested_order_type=order_type,
            requested_brl_value=float(brl_value),
            report=dict(fill.get("execution_report") or {}),
        )
        exec_qty = float(fill["qty_usdt"])
        exec_quote = float(fill["quote_brl"])
        exec_price = float(fill["price_brl"])
        if exec_qty <= 0 or exec_quote <= 0 or exec_price <= 0:
            raise RuntimeError(f"Compra live sem execução válida: {fill}")
        exchange_order_id = (
            str((fill.get("execution_report") or {}).get("exchange_order_id") or "") or None
        )
        client_order_id = (
            str((fill.get("execution_report") or {}).get("client_order_id") or "") or None
        )
        if not client_order_id:
            attempts = list((fill.get("execution_report") or {}).get("attempts") or [])
            if attempts:
                latest = dict(attempts[-1].get("latest") or {})
                submitted = dict(attempts[-1].get("submitted") or {})
                client_order_id = str(latest.get("client_order_id") or submitted.get("client_order_id") or "") or None
                exchange_order_id = str(latest.get("order_id") or submitted.get("order_id") or exchange_order_id or "") or None
    else:
        exec_price = float(price_brl)
        exec_quote = float(brl_value)
        exec_qty = exec_quote / max(exec_price, 1e-9)
        exchange_order_id = None
        client_order_id = None
        record_simulated_execution(
            store=store,
            bot_order_id=bot_order_id,
            side="buy",
            reason=reason,
            order_type=order_type,
            price_brl=exec_price,
            qty_usdt=exec_qty,
            brl_value=exec_quote,
        )

    fee = exec_quote * fee_rate
    total_cost = exec_quote + fee
    new_qty = position.qty_usdt + exec_qty
    new_spent = position.brl_spent + total_cost
    avg = new_spent / max(new_qty, 1e-9)
    tp_price, stop_price = compute_exit_targets(
        qty_usdt=new_qty, brl_spent=new_spent, avg_price_brl=avg, params=params, cfg=cfg
    )
    updated = store.apply_buy_fill(
        bot_order_id=bot_order_id,
        reason=reason,
        regime=regime,
        mode=str(cfg["execution"]["mode"]),
        fee_rate=fee_rate,
        exec_price_brl=exec_price,
        exec_qty_usdt=exec_qty,
        exec_quote_brl=exec_quote,
        tp_price_brl=tp_price,
        stop_price_brl=stop_price,
        order_type=order_type,
        source="exchange" if is_live_mode(cfg) else "simulated",
        client_order_id=client_order_id,
        exchange_order_id=exchange_order_id,
        run_id=str(cfg.get("__run_id", "") or ""),
    )
    clear_reentry_price_block(store)
    return updated


def execute_sell(
    *,
    store: StateStore,
    position: PositionState,
    exchange: ExchangeAdapter,
    price_brl: float,
    reason: str,
    regime: str,
    cfg: dict[str, Any],
    params: dict[str, Any],
) -> PositionState:
    fee_rate = float(cfg["execution"].get("fee_rate", 0.001))
    order_type = choose_exit_order_type(reason, cfg, params)
    fallback_market = False
    bot_order_id = new_bot_order_id("sell", reason)
    requested_price = None if order_type == "market" else float(price_brl)
    client_prefix = client_order_id_prefix(bot_order_id)
    store.add_order_event(
        bot_order_id=bot_order_id,
        side="sell",
        order_type=order_type,
        state="planned",
        reason=reason,
        price_brl=requested_price,
        qty_usdt=float(position.qty_usdt),
        executed_qty_usdt=0.0,
        brl_value=float(position.qty_usdt * (requested_price or price_brl)),
        source="bot",
        note="logical_order_created",
    )
    if is_live_mode(cfg):
        store.upsert_dispatch_lock(
            bot_order_id=bot_order_id,
            side="sell",
            reason=reason,
            order_type=order_type,
            client_order_id=f"{client_prefix}-L1" if order_type == "limit" else f"{client_prefix}-M1",
            status="pending_submit",
            requested_price_brl=requested_price,
            requested_qty_usdt=float(position.qty_usdt),
            requested_brl_value=float(position.qty_usdt * (requested_price or price_brl)),
            details={"client_order_id_prefix": client_prefix, "regime": regime},
        )
        if order_type == "limit" and reason in {"take_profit", "trailing_exit"}:
            store.add_event(
                "INFO",
                "profit_exit_limit_only",
                {"reason": reason, "price_brl": float(price_brl), "qty_usdt": float(position.qty_usdt)},
            )
        try:
            fill = exchange.execute_exit(
                qty_usdt=float(position.qty_usdt),
                price_brl=None if order_type == "market" else float(price_brl),
                order_type=order_type,
                fallback_market=fallback_market,
                client_order_id_prefix=client_prefix,
            )
            store.update_dispatch_lock(
                bot_order_id,
                status="submitted",
                details={"execution_report": dict(fill.get("execution_report") or {}), "regime": regime},
            )
        except Exception as exc:
            mark_dispatch_unknown(
                store,
                bot_order_id=bot_order_id,
                side="sell",
                reason=reason,
                order_type=order_type,
                requested_price=requested_price,
                requested_qty_usdt=float(position.qty_usdt),
                requested_brl_value=float(position.qty_usdt * (requested_price or price_brl)),
                client_prefix=client_prefix,
                error=exc,
            )
            raise
        record_execution_report(
            store=store,
            bot_order_id=bot_order_id,
            side="sell",
            reason=reason,
            requested_order_type=order_type,
            requested_qty_usdt=float(position.qty_usdt),
            requested_brl_value=float(position.qty_usdt * (requested_price or price_brl)),
            report=dict(fill.get("execution_report") or {}),
        )
        exec_qty = float(fill["qty_usdt"])
        gross = float(fill["quote_brl"])
        exec_price = float(fill["price_brl"])
        if exec_qty <= 0 or gross <= 0 or exec_price <= 0:
            raise RuntimeError(f"Venda live sem execução válida: {fill}")
        exchange_order_id = (
            str((fill.get("execution_report") or {}).get("exchange_order_id") or "") or None
        )
        client_order_id = (
            str((fill.get("execution_report") or {}).get("client_order_id") or "") or None
        )
        if not client_order_id:
            attempts = list((fill.get("execution_report") or {}).get("attempts") or [])
            if attempts:
                latest = dict(attempts[-1].get("latest") or {})
                submitted = dict(attempts[-1].get("submitted") or {})
                client_order_id = str(latest.get("client_order_id") or submitted.get("client_order_id") or "") or None
                exchange_order_id = str(latest.get("order_id") or submitted.get("order_id") or exchange_order_id or "") or None
    else:
        exec_qty = float(position.qty_usdt)
        exec_price = float(price_brl)
        gross = exec_qty * exec_price
        exchange_order_id = None
        client_order_id = None
        record_simulated_execution(
            store=store,
            bot_order_id=bot_order_id,
            side="sell",
            reason=reason,
            order_type=order_type,
            price_brl=exec_price,
            qty_usdt=exec_qty,
            brl_value=gross,
        )

    net_received = gross - (gross * fee_rate)
    target_qty = float(position.qty_usdt)
    fill_ratio = min(1.0, exec_qty / max(target_qty, 1e-9))
    sold_cost_basis = float(position.brl_spent) * fill_ratio
    pnl_brl = net_received - sold_cost_basis
    pnl_pct = (pnl_brl / sold_cost_basis) * 100.0 if sold_cost_basis else 0.0

    remaining_qty = max(0.0, target_qty - exec_qty)
    remaining_spent = max(0.0, float(position.brl_spent) - sold_cost_basis)
    if remaining_qty <= live_reconcile_qty_tolerance(cfg):
        updated = store.apply_sell_fill(
            bot_order_id=bot_order_id,
            reason=reason,
            regime=regime,
            mode=str(cfg["execution"]["mode"]),
            fee_rate=fee_rate,
            exec_price_brl=exec_price,
            exec_qty_usdt=exec_qty,
            exec_quote_brl=gross,
            qty_tolerance_usdt=live_reconcile_qty_tolerance(cfg),
            tp_price_brl=0.0,
            stop_price_brl=0.0,
            order_type=order_type,
            source="exchange" if is_live_mode(cfg) else "simulated",
            client_order_id=client_order_id,
            exchange_order_id=exchange_order_id,
            run_id=str(cfg.get("__run_id", "") or ""),
        )
        send_sell_notification(
            store=store,
            cfg=cfg,
            reason=reason,
            exec_price=exec_price,
            exec_qty=exec_qty,
            pnl_brl=pnl_brl,
            pnl_pct=pnl_pct,
            order_type=order_type,
        )
        post_sell_controls(store, cfg, params, reason, exec_price)
        return updated

    remaining_avg = remaining_spent / max(remaining_qty, 1e-9)
    tp_price, stop_price = compute_exit_targets(
        qty_usdt=remaining_qty,
        brl_spent=remaining_spent,
        avg_price_brl=remaining_avg,
        params=params,
        cfg=cfg,
    )
    return store.apply_sell_fill(
        bot_order_id=bot_order_id,
        reason=reason,
        regime=regime,
        mode=str(cfg["execution"]["mode"]),
        fee_rate=fee_rate,
        exec_price_brl=exec_price,
        exec_qty_usdt=exec_qty,
        exec_quote_brl=gross,
        qty_tolerance_usdt=live_reconcile_qty_tolerance(cfg),
        tp_price_brl=tp_price,
        stop_price_brl=stop_price,
        order_type=order_type,
        source="exchange" if is_live_mode(cfg) else "simulated",
        client_order_id=client_order_id,
        exchange_order_id=exchange_order_id,
        run_id=str(cfg.get("__run_id", "") or ""),
    )
