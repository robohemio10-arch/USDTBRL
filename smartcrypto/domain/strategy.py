from __future__ import annotations

from typing import Any

from smartcrypto.domain.models import SignalDecision
from smartcrypto.domain.risk import (
    effective_cycle_cap,
    estimate_exit_pnl_brl,
    min_profit_brl,
    min_profit_exit_price,
)


def default_signal() -> SignalDecision:
    return SignalDecision(
        should_buy=False,
        should_sell=False,
        confidence=0.0,
        reason="strategy_not_migrated_yet",
    )


def normalize_ramps(
    cfg: dict[str, Any], regime: str, first_buy_brl: float
) -> list[dict[str, float]]:
    del first_buy_brl
    raw = cfg.get("strategy", {}).get("ramps") or []
    ramps: list[dict[str, float]] = []
    if raw:
        for row in raw:
            drop_pct = float(row.get("drop_pct", 0.0))
            multiplier = float(row.get("multiplier", 1.0))
            if drop_pct > 0 and multiplier > 0:
                ramps.append({"drop_pct": drop_pct, "multiplier": multiplier})
    else:
        base_step = float(cfg["strategy"].get("safety_step_pct", 0.7))
        base_scale = float(cfg["strategy"].get("safety_volume_scale", 1.45))
        safety_orders = int(cfg["strategy"].get("safety_orders", 5))
        for index in range(1, safety_orders + 1):
            ramps.append(
                {
                    "drop_pct": round(base_step * index, 4),
                    "multiplier": round(base_scale ** (index - 1), 6),
                }
            )

    adjusted: list[dict[str, float]] = []
    for row in ramps:
        drop = float(row["drop_pct"])
        multiplier = float(row["multiplier"])
        if regime == "bull":
            drop *= 0.92
        elif regime == "bear":
            drop *= 1.12
            multiplier *= 0.96
        adjusted.append({"drop_pct": round(drop, 4), "multiplier": round(multiplier, 6)})
    return adjusted


def fit_ramps_to_cycle(
    ramps: list[dict[str, float]],
    *,
    first_buy_brl: float,
    cycle_cap_brl: float,
) -> tuple[list[dict[str, float]], int, float]:
    if first_buy_brl <= 0 or cycle_cap_brl <= 0:
        return [], len(ramps), 0.0
    fitted: list[dict[str, float]] = []
    cumulative = float(first_buy_brl)
    trimmed = 0
    for row in ramps:
        order_brl = float(first_buy_brl) * float(row["multiplier"])
        if cumulative + order_brl > float(cycle_cap_brl) + 1e-9:
            trimmed += 1
            continue
        fitted.append({"drop_pct": float(row["drop_pct"]), "multiplier": float(row["multiplier"])})
        cumulative += order_brl
    return fitted, trimmed, cumulative



def apply_active_ramp_limit(
    ramps: list[dict[str, float]],
    *,
    max_active_ramps: int | None,
    first_buy_brl: float,
) -> tuple[list[dict[str, float]], int, float]:
    if max_active_ramps is None or int(max_active_ramps) <= 0:
        total_brl = float(first_buy_brl)
        for row in ramps:
            total_brl += float(first_buy_brl) * float(row["multiplier"])
        return list(ramps), 0, total_brl

    limited_count = max(0, int(max_active_ramps))
    active = list(ramps[:limited_count])
    trimmed = max(0, len(ramps) - len(active))
    total_brl = float(first_buy_brl)
    for row in active:
        total_brl += float(first_buy_brl) * float(row["multiplier"])
    return active, trimmed, total_brl


def sanitize_exit_profile(
    *,
    tp_pct: float,
    trailing_activation_pct: float,
    trailing_callback_pct: float,
    stop_loss_pct: float,
    trailing_enabled: bool,
) -> dict[str, float | bool]:
    tp_pct = min(max(float(tp_pct), 0.05), 8.0)
    trailing_activation_pct = (
        min(max(float(trailing_activation_pct), 0.10), 8.0)
        if trailing_enabled
        else max(float(trailing_activation_pct), 0.0)
    )
    trailing_callback_pct = (
        min(max(float(trailing_callback_pct), 0.05), 5.0)
        if trailing_enabled
        else max(float(trailing_callback_pct), 0.0)
    )
    stop_loss_pct = min(max(float(stop_loss_pct), 0.50), 8.0)
    if trailing_enabled and trailing_activation_pct > 0:
        trailing_callback_pct = min(
            trailing_callback_pct,
            max(0.05, trailing_activation_pct * 0.65),
        )
        if trailing_callback_pct >= trailing_activation_pct:
            trailing_callback_pct = max(0.05, trailing_activation_pct * 0.50)
    return {
        "tp_pct": round(tp_pct, 4),
        "trailing_enabled": bool(trailing_enabled),
        "trailing_activation_pct": round(trailing_activation_pct, 4),
        "trailing_callback_pct": round(trailing_callback_pct, 4),
        "stop_loss_pct": round(stop_loss_pct, 4),
    }


