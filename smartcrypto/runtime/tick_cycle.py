from __future__ import annotations

from typing import Any

from smartcrypto.domain.risk import min_profit_brl, min_profit_exit_price
from smartcrypto.domain.strategy import can_execute_sell_reason as domain_can_execute_sell_reason
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
from smartcrypto.runtime.ai_runtime import evaluate_runtime_ai
from smartcrypto.state.store import StateStore


def _legacy() -> Any:
    from smartcrypto.runtime import bot_runtime as legacy

    return legacy


def _set_baseline_decision(store: StateStore, decision: dict[str, Any]) -> None:
    payload = dict(decision or {})
    payload.setdefault("source", "runtime_tick")
    payload.setdefault("enabled", True)
    payload.setdefault("is_real", True)
    store.set_flag("ai_runtime_baseline_decision", payload)


def _open_position_ladder(position: Any, last_price: float, params: dict[str, Any]) -> list[dict[str, float]]:
    if str(position.status) != "open":
        return []
    return build_safety_ladder(
        float(position.avg_price_brl or last_price),
        params,
        int(position.safety_count),
        float(position.brl_spent),
    )


def _refresh_dashboard_orders(
    store: StateStore,
    position: Any,
    last_price: float,
    cfg: dict[str, Any],
    params: dict[str, Any],
    *,
    allow_new_entries: bool = True,
) -> list[dict[str, float]]:
    ladder = _open_position_ladder(position, last_price, params)
    store.replace_safety_ladder(ladder)
    replace_dashboard_orders(
        store,
        position,
        ladder,
        cfg,
        params,
        allow_new_entries=allow_new_entries,
    )
    return ladder


def _refresh_open_position_metrics(
    store: StateStore,
    position: Any,
    *,
    last_price: float,
    regime: str,
) -> Any:
    if str(position.status) != "open":
        return position
    unrealized = float(position.qty_usdt) * float(last_price) - float(position.brl_spent)
    return store.update_position(unrealized_pnl_brl=unrealized, regime=regime)


def _finalize_status(
    legacy: Any,
    store: StateStore,
    cfg: dict[str, Any],
    params: dict[str, Any],
    position: Any,
    *,
    last_price: float,
    regime: str,
    meta: dict[str, Any] | None = None,
    allow_new_entries: bool = True,
) -> dict[str, Any]:
    position = _refresh_open_position_metrics(
        store,
        position,
        last_price=last_price,
        regime=regime,
    )
    _refresh_dashboard_orders(
        store,
        position,
        last_price,
        cfg,
        params,
        allow_new_entries=allow_new_entries,
    )
    legacy.log_snapshot(
        store,
        price=last_price,
        position=position,
        cfg=cfg,
        regime=regime,
        meta=meta,
    )
    legacy.send_daily_report_if_due(
        store=store,
        cfg=cfg,
        position=position,
        last_price=last_price,
    )
    return legacy.status_payload(store, last_price, cfg)


def _can_execute_sell(
    *,
    position: Any,
    price_brl: float,
    reason: str,
    cfg: dict[str, Any],
) -> bool:
    return domain_can_execute_sell_reason(
        position=position,
        price_brl=float(price_brl),
        reason=reason,
        cfg=cfg,
    )


def _execute_sell_reason(
    legacy: Any,
    *,
    store: StateStore,
    position: Any,
    exchange: ExchangeAdapter,
    last_price: float,
    reason: str,
    regime: str,
    cfg: dict[str, Any],
    params: dict[str, Any],
) -> Any:
    return legacy.execute_sell(
        store=store,
        position=position,
        exchange=exchange,
        price_brl=legacy.offset_price(last_price, "sell", cfg),
        reason=reason,
        regime=regime,
        cfg=cfg,
        params=params,
    )


