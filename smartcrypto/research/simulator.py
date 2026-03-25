from __future__ import annotations

import json
import math
import random
from typing import Any

import pandas as pd

from smartcrypto.domain.regime import compute_regime
from smartcrypto.domain.risk import min_profit_brl, min_profit_exit_price
from smartcrypto.domain.strategy import can_execute_sell_reason, compute_exit_targets, strategy_params
from smartcrypto.execution.controls import (
    build_safety_ladder,
    entry_fallback_market_enabled,
    exit_fallback_market_enabled,
    offset_price,
)


def timeframe_to_seconds(timeframe: str) -> int:
    value = str(timeframe or "15m").strip().lower()
    units = {"m": 60, "h": 3600, "d": 86400, "w": 604800}
    try:
        amount = int(value[:-1])
        unit = value[-1]
        return max(60, amount * units.get(unit, 60))
    except Exception:
        return 900

def research_wait_bars(cfg: dict[str, Any]) -> int:
    wait_seconds = int(cfg.get("execution", {}).get("reprice_wait_seconds", 10) or 10)
    bar_seconds = timeframe_to_seconds(str(cfg.get("market", {}).get("timeframe", "15m")))
    return max(1, int(math.ceil(wait_seconds / max(1, bar_seconds))))

def synthetic_limit_fill_ratio(side: str, price_brl: float, row: pd.Series) -> float:
    low_price = float(row["low"])
    high_price = float(row["high"])
    open_price = float(row["open"])
    close_price = float(row["close"])
    if price_brl < low_price - 1e-12 or price_brl > high_price + 1e-12:
        return 0.0
    favorable_close = close_price <= price_brl if side == "buy" else close_price >= price_brl
    if favorable_close:
        return 1.0
    span = max(high_price - low_price, 1e-9)
    if side == "buy":
        penetration = (high_price - price_brl) / span
        open_help = 0.15 if open_price <= price_brl else 0.0
    else:
        penetration = (price_brl - low_price) / span
        open_help = 0.15 if open_price >= price_brl else 0.0
    return max(0.25, min(0.95, 0.35 + penetration * 0.5 + open_help))

def build_synthetic_ohlcv_from_close(
    base: pd.DataFrame, synthetic_close: pd.Series
) -> pd.DataFrame:
    synthetic_close = synthetic_close.astype(float).reset_index(drop=True)
    work = base.iloc[: len(synthetic_close)].copy().reset_index(drop=True)
    orig_close = (
        base["close"]
        .astype(float)
        .reset_index(drop=True)
        .replace(0.0, pd.NA)
        .ffill()
        .bfill()
        .fillna(1.0)
    )
    prev_orig_close = orig_close.shift(1).fillna(orig_close)
    high_scale = (
        base["high"].astype(float).reset_index(drop=True)
        / pd.concat(
            [
                base["open"].astype(float).reset_index(drop=True),
                base["close"].astype(float).reset_index(drop=True),
            ],
            axis=1,
        )
        .max(axis=1)
        .replace(0.0, pd.NA)
    ).fillna(1.0)
    low_scale = (
        base["low"].astype(float).reset_index(drop=True)
        / pd.concat(
            [
                base["open"].astype(float).reset_index(drop=True),
                base["close"].astype(float).reset_index(drop=True),
            ],
            axis=1,
        )
        .min(axis=1)
        .replace(0.0, pd.NA)
    ).fillna(1.0)
    gap_returns = (
        (base["open"].astype(float).reset_index(drop=True) / prev_orig_close)
        .replace([pd.NA, float("inf"), -float("inf")], 1.0)
        .fillna(1.0)
    )
    synthetic_open = (
        synthetic_close.shift(1).fillna(synthetic_close.iloc[0])
        * gap_returns.iloc[: len(synthetic_close)].astype(float).values
    )
    work["close"] = synthetic_close.values
    work["open"] = synthetic_open.values
    max_oc = work[["open", "close"]].max(axis=1)
    min_oc = work[["open", "close"]].min(axis=1)
    work["high"] = (max_oc * high_scale.iloc[: len(work)].clip(lower=1.0).values).astype(float)
    work["low"] = (min_oc * low_scale.iloc[: len(work)].clip(upper=1.0).values).astype(float)
    work["high"] = work[["high", "open", "close"]].max(axis=1)
    work["low"] = work[["low", "open", "close"]].min(axis=1)
    return work

