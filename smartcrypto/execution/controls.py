from __future__ import annotations

import time
from typing import Any

from smartcrypto.state.store import PositionState, StateStore, utc_now


def order_type_for(side: str, cfg: dict[str, Any]) -> str:
    if not bool(cfg.get("execution", {}).get("limit_orders_enabled", True)):
        return "market"
    return str(
        cfg["execution"].get("entry_order_type" if side == "buy" else "exit_order_type", "limit")
    )


def offset_price(price_brl: float, side: str, cfg: dict[str, Any]) -> float:
    if not bool(cfg.get("execution", {}).get("limit_orders_enabled", True)):
        return float(price_brl)
    if side == "buy":
        bps = float(cfg["execution"].get("buy_price_offset_bps", 0.0))
        return float(price_brl) * (1.0 - bps / 10000.0)
    bps = float(cfg["execution"].get("sell_price_offset_bps", 0.0))
    return float(price_brl) * (1.0 + bps / 10000.0)


def is_live_mode(cfg: dict[str, Any]) -> bool:
    return str(cfg.get("execution", {}).get("mode", "dry_run")).lower() == "live"


def fallback_market_enabled(cfg: dict[str, Any]) -> bool:
    return bool(cfg.get("execution", {}).get("fallback_market", False))


def entry_fallback_market_enabled(cfg: dict[str, Any]) -> bool:
    execution_cfg = cfg.get("execution", {}) or {}
    if "entry_fallback_market" in execution_cfg:
        return bool(execution_cfg.get("entry_fallback_market", False))
    return fallback_market_enabled(cfg)


def exit_fallback_market_enabled(cfg: dict[str, Any], reason: str, params: dict[str, Any]) -> bool:
    return False


def choose_exit_order_type(reason: str, cfg: dict[str, Any], params: dict[str, Any]) -> str:
    if reason == "force_sell" and bool(cfg.get("execution", {}).get("force_sell_market", True)):
        return "market"
    if reason == "stop_loss" and bool(params.get("stop_loss_market", False)):
        return "market"
    return order_type_for("sell", cfg)


def _flag_ts_to_epoch(value: Any) -> float | None:
    if value in (None, "", 0, 0.0, False):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except Exception:
        return None


def set_reentry_block(store: StateStore, seconds: int, reason: str) -> None:
    if seconds <= 0:
        store.set_flag("reentry_block_until", 0)
        return
    until_epoch = time.time() + int(seconds)
    store.set_flag("reentry_block_until", until_epoch)
    store.add_event(
        "WARN",
        "reentry_block_set",
        {"reason": reason, "seconds": int(seconds), "until_epoch": until_epoch},
    )


def reentry_remaining_seconds(store: StateStore) -> int:
    value = store.get_flag("reentry_block_until", 0)
    try:
        until_epoch = float(value or 0.0)
    except Exception:
        until_epoch = 0.0
    if until_epoch <= 0:
        return 0
    return max(0, int(until_epoch - time.time()))


def clear_reentry_price_block(store: StateStore) -> None:
    store.set_flag("reentry_price_below", 0)


def set_reentry_price_block(
    store: StateStore, exit_price_brl: float, params: dict[str, Any], reason: str
) -> None:
    return_rebuy_pct = float(params.get("return_rebuy_pct", 0.0) or 0.0)
    if return_rebuy_pct <= 0 or exit_price_brl <= 0:
        clear_reentry_price_block(store)
        return
    trigger_price = exit_price_brl * (1.0 - return_rebuy_pct)
    store.set_flag("reentry_price_below", trigger_price)
    store.add_event(
        "INFO",
        "reentry_price_block_set",
        {
            "reason": reason,
            "exit_price_brl": exit_price_brl,
            "return_rebuy_pct": return_rebuy_pct,
            "trigger_price_brl": trigger_price,
        },
    )


