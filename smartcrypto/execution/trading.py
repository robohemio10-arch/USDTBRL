from __future__ import annotations

from typing import Any

from smartcrypto.execution.controls import (
    choose_exit_order_type,
    clear_reentry_price_block,
    entry_fallback_market_enabled,
    is_live_mode,
    post_sell_controls,
)
from smartcrypto.infra.binance_adapter import ExchangeAdapter
from smartcrypto.state.store import PositionState, StateStore, utc_now


def _legacy() -> Any:
    from smartcrypto.runtime import bot_runtime as legacy
    return legacy


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
    legacy = _legacy()
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

        submitted_state = legacy.map_exchange_order_state(submitted)
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

        latest_state = legacy.map_exchange_order_state(latest)
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
    legacy = _legacy()
    fee_rate = float(cfg["execution"].get("fee_rate", 0.001))
    order_type = legacy.order_type_for("buy", cfg)
    fallback_market = entry_fallback_market_enabled(cfg)
    bot_order_id = legacy.new_bot_order_id("buy", reason)
    requested_price = None if order_type == "market" else float(price_brl)
    client_prefix = legacy.client_order_id_prefix(bot_order_id)
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
            client_order_id=(
                f"{client_prefix}-L1" if order_type == "limit" else f"{client_prefix}-M1"
            ),
            status="pending_submit",
            requested_price_brl=requested_price,
            requested_brl_value=float(brl_value),
            details={"client_order_id_prefix": client_prefix},
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
                details={"execution_report": dict(fill.get("execution_report") or {})},
            )
        except Exception as exc:
            legacy.mark_dispatch_unknown(
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
        store.clear_dispatch_lock(bot_order_id, terminal_status="terminal")
    else:
        exec_price = float(price_brl)
        exec_quote = float(brl_value)
        exec_qty = exec_quote / max(exec_price, 1e-9)
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
    tp_price, stop_price = legacy.compute_exit_targets(
        qty_usdt=new_qty, brl_spent=new_spent, avg_price_brl=avg, params=params, cfg=cfg
    )
    safety_count = position.safety_count + (1 if position.status == "open" else 0)
    store.add_trade(
        side="buy",
        price_brl=exec_price,
        qty_usdt=exec_qty,
        brl_value=exec_quote,
        fee_brl=fee,
        reason=reason,
        mode=str(cfg["execution"]["mode"]),
        regime=regime,
    )
    if position.status == "flat":
        store.open_cycle(
            regime=regime, entry_price_brl=exec_price, qty_usdt=new_qty, brl_spent=new_spent
        )
    else:
        store.sync_open_cycle(qty_usdt=new_qty, brl_spent=new_spent, safety_count=safety_count)
    updated = store.update_position(
        status="open",
        qty_usdt=new_qty,
        brl_spent=new_spent,
        avg_price_brl=avg,
        tp_price_brl=tp_price,
        stop_price_brl=stop_price,
        safety_count=safety_count,
        regime=regime,
        trailing_active=0,
        trailing_anchor_brl=0.0,
        unrealized_pnl_brl=(new_qty * exec_price) - new_spent,
    )
    clear_reentry_price_block(store)
    store.add_event(
        "INFO",
        "buy_executed",
        {
            "reason": reason,
            "price_brl": exec_price,
            "brl_value": exec_quote,
            "qty_usdt": exec_qty,
            "order_type": order_type,
            "bot_order_id": bot_order_id,
        },
    )
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
    legacy = _legacy()
    fee_rate = float(cfg["execution"].get("fee_rate", 0.001))
    order_type = choose_exit_order_type(reason, cfg, params)
    fallback_market = False
    bot_order_id = legacy.new_bot_order_id("sell", reason)
    requested_price = None if order_type == "market" else float(price_brl)
    client_prefix = legacy.client_order_id_prefix(bot_order_id)
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
            client_order_id=(
                f"{client_prefix}-L1" if order_type == "limit" else f"{client_prefix}-M1"
            ),
            status="pending_submit",
            requested_price_brl=requested_price,
            requested_qty_usdt=float(position.qty_usdt),
            requested_brl_value=float(position.qty_usdt * (requested_price or price_brl)),
            details={"client_order_id_prefix": client_prefix},
        )
        if order_type == "limit" and reason in {"take_profit", "trailing_exit"}:
            store.add_event(
                "INFO",
                "profit_exit_limit_only",
                {
                    "reason": reason,
                    "price_brl": float(price_brl),
                    "qty_usdt": float(position.qty_usdt),
                },
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
                details={"execution_report": dict(fill.get("execution_report") or {})},
            )
        except Exception as exc:
            legacy.mark_dispatch_unknown(
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
        store.clear_dispatch_lock(bot_order_id, terminal_status="terminal")
    else:
        exec_qty = float(position.qty_usdt)
        exec_price = float(price_brl)
        gross = exec_qty * exec_price
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
    fee = gross * fee_rate
    net_received = gross - fee
    target_qty = float(position.qty_usdt)
    fill_ratio = min(1.0, exec_qty / max(target_qty, 1e-9))
    sold_cost_basis = float(position.brl_spent) * fill_ratio
    pnl_brl = net_received - sold_cost_basis
    pnl_pct = (pnl_brl / sold_cost_basis) * 100.0 if sold_cost_basis else 0.0
    realized = position.realized_pnl_brl + pnl_brl
    store.add_trade(
        side="sell",
        price_brl=exec_price,
        qty_usdt=exec_qty,
        brl_value=gross,
        fee_brl=fee,
        reason=reason,
        mode=str(cfg["execution"]["mode"]),
        regime=regime,
    )
    remaining_qty = max(0.0, target_qty - exec_qty)
    remaining_spent = max(0.0, float(position.brl_spent) - sold_cost_basis)
    if remaining_qty <= live_reconcile_qty_tolerance(cfg):
        store.close_latest_cycle(
            exit_price_brl=exec_price,
            brl_received=net_received,
            pnl_brl=pnl_brl,
            pnl_pct=pnl_pct,
            safety_count=position.safety_count,
            exit_reason=reason,
        )
        store.add_event(
            "INFO",
            "sell_executed",
            {
                "reason": reason,
                "price_brl": exec_price,
                "pnl_brl": pnl_brl,
                "qty_usdt": exec_qty,
                "order_type": order_type,
                "bot_order_id": bot_order_id,
            },
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
        updated = store.reset_position(realized_pnl_brl=realized)
        post_sell_controls(store, cfg, params, reason, exec_price)
        return updated
    remaining_avg = remaining_spent / max(remaining_qty, 1e-9)
    tp_price, stop_price = legacy.compute_exit_targets(
        qty_usdt=remaining_qty,
        brl_spent=remaining_spent,
        avg_price_brl=remaining_avg,
        params=params,
        cfg=cfg,
    )
    store.sync_open_cycle(
        qty_usdt=remaining_qty, brl_spent=remaining_spent, safety_count=position.safety_count
    )
    updated = store.update_position(
        status="open",
        qty_usdt=remaining_qty,
        brl_spent=remaining_spent,
        avg_price_brl=remaining_avg,
        tp_price_brl=tp_price,
        stop_price_brl=stop_price,
        safety_count=position.safety_count,
        regime=regime,
        trailing_active=position.trailing_active,
        trailing_anchor_brl=position.trailing_anchor_brl,
        realized_pnl_brl=realized,
        unrealized_pnl_brl=(remaining_qty * exec_price) - remaining_spent,
    )
    store.add_event(
        "WARN",
        "sell_partially_executed",
        {
            "reason": reason,
            "price_brl": exec_price,
            "qty_executed_usdt": exec_qty,
            "qty_remaining_usdt": remaining_qty,
            "pnl_brl": pnl_brl,
            "order_type": order_type,
            "bot_order_id": bot_order_id,
        },
    )
    return updated