def block_bootstrap_ohlcv(data: pd.DataFrame, runs_seed: int, block_size: int) -> pd.DataFrame:
    base = data.copy().reset_index(drop=True)
    if len(base) < max(80, block_size + 10):
        return base
    rng = random.Random(int(runs_seed))
    close = base["close"].astype(float).reset_index(drop=True)
    returns = close.pct_change().fillna(0.0).reset_index(drop=True)
    sampled_indices: list[int] = []
    while len(sampled_indices) < len(base):
        start = rng.randint(1, max(1, len(base) - block_size))
        sampled_indices.extend(list(range(start, min(len(base), start + block_size))))
    sampled_indices = sampled_indices[: len(base) - 1]
    sampled_returns = returns.iloc[sampled_indices].reset_index(drop=True)
    synthetic_close = [float(close.iloc[0])]
    for ret in sampled_returns:
        synthetic_close.append(max(0.0001, synthetic_close[-1] * (1.0 + float(ret))))
    synthetic_close_series = pd.Series(synthetic_close[: len(base)], dtype=float)
    sampled_rows = base.iloc[[0] + sampled_indices].reset_index(drop=True)
    return build_synthetic_ohlcv_from_close(sampled_rows, synthetic_close_series)

def research_candidate_configs(
    cfg: dict[str, Any],
) -> list[tuple[dict[str, Any], dict[str, float]]]:
    base_tp = float(cfg.get("strategy", {}).get("take_profit_pct", 0.65) or 0.65)
    base_first = float(cfg.get("strategy", {}).get("first_buy_brl", 25.0) or 25.0)
    base_activation = float(cfg.get("strategy", {}).get("trailing_activation_pct", 0.45) or 0.45)
    base_callback = float(cfg.get("strategy", {}).get("trailing_callback_pct", 0.18) or 0.18)

    tp_candidates = sorted({round(max(0.15, base_tp * scale), 2) for scale in (0.8, 1.0, 1.2, 1.4)})
    first_candidates = sorted(
        {round(max(5.0, base_first * scale), 2) for scale in (0.75, 1.0, 1.25)}
    )
    activation_candidates = sorted(
        {round(max(0.1, base_activation * scale), 2) for scale in (0.8, 1.0, 1.2)}
    )
    callback_candidates = sorted(
        {round(max(0.05, base_callback * scale), 2) for scale in (0.8, 1.0, 1.2)}
    )

    variants: list[tuple[dict[str, Any], dict[str, float]]] = []
    for tp in tp_candidates:
        for first_buy in first_candidates:
            for activation in activation_candidates:
                for callback in callback_candidates:
                    if callback >= activation:
                        continue
                    cfg_local = json.loads(json.dumps(cfg))
                    cfg_local.setdefault("strategy", {})
                    cfg_local["strategy"]["take_profit_pct"] = float(tp)
                    cfg_local["strategy"]["first_buy_brl"] = float(first_buy)
                    cfg_local["strategy"]["trailing_activation_pct"] = float(activation)
                    cfg_local["strategy"]["trailing_callback_pct"] = float(callback)
                    variants.append(
                        (
                            cfg_local,
                            {
                                "take_profit_pct": float(tp),
                                "first_buy_brl": float(first_buy),
                                "trailing_activation_pct": float(activation),
                                "trailing_callback_pct": float(callback),
                            },
                        )
                    )
    return variants

def todays_realized_loss_brl(store: StateStore) -> float:

    df = store.read_df("cycles", 2000)
    if df.empty or "closed_at" not in df.columns:
        return 0.0
    closed = df.copy()
    closed["closed_at"] = pd.to_datetime(closed["closed_at"], errors="coerce", utc=True)
    today = pd.Timestamp.utcnow().normalize()
    closed = closed[closed["closed_at"] >= today]
    if closed.empty or "pnl_brl" not in closed.columns:
        return 0.0
    return float(closed["pnl_brl"].fillna(0.0).sum())