def reentry_price_threshold(store: StateStore) -> float:
    value = store.get_flag("reentry_price_below", 0)
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def post_sell_controls(
    store: StateStore,
    cfg: dict[str, Any],
    params: dict[str, Any],
    reason: str,
    exit_price_brl: float,
) -> None:
    pause_after_sell = bool(params.get("deactivate_after_sell", False)) or bool(
        store.get_flag("pause_after_sell_requested", False)
    )
    cooldown = 0
    runtime = cfg.get("runtime", {})
    if reason == "force_sell":
        pause_after_sell = True
        cooldown = int(runtime.get("cooldown_after_force_sell_seconds", 300) or 0)
    elif reason == "stop_loss":
        cooldown = int(runtime.get("cooldown_after_stop_loss_seconds", 900) or 0)
    elif reason in {"trailing_exit", "take_profit"}:
        cooldown = int(runtime.get("cooldown_after_profit_sell_seconds", 0) or 0)
    if pause_after_sell:
        store.set_flag("paused", True)
        store.set_flag("pause_after_sell_requested", False)
        store.add_event(
            "WARN",
            "bot_paused_after_sell",
            {"reason": reason, "requested": True},
        )
    if cooldown > 0:
        set_reentry_block(store, cooldown, reason)


def reconcile_flat_state(store: StateStore, reason: str) -> None:
    current = store.get_position()
    try:
        with store.conn() as c:
            c.execute(
                """
                update cycles
                set closed_at = coalesce(closed_at, ?),
                    exit_price_brl = coalesce(exit_price_brl, 0.0),
                    brl_received = coalesce(brl_received, 0.0),
                    pnl_brl = coalesce(pnl_brl, 0.0),
                    pnl_pct = coalesce(pnl_pct, 0.0),
                    exit_reason = coalesce(exit_reason, ?),
                    status = 'closed'
                where status = 'open'
                """,
                (utc_now(), reason),
            )
    except Exception:
        pass
    store.replace_planned_orders([])
    store.replace_safety_ladder([])
    store.reset_position(realized_pnl_brl=current.realized_pnl_brl)


def build_safety_ladder(
    avg_price: float,
    params: dict[str, Any],
    filled_count: int,
    current_spent: float,
) -> list[dict[str, float | int | str]]:
    rows: list[dict[str, float | int | str]] = []
    budget_cap = float(params["max_cycle_brl"])
    cumulative = float(params["first_buy_brl"])
    for i, row in enumerate(params["ramps"], start=1):
        order_brl = float(params["first_buy_brl"]) * float(row["multiplier"])
        if cumulative + order_brl > budget_cap + 1e-9:
            break
        cumulative += order_brl
        trigger = avg_price * (1.0 - float(row["drop_pct"]) / 100.0)
        expected_qty = order_brl / max(trigger, 1e-9)
        rows.append(
            {
                "step_index": i,
                "trigger_price_brl": round(trigger, 6),
                "order_brl": round(order_brl, 2),
                "expected_qty_usdt": round(expected_qty, 6),
                "drop_pct": round(float(row["drop_pct"]), 4),
                "multiplier": round(float(row["multiplier"]), 6),
                "status": "filled" if i <= filled_count else "ready",
            }
        )
    return rows


def replace_dashboard_orders(
    store: StateStore,
    position: PositionState,
    ladder: list[dict[str, Any]],
    cfg: dict[str, Any],
    params: dict[str, Any],
    *,
    allow_new_entries: bool = True,
) -> None:
    orders: list[dict[str, Any]] = []
    if position.status == "flat":
        if allow_new_entries:
            buy_type = order_type_for("buy", cfg)
            orders.append(
                {
                    "side": "buy",
                    "order_type": buy_type,
                    "price_brl": None if buy_type == "market" else None,
                    "qty_usdt": 0.0,
                    "brl_value": float(params["first_buy_brl"]),
                    "reason": "initial_entry",
                    "status": "planned",
                }
            )
    else:
        buy_type = order_type_for("buy", cfg)
        sell_type = order_type_for("sell", cfg)
        for row in ladder:
            if row["status"] == "ready":
                orders.append(
                    {
                        "side": "buy",
                        "order_type": buy_type,
                        "price_brl": float(row["trigger_price_brl"]) if buy_type == "limit" else None,
                        "qty_usdt": float(row["expected_qty_usdt"]),
                        "brl_value": float(row["order_brl"]),
                        "reason": f"safety_{int(row['step_index'])}",
                        "status": "planned",
                    }
                )
        if position.tp_price_brl > 0 and position.qty_usdt > 0:
            orders.append(
                {
                    "side": "sell",
                    "order_type": sell_type,
                    "price_brl": float(position.tp_price_brl) if sell_type == "limit" else None,
                    "qty_usdt": float(position.qty_usdt),
                    "brl_value": float(position.qty_usdt * position.tp_price_brl),
                    "reason": "take_profit",
                    "status": "planned",
                }
            )
    store.replace_planned_orders(orders)
