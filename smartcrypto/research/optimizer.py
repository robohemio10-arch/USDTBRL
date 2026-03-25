from __future__ import annotations

from typing import Any

import pandas as pd


def default_search_space() -> dict[str, tuple[float, float]]:
    return {
        "take_profit_pct": (0.15, 2.5),
        "first_buy_brl": (5.0, 250.0),
        "trailing_activation_pct": (0.1, 1.5),
        "trailing_callback_pct": (0.05, 0.9),
    }


from smartcrypto.research.simulator import research_candidate_configs


def optimize_on_dataset(cfg: dict[str, Any], data: pd.DataFrame) -> dict[str, Any]:
    from smartcrypto.research.backtest import simulate_strategy

    best: dict[str, Any] | None = None
    for cfg_local, params_local in research_candidate_configs(cfg):
        res = simulate_strategy(cfg_local, data)
        score = float(res["pnl_brl"]) - max(0.0, abs(float(res["max_drawdown_pct"]))) * 1.35
        if best is None or score > float(best["score"]):
            best = {
                "score": round(score, 4),
                **params_local,
                "pnl_brl": res["pnl_brl"],
                "max_drawdown_pct": res["max_drawdown_pct"],
                "win_rate_pct": res["win_rate_pct"],
                "avg_cycle_pnl_brl": res["avg_cycle_pnl_brl"],
            }
    return best or {
        "score": 0.0,
        "take_profit_pct": float(cfg.get("strategy", {}).get("take_profit_pct", 0.65)),
        "first_buy_brl": float(cfg.get("strategy", {}).get("first_buy_brl", 25.0)),
        "trailing_activation_pct": float(
            cfg.get("strategy", {}).get("trailing_activation_pct", 0.45)
        ),
        "trailing_callback_pct": float(cfg.get("strategy", {}).get("trailing_callback_pct", 0.18)),
        "pnl_brl": 0.0,
        "max_drawdown_pct": 0.0,
        "win_rate_pct": 0.0,
        "avg_cycle_pnl_brl": 0.0,
    }
def optimize(cfg: dict[str, Any], exchange: Any, store: Any | None = None) -> dict[str, Any]:
    bars = int(cfg["market"].get("research_lookback_bars", 800))
    data = exchange.fetch_ohlcv(cfg["market"]["timeframe"], bars)
    result = optimize_on_dataset(cfg, data)
    if store is not None:
        store.add_research_run(
            "optimize",
            "research.optimizer",
            {"bars": bars, "candidates": len(research_candidate_configs(cfg))},
            result,
        )
    return result