def simulate_strategy(cfg: dict[str, Any], ohlcv: pd.DataFrame) -> dict[str, Any]:
    if ohlcv.empty or len(ohlcv) < 80:
        return {
            "bars": int(len(ohlcv)),
            "trades": 0,
            "closed_cycles": 0,
            "pnl_brl": 0.0,
            "win_rate_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "avg_cycle_pnl_brl": 0.0,
            "final_equity_brl": round(
                float(cfg.get("portfolio", {}).get("initial_cash_brl", 0.0) or 0.0), 2
            ),
            "open_position_brl": 0.0,
            "limit_fill_count": 0,
            "market_fill_count": 0,
            "partial_fill_count": 0,
            "fill_rate_pct": 0.0,
            "reprice_count": 0,
            "fallback_market_count": 0,
            "avg_hold_bars": 0.0,
            "methodology": "v9_2_research_live_like_v2",
        }

    data = ohlcv.copy().reset_index(drop=True)
    fee_rate = float(cfg["execution"].get("fee_rate", 0.001))
    initial_cash = float(cfg["portfolio"]["initial_cash_brl"])
    cash = initial_cash
    realized = 0.0
    closed_cycles: list[float] = []
    cycle_hold_bars: list[int] = []
    equity_curve: list[float] = []
    wait_bars = research_wait_bars(cfg)
    max_reprices = max(0, int(cfg.get("execution", {}).get("reprice_attempts", 0) or 0))
    use_limit_orders = bool(cfg.get("execution", {}).get("limit_orders_enabled", True))

    stats: dict[str, Any] = {
        "orders_submitted": 0,
        "limit_submitted": 0,
        "market_submitted": 0,
        "limit_fill_count": 0,
        "market_fill_count": 0,
        "partial_fill_count": 0,
        "reprice_count": 0,
        "fallback_market_count": 0,
        "canceled_order_count": 0,
    }

    position: dict[str, Any] = {
        "status": "flat",
        "qty_usdt": 0.0,
        "brl_spent": 0.0,
        "avg_price_brl": 0.0,
        "safety_count": 0,
        "trailing_active": False,
        "trailing_anchor_brl": 0.0,
        "tp_price_brl": 0.0,
        "stop_price_brl": 0.0,
        "opened_index": None,
    }
    pending_order: dict[str, Any] | None = None
    reentry_price_below = 0.0

    def refresh_targets(params_local: dict[str, Any]) -> None:
        if position["qty_usdt"] <= 0:
            position["tp_price_brl"] = 0.0
            position["stop_price_brl"] = 0.0
            return
        tp_price, stop_price = compute_exit_targets(
            qty_usdt=float(position["qty_usdt"]),
            brl_spent=float(position["brl_spent"]),
            avg_price_brl=float(position["avg_price_brl"]),
            params=params_local,
            cfg=cfg,
        )
        position["tp_price_brl"] = float(tp_price)
        position["stop_price_brl"] = float(stop_price)

    def submit_order(
        *,
        side: str,
        reason: str,
        order_type: str,
        price_brl: float | None,
        brl_value: float | None,
        qty_usdt: float | None,
        fallback_market: bool,
        active_from_index: int,
    ) -> dict[str, Any]:
        stats["orders_submitted"] += 1
        if order_type == "limit":
            stats["limit_submitted"] += 1
        else:
            stats["market_submitted"] += 1
        return {
            "side": side,
            "reason": reason,
            "order_type": order_type,
            "price_brl": None if price_brl is None else float(price_brl),
            "remaining_brl_value": None if brl_value is None else float(brl_value),
            "remaining_qty_usdt": None if qty_usdt is None else float(qty_usdt),
            "fallback_market": bool(fallback_market),
            "active_from_index": int(active_from_index),
            "next_reprice_index": int(active_from_index + wait_bars),
            "attempts_done": 0,
        }

    def apply_buy(fill_price: float, brl_value: float, params_local: dict[str, Any]) -> float:
        nonlocal cash, reentry_price_below
        if brl_value <= 0 or fill_price <= 0:
            return 0.0
        affordable_value = min(float(brl_value), max(0.0, cash / (1.0 + fee_rate)))
        if affordable_value <= 0:
            return 0.0
        qty = affordable_value / fill_price
        fee = affordable_value * fee_rate
        total_cost = affordable_value + fee
        cash -= total_cost
        if position["status"] == "flat":
            position["opened_index"] = current_index
        position["status"] = "open"
        position["qty_usdt"] += qty
        position["brl_spent"] += total_cost
        position["avg_price_brl"] = position["brl_spent"] / max(position["qty_usdt"], 1e-9)
        position["trailing_active"] = False
        position["trailing_anchor_brl"] = 0.0
        reentry_price_below = 0.0
        refresh_targets(params_local)
        return affordable_value

    def apply_sell(fill_price: float, reason: str, qty_ratio: float = 1.0) -> float:
        nonlocal cash, realized, reentry_price_below
        qty_total = float(position["qty_usdt"])
        if qty_total <= 0 or fill_price <= 0:
            return 0.0
        qty_ratio = max(0.0, min(1.0, float(qty_ratio)))
        qty = qty_total * qty_ratio
        if qty <= 0:
            return 0.0
        cost_portion = float(position["brl_spent"]) * (qty / max(qty_total, 1e-9))
        gross = qty * fill_price
        fee = gross * fee_rate
        net = gross - fee
        pnl = net - cost_portion
        cash += net
        realized += pnl
        remaining_qty = max(0.0, qty_total - qty)
        remaining_spent = max(0.0, float(position["brl_spent"]) - cost_portion)
        if remaining_qty <= 1e-9:
            closed_cycles.append(pnl if qty_ratio >= 0.999 else pnl)
            if position["opened_index"] is not None:
                cycle_hold_bars.append(max(1, int(current_index - int(position["opened_index"]))))
            position.update(
                {
                    "status": "flat",
                    "qty_usdt": 0.0,
                    "brl_spent": 0.0,
                    "avg_price_brl": 0.0,
                    "safety_count": 0,
                    "trailing_active": False,
                    "trailing_anchor_brl": 0.0,
                    "tp_price_brl": 0.0,
                    "stop_price_brl": 0.0,
                    "opened_index": None,
                }
            )
            if reason in {"take_profit", "trailing_exit"}:
                reentry_price_below = fill_price * (1.0 - float(params["return_rebuy_pct"]))
            else:
                reentry_price_below = 0.0
        else:
            position["qty_usdt"] = remaining_qty
            position["brl_spent"] = remaining_spent
            position["avg_price_brl"] = remaining_spent / max(remaining_qty, 1e-9)
            refresh_targets(params)
        return pnl

    def maybe_fill_pending(row: pd.Series, params_local: dict[str, Any]) -> None:
        nonlocal pending_order
        if pending_order is None or current_index < int(pending_order["active_from_index"]):
            return
        order_type = str(pending_order["order_type"])
        side = str(pending_order["side"])
        touched_fill_ratio = 0.0
        fill_price = 0.0

        if order_type == "market":
            fill_price = float(row["open"])
            touched_fill_ratio = 1.0
        else:
            price_brl = float(pending_order["price_brl"] or 0.0)
            touched_fill_ratio = synthetic_limit_fill_ratio(side, price_brl, row)
            fill_price = price_brl

        if touched_fill_ratio > 0:
            if side == "buy":
                requested_value = float(pending_order["remaining_brl_value"] or 0.0)
                fill_value = requested_value * touched_fill_ratio
                executed_value = apply_buy(fill_price, fill_value, params_local)
                if executed_value <= 0:
                    pending_order = None
                    return
                executed_ratio = min(1.0, executed_value / max(requested_value, 1e-9))
                if executed_ratio < 0.999:
                    stats["partial_fill_count"] += 1
                    pending_order["remaining_brl_value"] = max(
                        0.0, requested_value - executed_value
                    )
                else:
                    pending_order["remaining_brl_value"] = 0.0
            else:
                qty_remaining = float(pending_order["remaining_qty_usdt"] or 0.0)
                sell_ratio = min(1.0, touched_fill_ratio)
                executed_qty = qty_remaining * sell_ratio
                if executed_qty <= 0:
                    return
                apply_sell(
                    fill_price,
                    str(pending_order["reason"]),
                    qty_ratio=executed_qty / max(float(position["qty_usdt"]), 1e-9),
                )
                if sell_ratio < 0.999 and position["status"] == "open":
                    stats["partial_fill_count"] += 1
                    pending_order["remaining_qty_usdt"] = max(0.0, qty_remaining - executed_qty)
                else:
                    pending_order["remaining_qty_usdt"] = 0.0

            if order_type == "limit":
                stats["limit_fill_count"] += 1
            else:
                stats["market_fill_count"] += 1

            if side == "buy" and float(pending_order.get("remaining_brl_value") or 0.0) <= 1e-6:
                pending_order = None
                return
            if side == "sell":
                remaining_qty = float(pending_order.get("remaining_qty_usdt") or 0.0)
                if remaining_qty <= 1e-9 or position["status"] == "flat":
                    pending_order = None
                    return

        if (
            order_type == "limit"
            and pending_order is not None
            and current_index >= int(pending_order["next_reprice_index"])
        ):
            if int(pending_order["attempts_done"]) < max_reprices:
                pending_order["attempts_done"] = int(pending_order["attempts_done"]) + 1
                pending_order["next_reprice_index"] = current_index + wait_bars
                pending_order["price_brl"] = offset_price(float(row["close"]), side, cfg)
                stats["reprice_count"] += 1
            elif bool(pending_order["fallback_market"]):
                pending_order["order_type"] = "market"
                pending_order["active_from_index"] = current_index + 1
                stats["fallback_market_count"] += 1
            elif current_index - int(pending_order["active_from_index"]) > max(wait_bars * 8, 12):
                stats["canceled_order_count"] += 1
                pending_order = None

    start_index = 60
    for current_index in range(start_index, len(data)):
        window = data.iloc[: current_index + 1]
        row = data.iloc[current_index]
        close_price = float(row["close"])
        high_price = float(row["high"])
        low_price = float(row["low"])
        regime, _, _ = compute_regime(window)
        params = strategy_params(cfg, regime)

        maybe_fill_pending(row, params)

        if position["status"] == "open":
            if bool(params["trailing_enabled"]):
                activation_price = max(
                    float(position["avg_price_brl"]) * (1.0 + float(params["trailing_activation"])),
                    min_profit_exit_price(
                        qty_usdt=float(position["qty_usdt"]),
                        brl_spent=float(position["brl_spent"]),
                        fee_rate=fee_rate,
                        desired_profit_brl=min_profit_brl(cfg),
                    ),
                )
                if high_price >= activation_price:
                    position["trailing_active"] = True
                    position["trailing_anchor_brl"] = max(
                        float(position["trailing_anchor_brl"]), high_price
                    )

            stop_triggered = bool(params["stop_loss_enabled"]) and low_price <= float(
                position["stop_price_brl"]
            )
            if stop_triggered:
                stop_fill = min(
                    float(position["stop_price_brl"]),
                    max(low_price, min(close_price, float(position["stop_price_brl"]))),
                )
                pending_order = None
                apply_sell(stop_fill, "stop_loss", qty_ratio=1.0)
                stats["market_fill_count"] += 1
            elif position["status"] == "open":
                if bool(position["trailing_active"]):
                    position["trailing_anchor_brl"] = max(
                        float(position["trailing_anchor_brl"]), high_price
                    )
                    trailing_price = float(position["trailing_anchor_brl"]) * (
                        1.0 - float(params["trailing_callback"])
                    )
                    if (
                        low_price <= trailing_price
                        and pending_order is None
                        and can_execute_sell_reason(
                            qty_usdt=float(position["qty_usdt"]),
                            brl_spent=float(position["brl_spent"]),
                            price_brl=trailing_price,
                            reason="trailing_exit",
                            cfg=cfg,
                        )
                    ):
                        pending_order = submit_order(
                            side="sell",
                            reason="trailing_exit",
                            order_type="limit" if use_limit_orders else "market",
                            price_brl=(
                                offset_price(max(trailing_price, close_price), "sell", cfg)
                                if use_limit_orders
                                else None
                            ),
                            brl_value=None,
                            qty_usdt=float(position["qty_usdt"]),
                            fallback_market=exit_fallback_market_enabled(
                                cfg, "trailing_exit", params
                            ),
                            active_from_index=current_index + 1,
                        )
                elif high_price >= float(position["tp_price_brl"]) and pending_order is None:
                    exit_ref = max(float(position["tp_price_brl"]), close_price)
                    if can_execute_sell_reason(
                        qty_usdt=float(position["qty_usdt"]),
                        brl_spent=float(position["brl_spent"]),
                        price_brl=exit_ref,
                        reason="take_profit",
                        cfg=cfg,
                    ):
                        pending_order = submit_order(
                            side="sell",
                            reason="take_profit",
                            order_type="limit" if use_limit_orders else "market",
                            price_brl=(
                                offset_price(exit_ref, "sell", cfg) if use_limit_orders else None
                            ),
                            brl_value=None,
                            qty_usdt=float(position["qty_usdt"]),
                            fallback_market=exit_fallback_market_enabled(
                                cfg, "take_profit", params
                            ),
                            active_from_index=current_index + 1,
                        )

            while position["status"] == "open" and pending_order is None:
                ladder = build_safety_ladder(
                    float(position["avg_price_brl"]),
                    params,
                    int(position["safety_count"]),
                    float(position["brl_spent"]),
                )
                next_row = next(
                    (step for step in ladder if str(step.get("status", "")).lower() == "ready"),
                    None,
                )
                if not next_row or low_price > float(next_row["trigger_price_brl"]):
                    break
                max_open = float(cfg["risk"].get("max_open_brl", params["max_cycle_brl"]))
                remaining_budget = max(
                    0.0, float(params["max_cycle_brl"]) - float(position["brl_spent"])
                )
                remaining_open = max(0.0, max_open - float(position["brl_spent"]))
                order_brl = min(
                    float(next_row["order_brl"]),
                    max(0.0, cash / (1.0 + fee_rate)),
                    remaining_budget,
                    remaining_open,
                )
                if order_brl <= 0:
                    break
                pending_order = submit_order(
                    side="buy",
                    reason=f"safety_{int(next_row['step_index'])}",
                    order_type="limit" if use_limit_orders else "market",
                    price_brl=offset_price(close_price, "buy", cfg) if use_limit_orders else None,
                    brl_value=order_brl,
                    qty_usdt=None,
                    fallback_market=entry_fallback_market_enabled(cfg),
                    active_from_index=current_index + 1,
                )
                position["safety_count"] = int(position["safety_count"]) + 1
                break

        if position["status"] == "flat" and pending_order is None:
            max_open = float(cfg["risk"].get("max_open_brl", params["max_cycle_brl"]))
            reentry_ok = reentry_price_below <= 0 or close_price <= reentry_price_below
            order_brl = min(
                float(params["first_buy_brl"]),
                max(0.0, cash / (1.0 + fee_rate)),
                max_open,
                float(params["max_cycle_brl"]),
            )
            if order_brl > 0 and reentry_ok and bool(params["enabled"]):
                pending_order = submit_order(
                    side="buy",
                    reason="initial_entry",
                    order_type="limit" if use_limit_orders else "market",
                    price_brl=offset_price(close_price, "buy", cfg) if use_limit_orders else None,
                    brl_value=order_brl,
                    qty_usdt=None,
                    fallback_market=entry_fallback_market_enabled(cfg),
                    active_from_index=current_index + 1,
                )

        open_value = float(position["qty_usdt"]) * close_price
        equity_curve.append(cash + open_value)

    if position["status"] == "open":
        last_close = float(data["close"].astype(float).iloc[-1])
        open_value = float(position["qty_usdt"]) * last_close
        equity_curve.append(cash + open_value)
    final_equity = float(equity_curve[-1]) if equity_curve else float(initial_cash)
    equity_series = pd.Series(equity_curve or [initial_cash], dtype=float)
    running_peak = equity_series.cummax().replace(0, pd.NA).ffill().fillna(initial_cash)
    max_drawdown_pct = float((((equity_series / running_peak) - 1.0) * 100.0).min())
    wins = sum(1 for pnl in closed_cycles if pnl > 0)
    trades = len(closed_cycles)
    win_rate_pct = (wins / trades) * 100.0 if trades else 0.0
    avg_cycle_pnl = float(sum(closed_cycles) / trades) if trades else 0.0
    fill_events = stats["limit_fill_count"] + stats["market_fill_count"]
    fill_rate_pct = (
        (fill_events / stats["orders_submitted"] * 100.0) if stats["orders_submitted"] else 0.0
    )
    avg_hold_bars = float(sum(cycle_hold_bars) / len(cycle_hold_bars)) if cycle_hold_bars else 0.0

    return {
        "bars": int(len(data)),
        "trades": trades,
        "closed_cycles": trades,
        "pnl_brl": round(realized, 2),
        "win_rate_pct": round(win_rate_pct, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "avg_cycle_pnl_brl": round(avg_cycle_pnl, 4),
        "final_equity_brl": round(final_equity, 2),
        "open_position_brl": (
            round(float(position["qty_usdt"]) * float(data["close"].iloc[-1]), 2)
            if position["status"] == "open"
            else 0.0
        ),
        "limit_fill_count": int(stats["limit_fill_count"]),
        "market_fill_count": int(stats["market_fill_count"]),
        "partial_fill_count": int(stats["partial_fill_count"]),
        "fill_rate_pct": round(fill_rate_pct, 2),
        "reprice_count": int(stats["reprice_count"]),
        "fallback_market_count": int(stats["fallback_market_count"]),
        "canceled_order_count": int(stats["canceled_order_count"]),
        "avg_hold_bars": round(avg_hold_bars, 2),
        "methodology": "v9_2_research_live_like_v2",
    }