def strategy_runtime_diagnostics(params: dict[str, Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    configured_ramps = int(params.get("configured_ramps", len(params.get("ramps", []))))
    active_ramps = len(params.get("ramps", []))
    trimmed_ramps = int(params.get("trimmed_ramps", max(0, configured_ramps - active_ramps)))
    cycle_trimmed_ramps = int(params.get("cycle_trimmed_ramps", 0))
    dashboard_trimmed_ramps = int(params.get("dashboard_trimmed_ramps", 0))
    if cycle_trimmed_ramps > 0:
        messages.append(
            {
                "level": "WARN",
                "code": "ramps_trimmed_to_cycle",
                "payload": {
                    "configured_ramps": configured_ramps,
                    "active_ramps": active_ramps,
                    "trimmed_ramps": cycle_trimmed_ramps,
                    "cycle_cap_brl": float(params.get("max_cycle_brl", 0.0)),
                },
            }
        )
    if dashboard_trimmed_ramps > 0:
        messages.append(
            {
                "level": "INFO",
                "code": "ramps_limited_by_dashboard",
                "payload": {
                    "configured_ramps": configured_ramps,
                    "active_ramps": active_ramps,
                    "trimmed_ramps": dashboard_trimmed_ramps,
                    "max_active_ramps": int(params.get("max_active_ramps", 0)),
                },
            }
        )
    elif trimmed_ramps > 0 and cycle_trimmed_ramps == 0:
        messages.append(
            {
                "level": "INFO",
                "code": "ramps_trimmed",
                "payload": {
                    "configured_ramps": configured_ramps,
                    "active_ramps": active_ramps,
                    "trimmed_ramps": trimmed_ramps,
                },
            }
        )
    return messages


def strategy_params(cfg: dict[str, Any], regime: str) -> dict[str, Any]:
    strategy_cfg = cfg["strategy"]
    base_first_buy = float(strategy_cfg.get("first_buy_brl", 300.0))
    first_buy = base_first_buy
    tp_pct = float(strategy_cfg.get("take_profit_pct", 0.8))
    stop_pct = float(strategy_cfg.get("stop_loss_pct", 3.0))
    trailing_activation_pct = float(strategy_cfg.get("trailing_activation_pct", 0.45))
    trailing_callback_pct = float(strategy_cfg.get("trailing_callback_pct", 0.22))
    if regime == "bull":
        first_buy = base_first_buy * 1.10
        tp_pct *= 1.08
        stop_pct *= 0.90
        trailing_activation_pct *= 1.05
    elif regime == "bear":
        tp_pct *= 0.95
        stop_pct *= 1.08
        trailing_activation_pct *= 0.95

    exit_profile = sanitize_exit_profile(
        tp_pct=tp_pct,
        trailing_activation_pct=trailing_activation_pct,
        trailing_callback_pct=trailing_callback_pct,
        stop_loss_pct=stop_pct,
        trailing_enabled=bool(strategy_cfg.get("trailing_enabled", True)),
    )
    requested_cycle_brl = float(
        strategy_cfg.get("max_cycle_brl", cfg["risk"].get("max_open_brl", 3000.0))
    )
    cycle_cap_brl = effective_cycle_cap(cfg, requested_cycle_brl)
    raw_ramps = normalize_ramps(cfg, regime, first_buy)
    max_active_ramps_raw = strategy_cfg.get("max_active_ramps", 0)
    try:
        max_active_ramps = int(max_active_ramps_raw or 0)
    except Exception:
        max_active_ramps = 0
    fitted_ramps, cycle_trimmed_ramps, cycle_total_brl = fit_ramps_to_cycle(
        raw_ramps,
        first_buy_brl=first_buy,
        cycle_cap_brl=cycle_cap_brl,
    )
    active_ramps, dashboard_trimmed_ramps, fitted_total_brl = apply_active_ramp_limit(
        fitted_ramps,
        max_active_ramps=max_active_ramps,
        first_buy_brl=first_buy,
    )
    trimmed_ramps = int(cycle_trimmed_ramps) + int(dashboard_trimmed_ramps)

    params: dict[str, Any] = {
        "enabled": bool(strategy_cfg.get("enabled", True)),
        "first_buy_brl": round(first_buy, 4),
        "tp": float(exit_profile["tp_pct"]) / 100.0,
        "stop": float(exit_profile["stop_loss_pct"]) / 100.0,
        "stop_loss_enabled": bool(strategy_cfg.get("stop_loss_enabled", True)),
        "stop_loss_market": bool(strategy_cfg.get("stop_loss_market", True)),
        "trailing_enabled": bool(exit_profile["trailing_enabled"]),
        "trailing_activation": float(exit_profile["trailing_activation_pct"]) / 100.0,
        "trailing_callback": float(exit_profile["trailing_callback_pct"]) / 100.0,
        "return_rebuy_pct": float(strategy_cfg.get("return_rebuy_pct", 0.40)) / 100.0,
        "max_cycle_brl": float(cycle_cap_brl),
        "requested_cycle_brl": float(requested_cycle_brl),
        "deactivate_after_sell": bool(cfg.get("runtime", {}).get("deactivate_after_sell", False)),
        "configured_ramps": len(raw_ramps),
        "trimmed_ramps": int(trimmed_ramps),
        "cycle_trimmed_ramps": int(cycle_trimmed_ramps),
        "dashboard_trimmed_ramps": int(dashboard_trimmed_ramps),
        "max_active_ramps": int(max_active_ramps),
        "cycle_fitted_total_brl": round(float(cycle_total_brl), 2),
        "fitted_cycle_total_brl": round(float(fitted_total_brl), 2),
    }
    params["ramps"] = active_ramps
    params["safety_orders"] = len(params["ramps"])
    return params


def compute_exit_targets(
    *,
    qty_usdt: float,
    brl_spent: float,
    avg_price_brl: float,
    params: dict[str, Any],
    cfg: dict[str, Any],
) -> tuple[float, float]:
    fee_rate = float(cfg["execution"].get("fee_rate", 0.001))
    base_tp = float(avg_price_brl) * (1.0 + float(params["tp"]))
    profit_floor = min_profit_exit_price(
        qty_usdt=float(qty_usdt),
        brl_spent=float(brl_spent),
        fee_rate=fee_rate,
        desired_profit_brl=min_profit_brl(cfg),
    )
    tp_price = max(base_tp, profit_floor)
    stop_price = float(avg_price_brl) * (1.0 - float(params["stop"]))
    return tp_price, stop_price


def sell_reason_uses_profit_floor(reason: str) -> bool:
    return reason in {"take_profit", "trailing_exit"}


def _resolve_sell_context(
    *,
    qty_usdt: float | None = None,
    brl_spent: float | None = None,
    position: Any | None = None,
) -> tuple[float, float]:
    if position is not None:
        if qty_usdt is None:
            qty_usdt = getattr(position, "qty_usdt", None)
        if brl_spent is None:
            brl_spent = getattr(position, "brl_spent", None)
        if isinstance(position, dict):
            if qty_usdt is None:
                qty_usdt = position.get("qty_usdt")
            if brl_spent is None:
                brl_spent = position.get("brl_spent")
    if qty_usdt is None or brl_spent is None:
        raise ValueError("qty_usdt e brl_spent são obrigatórios para validar saída.")
    return float(qty_usdt), float(brl_spent)


def can_execute_sell_reason(
    *,
    price_brl: float,
    reason: str,
    cfg: dict[str, Any],
    qty_usdt: float | None = None,
    brl_spent: float | None = None,
    position: Any | None = None,
) -> bool:
    resolved_qty_usdt, resolved_brl_spent = _resolve_sell_context(
        qty_usdt=qty_usdt,
        brl_spent=brl_spent,
        position=position,
    )
    if not sell_reason_uses_profit_floor(reason):
        return True
    pnl_brl = estimate_exit_pnl_brl(
        qty_usdt=resolved_qty_usdt,
        brl_spent=resolved_brl_spent,
        price_brl=float(price_brl),
        fee_rate=float(cfg["execution"].get("fee_rate", 0.001)),
    )
    return pnl_brl + 1e-9 >= min_profit_brl(cfg)