def tick(cfg: dict[str, Any], store: StateStore, exchange: ExchangeAdapter) -> dict[str, Any]:
    legacy = _legacy()
    lookback = int(cfg["market"].get("lookback_bars", 240))
    ohlcv = exchange.fetch_ohlcv(cfg["market"]["timeframe"], lookback)
    legacy.write_market_cache(
        cfg,
        str(cfg["market"]["timeframe"]),
        ohlcv.tail(max(lookback, 1)).reset_index(drop=True),
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
    ai_runtime = evaluate_runtime_ai(cfg, store, ohlcv)
    baseline_decision: dict[str, Any] = {
        "source": "runtime_tick",
        "enabled": True,
        "is_real": True,
        "position_status": str(position.status),
        "entry_gate": bool(position.status == "flat"),
        "position_action": "wait",
        "reason": "no_signal",
    }

    if legacy.active_dispatch_lock_present(cfg, store):
        baseline_decision.update({"entry_gate": False, "reason": "dispatch_lock_active"})
        _set_baseline_decision(store, baseline_decision)
        return _finalize_status(
            legacy,
            store,
            cfg,
            params,
            position,
            last_price=last_price,
            regime=regime,
            meta={"action": "dispatch_lock_active"},
            allow_new_entries=False,
        )

    if bool(store.get_flag("live_reconcile_required", False)):
        baseline_decision.update({"entry_gate": False, "reason": "reconcile_required"})
        _set_baseline_decision(store, baseline_decision)
        return _finalize_status(
            legacy,
            store,
            cfg,
            params,
            position,
            last_price=last_price,
            regime=regime,
            meta={"action": "reconcile_required"},
            allow_new_entries=False,
        )

    if bool(store.get_flag("reset_cycle_requested", False)):
        baseline_decision.update({"entry_gate": False, "reason": "reset_cycle_requested"})
        if is_live_mode(cfg) and position.status == "open":
            store.set_flag("reset_cycle_requested", False)
            store.add_event(
                "ERROR",
                "reset_blocked_live_open_position",
                {"reason": "position_open_on_exchange_must_be_closed_first"},
            )
            _set_baseline_decision(store, baseline_decision)
            return _finalize_status(
                legacy,
                store,
                cfg,
                params,
                position,
                last_price=last_price,
                regime=regime,
                meta={"action": "reset_blocked"},
            )
        reconcile_flat_state(store, reason="reset")
        store.set_flag("reset_cycle_requested", False)
        reset_cooldown = int(cfg.get("runtime", {}).get("cooldown_after_reset_seconds", 300) or 0)
        if reset_cooldown > 0:
            set_reentry_block(store, reset_cooldown, "reset")
        store.add_event("WARN", "cycle_reset_from_dashboard", {})
        position = store.get_position()
        _set_baseline_decision(store, baseline_decision)
        return _finalize_status(
            legacy,
            store,
            cfg,
            params,
            position,
            last_price=last_price,
            regime=regime,
            meta={"action": "reset"},
        )

    if bool(store.get_flag("paused", False)) or not params["enabled"]:
        baseline_decision.update({"entry_gate": False, "reason": "paused_or_disabled"})
        _set_baseline_decision(store, baseline_decision)
        return _finalize_status(
            legacy,
            store,
            cfg,
            params,
            position,
            last_price=last_price,
            regime=regime,
            meta={"action": "paused_or_disabled"},
        )

    daily_loss_limit = float(cfg.get("risk", {}).get("max_daily_loss_brl", 0.0))
    current_unrealized_loss = min(0.0, float(position.qty_usdt) * last_price - float(position.brl_spent))
    todays_total_loss = legacy.todays_realized_loss_brl(store) + current_unrealized_loss
    if daily_loss_limit > 0 and todays_total_loss <= -abs(daily_loss_limit):
        baseline_decision.update({"entry_gate": False, "reason": "daily_loss_limit_hit"})
        _set_baseline_decision(store, baseline_decision)
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
        return _finalize_status(
            legacy,
            store,
            cfg,
            params,
            position,
            last_price=last_price,
            regime=regime,
            meta={"action": "daily_loss_limit_hit"},
        )

    if bool(store.get_flag("force_sell_requested", False)) and position.status == "open":
        baseline_decision.update({"entry_gate": False, "position_action": "reduce", "reason": "force_sell"})
        position = _execute_sell_reason(
            legacy,
            store=store,
            position=position,
            exchange=exchange,
            last_price=last_price,
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
            baseline_decision.update({"entry_gate": False, "reason": "reentry_blocked"})
            _set_baseline_decision(store, baseline_decision)
            return _finalize_status(
                legacy,
                store,
                cfg,
                params,
                position,
                last_price=last_price,
                regime=regime,
                meta={"action": "reentry_blocked", "remaining_seconds": remaining_reentry_block},
                allow_new_entries=False,
            )

        price_reentry_limit = reentry_price_threshold(store)
        if price_reentry_limit > 0 and last_price > price_reentry_limit:
            baseline_decision.update({"entry_gate": False, "reason": "reentry_price_blocked"})
            _set_baseline_decision(store, baseline_decision)
            return _finalize_status(
                legacy,
                store,
                cfg,
                params,
                position,
                last_price=last_price,
                regime=regime,
                meta={"action": "reentry_price_blocked", "trigger_price_brl": price_reentry_limit},
                allow_new_entries=False,
            )

        initial_cash = float(cfg["portfolio"]["initial_cash_brl"])
        current_cash = legacy.cash_available(initial_cash, position)
        max_open_brl = float(cfg["risk"].get("max_open_brl", params["max_cycle_brl"]))
        order_brl = min(
            float(params["first_buy_brl"]),
            current_cash,
            max_open_brl,
            float(params["max_cycle_brl"]),
        )
        if order_brl > 0:
            baseline_decision.update(
                {
                    "entry_gate": True,
                    "position_action": "enter",
                    "reason": "initial_entry",
                    "order_brl": float(order_brl),
                }
            )
            if not bool(ai_runtime.get("effective_entry_gate", True)):
                _set_baseline_decision(store, baseline_decision)
                store.add_event(
                    "INFO",
                    "ai_entry_blocked",
                    {
                        "stage": ai_runtime.get("stage", "unknown"),
                        "reason": ai_runtime.get("reason", ""),
                    },
                )
                return _finalize_status(
                    legacy,
                    store,
                    cfg,
                    params,
                    position,
                    last_price=last_price,
                    regime=regime,
                    meta={"action": "ai_entry_blocked", "ai": ai_runtime},
                )
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
        ladder = _open_position_ladder(position, last_price, params)
        next_row = next((row for row in ladder if row["status"] == "ready"), None)
        allow_safety = str(ai_runtime.get("position_action", "wait")) not in {"reduce", "risk_off"}

        if next_row and allow_safety and last_price <= float(next_row["trigger_price_brl"]):
            initial_cash = float(cfg["portfolio"]["initial_cash_brl"])
            current_cash = legacy.cash_available(initial_cash, position)
            remaining_budget = max(0.0, float(params["max_cycle_brl"]) - float(position.brl_spent))
            remaining_open = max(
                0.0,
                float(cfg["risk"].get("max_open_brl", params["max_cycle_brl"])) - float(position.brl_spent),
            )
            order_brl = min(
                float(next_row["order_brl"]),
                current_cash,
                remaining_budget,
                remaining_open,
            )
            if order_brl > 0:
                baseline_decision.update(
                    {
                        "entry_gate": True,
                        "position_action": "add",
                        "reason": f"safety_{int(next_row['step_index'])}",
                        "order_brl": float(order_brl),
                    }
                )
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
            ai_position_action = str(ai_runtime.get("position_action", "wait"))
            sell_price = legacy.offset_price(last_price, "sell", cfg)

            if ai_position_action in {"risk_off", "take_profit"} and _can_execute_sell(
                position=position,
                price_brl=sell_price,
                reason=f"ai_{ai_position_action}",
                cfg=cfg,
            ):
                baseline_decision.update(
                    {
                        "entry_gate": False,
                        "position_action": "hold",
                        "reason": "ai_override_sell",
                    }
                )
                position = _execute_sell_reason(
                    legacy,
                    store=store,
                    position=position,
                    exchange=exchange,
                    last_price=last_price,
                    reason=f"ai_{ai_position_action}",
                    regime=regime,
                    cfg=cfg,
                    params=params,
                )
                store.add_event("INFO", "ai_position_action", {"action": ai_position_action})

            position = store.get_position()

        if position.status == "open":
            trailing_active = int(position.trailing_active)
            trailing_anchor = float(position.trailing_anchor_brl)
            sell_price = legacy.offset_price(last_price, "sell", cfg)

            if bool(params["trailing_enabled"]):
                profit_floor_price = min_profit_exit_price(
                    qty_usdt=float(position.qty_usdt),
                    brl_spent=float(position.brl_spent),
                    fee_rate=float(cfg["execution"].get("fee_rate", 0.001)),
                    desired_profit_brl=min_profit_brl(cfg),
                )
                activation_price = max(
                    float(position.avg_price_brl) * (1.0 + float(params["trailing_activation"])),
                    profit_floor_price,
                )

                if last_price >= activation_price:
                    trailing_active = 1
                    trailing_anchor = max(trailing_anchor, last_price)

                if trailing_active:
                    trailing_anchor = max(trailing_anchor, last_price)
                    trailing_trigger_price = trailing_anchor * (1.0 - float(params["trailing_callback"]))
                    if last_price <= trailing_trigger_price and _can_execute_sell(
                        position=position,
                        price_brl=sell_price,
                        reason="trailing_exit",
                        cfg=cfg,
                    ):
                        baseline_decision.update(
                            {
                                "entry_gate": False,
                                "position_action": "reduce",
                                "reason": "trailing_exit",
                            }
                        )
                        position = _execute_sell_reason(
                            legacy,
                            store=store,
                            position=position,
                            exchange=exchange,
                            last_price=last_price,
                            reason="trailing_exit",
                            regime=regime,
                            cfg=cfg,
                            params=params,
                        )

            position = store.get_position()

            if position.status == "open":
                if bool(params["stop_loss_enabled"]) and last_price <= float(position.stop_price_brl):
                    baseline_decision.update(
                        {
                            "entry_gate": False,
                            "position_action": "risk_off",
                            "reason": "stop_loss",
                        }
                    )
                    position = _execute_sell_reason(
                        legacy,
                        store=store,
                        position=position,
                        exchange=exchange,
                        last_price=last_price,
                        reason="stop_loss",
                        regime=regime,
                        cfg=cfg,
                        params=params,
                    )
                elif (
                    last_price >= float(position.tp_price_brl)
                    and not trailing_active
                    and _can_execute_sell(
                        position=position,
                        price_brl=sell_price,
                        reason="take_profit",
                        cfg=cfg,
                    )
                ):
                    baseline_decision.update(
                        {
                            "entry_gate": False,
                            "position_action": "take_profit",
                            "reason": "take_profit",
                        }
                    )
                    position = _execute_sell_reason(
                        legacy,
                        store=store,
                        position=position,
                        exchange=exchange,
                        last_price=last_price,
                        reason="take_profit",
                        regime=regime,
                        cfg=cfg,
                        params=params,
                    )
                else:
                    unrealized = float(position.qty_usdt) * last_price - float(position.brl_spent)
                    position = store.update_position(
                        unrealized_pnl_brl=unrealized,
                        trailing_active=trailing_active,
                        trailing_anchor_brl=trailing_anchor,
                        regime=regime,
                    )

    _set_baseline_decision(store, baseline_decision)
    position = store.get_position()
    return _finalize_status(
        legacy,
        store,
        cfg,
        params,
        position,
        last_price=last_price,
        regime=regime,
    )
