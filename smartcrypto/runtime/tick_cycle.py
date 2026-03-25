from __future__ import annotations

from typing import Any

from smartcrypto.execution.controls import (
    build_safety_ladder,
    is_live_mode,
    reconcile_flat_state,
    reentry_price_threshold,
    reentry_remaining_seconds,
    replace_dashboard_orders,
    set_reentry_block,
)
from smartcrypto.infra.binance_adapter import ExchangeAdapter
from smartcrypto.state.store import StateStore


def _legacy() -> Any:
    from smartcrypto.runtime import bot_runtime as legacy
    return legacy


def tick(cfg: dict[str, Any], store: StateStore, exchange: ExchangeAdapter) -> dict[str, Any]:
    legacy = _legacy()
    lookback = int(cfg["market"].get("lookback_bars", 240))
    ohlcv = exchange.fetch_ohlcv(cfg["market"]["timeframe"], lookback)
    legacy.write_market_cache(
        cfg, str(cfg["market"]["timeframe"]), ohlcv.tail(max(lookback, 1)).reset_index(drop=True)
    )
    last_price = float(ohlcv["close"].astype(float).iloc[-1])
    regime, regime_score, features = legacy.compute_regime(ohlcv)
    store.add_regime_observation(regime, regime_score, features)

    if is_live_mode(cfg) and bool(cfg.get("runtime", {}).get("reconcile_on_tick", True)):
        legacy.recover_dispatch_locks(cfg, store, exchange)
        legacy.reconcile_live_exchange_state(cfg, store, exchange, last_price=last_price)

    params = legacy.strategy_params(cfg, regime)
    for notice in legacy.strategy_runtime_diagnostics(params):
        flag_key = f"runtime_notice_{notice['code']}"
        if not bool(store.get_flag(flag_key, False)):
            store.add_event(str(notice["level"]), str(notice["code"]), dict(notice["payload"]))
            store.set_flag(flag_key, True)
    position = store.update_position(regime=regime)

    if legacy.active_dispatch_lock_present(cfg, store):
        ladder = (
            build_safety_ladder(
                position.avg_price_brl or last_price,
                params,
                position.safety_count,
                position.brl_spent,
            )
            if position.status == "open"
            else []
        )
        store.replace_safety_ladder(ladder)
        replace_dashboard_orders(store, position, ladder, cfg, params, allow_new_entries=False)
        unrealized = position.qty_usdt * last_price - position.brl_spent
        position = store.update_position(unrealized_pnl_brl=unrealized, regime=regime)
        legacy.log_snapshot(
            store,
            price=last_price,
            position=position,
            cfg=cfg,
            regime=regime,
            meta={"action": "dispatch_lock_active"},
        )
        legacy.send_daily_report_if_due(store=store, cfg=cfg, position=position, last_price=last_price)
        return legacy.status_payload(store, last_price, cfg)

    if bool(store.get_flag("live_reconcile_required", False)):
        ladder = (
            build_safety_ladder(
                position.avg_price_brl or last_price,
                params,
                position.safety_count,
                position.brl_spent,
            )
            if position.status == "open"
            else []
        )
        store.replace_safety_ladder(ladder)
        replace_dashboard_orders(store, position, ladder, cfg, params, allow_new_entries=False)
        unrealized = position.qty_usdt * last_price - position.brl_spent
        position = store.update_position(unrealized_pnl_brl=unrealized, regime=regime)
        legacy.log_snapshot(
            store,
            price=last_price,
            position=position,
            cfg=cfg,
            regime=regime,
            meta={"action": "reconcile_required"},
        )
        legacy.send_daily_report_if_due(store=store, cfg=cfg, position=position, last_price=last_price)
        return legacy.status_payload(store, last_price, cfg)

    if bool(store.get_flag("reset_cycle_requested", False)):
        if is_live_mode(cfg) and position.status == "open":
            store.set_flag("reset_cycle_requested", False)
            store.add_event(
                "ERROR",
                "reset_blocked_live_open_position",
                {"reason": "position_open_on_exchange_must_be_closed_first"},
            )
            legacy.log_snapshot(
                store,
                price=last_price,
                position=position,
                cfg=cfg,
                regime=regime,
                meta={"action": "reset_blocked"},
            )
            legacy.send_daily_report_if_due(store=store, cfg=cfg, position=position, last_price=last_price)
            return legacy.status_payload(store, last_price, cfg)
        reconcile_flat_state(store, reason="reset")
        store.set_flag("reset_cycle_requested", False)
        reset_cooldown = int(cfg.get("runtime", {}).get("cooldown_after_reset_seconds", 300) or 0)
        if reset_cooldown > 0:
            set_reentry_block(store, reset_cooldown, "reset")
        store.add_event("WARN", "cycle_reset_from_dashboard", {})
        position = store.get_position()
        legacy.log_snapshot(
            store,
            price=last_price,
            position=position,
            cfg=cfg,
            regime=regime,
            meta={"action": "reset"},
        )
        legacy.send_daily_report_if_due(store=store, cfg=cfg, position=position, last_price=last_price)
        return legacy.status_payload(store, last_price, cfg)

    if bool(store.get_flag("paused", False)) or not params["enabled"]:
        ladder = (
            build_safety_ladder(
                position.avg_price_brl or last_price,
                params,
                position.safety_count,
                position.brl_spent,
            )
            if position.status == "open"
            else []
        )
        store.replace_safety_ladder(ladder)
        replace_dashboard_orders(store, position, ladder, cfg, params)
        unrealized = position.qty_usdt * last_price - position.brl_spent
        position = store.update_position(unrealized_pnl_brl=unrealized, regime=regime)
        legacy.log_snapshot(
            store,
            price=last_price,
            position=position,
            cfg=cfg,
            regime=regime,
            meta={"action": "paused_or_disabled"},
        )
        legacy.send_daily_report_if_due(store=store, cfg=cfg, position=position, last_price=last_price)
        return legacy.status_payload(store, last_price, cfg)

    daily_loss_limit = float(cfg.get("risk", {}).get("max_daily_loss_brl", 0.0))
    current_unrealized_loss = min(0.0, float(position.qty_usdt * last_price - position.brl_spent))
    todays_total_loss = legacy.todays_realized_loss_brl(store) + current_unrealized_loss
    if daily_loss_limit > 0 and todays_total_loss <= -abs(daily_loss_limit):
        store.set_flag("paused", True)
        store.add_event(
            "WARN",
            "daily_loss_limit_hit",
            {
                "limit_brl": daily_loss_limit,
                "todays_realized_brl": legacy.todays_realized_loss_brl(store),
                "current_unrealized_brl": current_unrealized_loss,
                "total_loss_brl": todays_total_loss,
            },
        )
        legacy.send_daily_report_if_due(store=store, cfg=cfg, position=position, last_price=last_price)
        return legacy.status_payload(store, last_price, cfg)

    if bool(store.get_flag("force_sell_requested", False)) and position.status == "open":
        position = legacy.execute_sell(
            store=store,
            position=position,
            exchange=exchange,
            price_brl=legacy.offset_price(last_price, "sell", cfg),
            reason="force_sell",
            regime=regime,
            cfg=cfg,
            params=params,
        )
        store.set_flag("force_sell_requested", False)

    position = store.get_position()

    if position.status == "flat":
        remaining_reentry_block = reentry_remaining_seconds(store)
        if remaining_reentry_block > 0:
            replace_dashboard_orders(store, position, [], cfg, params, allow_new_entries=False)
            legacy.log_snapshot(
                store,
                price=last_price,
                position=position,
                cfg=cfg,
                regime=regime,
                meta={"action": "reentry_blocked", "remaining_seconds": remaining_reentry_block},
            )
            legacy.send_daily_report_if_due(store=store, cfg=cfg, position=position, last_price=last_price)
            return legacy.status_payload(store, last_price, cfg)
        price_reentry_threshold = reentry_price_threshold(store)
        if price_reentry_threshold > 0 and last_price > price_reentry_threshold:
            replace_dashboard_orders(store, position, [], cfg, params, allow_new_entries=False)
            legacy.log_snapshot(
                store,
                price=last_price,
                position=position,
                cfg=cfg,
                regime=regime,
                meta={
                    "action": "reentry_price_blocked",
                    "trigger_price_brl": price_reentry_threshold,
                },
            )
            legacy.send_daily_report_if_due(store=store, cfg=cfg, position=position, last_price=last_price)
            return legacy.status_payload(store, last_price, cfg)
        initial_cash = float(cfg["portfolio"]["initial_cash_brl"])
        current_cash = legacy.cash_available(initial_cash, position)
        max_open = float(cfg["risk"].get("max_open_brl", params["max_cycle_brl"]))
        order_brl = min(
            float(params["first_buy_brl"]), current_cash, max_open, float(params["max_cycle_brl"])
        )
        if order_brl > 0:
            position = legacy.execute_buy(
                store=store,
                position=position,
                exchange=exchange,
                price_brl=legacy.offset_price(last_price, "buy", cfg),
                brl_value=order_brl,
                reason="initial_entry",
                regime=regime,
                cfg=cfg,
                params=params,
            )
    else:
        ladder = build_safety_ladder(
            position.avg_price_brl, params, position.safety_count, position.brl_spent
        )
        next_row = None
        for row in ladder:
            if row["status"] == "ready":
                next_row = row
                break
        if next_row and last_price <= float(next_row["trigger_price_brl"]):
            initial_cash = float(cfg["portfolio"]["initial_cash_brl"])
            current_cash = legacy.cash_available(initial_cash, position)
            remaining_budget = max(0.0, float(params["max_cycle_brl"]) - position.brl_spent)
            remaining_open = max(
                0.0,
                float(cfg["risk"].get("max_open_brl", params["max_cycle_brl"]))
                - position.brl_spent,
            )
            order_brl = min(
                float(next_row["order_brl"]), current_cash, remaining_budget, remaining_open
            )
            if order_brl > 0:
                position = legacy.execute_buy(
                    store=store,
                    position=position,
                    exchange=exchange,
                    price_brl=legacy.offset_price(last_price, "buy", cfg),
                    brl_value=order_brl,
                    reason=f"safety_{int(next_row['step_index'])}",
                    regime=regime,
                    cfg=cfg,
                    params=params,
                )

        position = store.get_position()
        if position.status == "open":
            trailing_active = int(position.trailing_active)
            anchor = float(position.trailing_anchor_brl)
            if bool(params["trailing_enabled"]):
                profit_floor_price = min_profit_exit_price(
                    qty_usdt=float(position.qty_usdt),
                    brl_spent=float(position.brl_spent),
                    fee_rate=float(cfg["execution"].get("fee_rate", 0.001)),
                    desired_profit_brl=min_profit_brl(cfg),
                )
                activation_price = max(
                    position.avg_price_brl * (1.0 + float(params["trailing_activation"])),
                    profit_floor_price,
                )
                if last_price >= activation_price:
                    trailing_active = 1
                    anchor = max(anchor, last_price)
                if trailing_active:
                    anchor = max(anchor, last_price)
                    trailing_trigger_price = anchor * (1.0 - float(params["trailing_callback"]))
                    if last_price <= trailing_trigger_price and can_execute_sell_reason(
                        position=position,
                        price_brl=legacy.offset_price(last_price, "sell", cfg),
                        reason="trailing_exit",
                        cfg=cfg,
                    ):
                        position = legacy.execute_sell(
                            store=store,
                            position=position,
                            exchange=exchange,
                            price_brl=legacy.offset_price(last_price, "sell", cfg),
                            reason="trailing_exit",
                            regime=regime,
                            cfg=cfg,
                            params=params,
                        )
            position = store.get_position()
            if position.status == "open":
                if bool(params["stop_loss_enabled"]) and last_price <= position.stop_price_brl:
                    position = legacy.execute_sell(
                        store=store,
                        position=position,
                        exchange=exchange,
                        price_brl=legacy.offset_price(last_price, "sell", cfg),
                        reason="stop_loss",
                        regime=regime,
                        cfg=cfg,
                        params=params,
                    )
                elif (
                    last_price >= position.tp_price_brl
                    and not trailing_active
                    and can_execute_sell_reason(
                        position=position,
                        price_brl=legacy.offset_price(last_price, "sell", cfg),
                        reason="take_profit",
                        cfg=cfg,
                    )
                ):
                    position = legacy.execute_sell(
                        store=store,
                        position=position,
                        exchange=exchange,
                        price_brl=legacy.offset_price(last_price, "sell", cfg),
                        reason="take_profit",
                        regime=regime,
                        cfg=cfg,
                        params=params,
                    )
                else:
                    unrealized = position.qty_usdt * last_price - position.brl_spent
                    position = store.update_position(
                        unrealized_pnl_brl=unrealized,
                        trailing_active=trailing_active,
                        trailing_anchor_brl=anchor,
                        regime=regime,
                    )

    position = store.get_position()
    ladder = (
        build_safety_ladder(
            position.avg_price_brl or last_price, params, position.safety_count, position.brl_spent
        )
        if position.status == "open"
        else []
    )
    store.replace_safety_ladder(ladder)
    replace_dashboard_orders(store, position, ladder, cfg, params)
    legacy.log_snapshot(store, price=last_price, position=position, cfg=cfg, regime=regime)
    legacy.send_daily_report_if_due(store=store, cfg=cfg, position=position, last_price=last_price)
    return legacy.status_payload(store, last_price, cfg)



