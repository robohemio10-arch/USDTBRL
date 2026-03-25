from __future__ import annotations

from typing import Any

import pandas as pd

from smartcrypto.research.simulator import block_bootstrap_ohlcv, simulate_strategy


def run_monte_carlo_on_dataframe(
    cfg: dict[str, Any],
    ohlcv: pd.DataFrame,
    *,
    runs: int,
    block_size: int,
) -> dict[str, Any]:
    if len(ohlcv) < 80:
        return {"runs": int(runs), "p5": 0.0, "median": 0.0, "p95": 0.0, "loss_probability_pct": 0.0}
    outcomes: list[float] = []
    drawdowns: list[float] = []
    for run_index in range(runs):
        synthetic = block_bootstrap_ohlcv(ohlcv, runs_seed=run_index + 7, block_size=block_size)
        simulated = simulate_strategy(cfg, synthetic)
        outcomes.append(float(simulated["pnl_brl"]))
        drawdowns.append(float(simulated["max_drawdown_pct"]))
    ser = pd.Series(outcomes, dtype=float)
    dd = pd.Series(drawdowns, dtype=float)
    return {
        "runs": int(runs),
        "p5": round(float(ser.quantile(0.05)), 2),
        "median": round(float(ser.median()), 2),
        "p95": round(float(ser.quantile(0.95)), 2),
        "loss_probability_pct": round(float((ser < 0).mean() * 100.0), 2),
        "median_drawdown_pct": round(float(dd.median()), 2),
        "methodology": "block_bootstrap_live_like_simulation",
    }


def run_monte_carlo(cfg: dict[str, Any], exchange: Any, store: Any | None = None) -> dict[str, Any]:
    bars = int(cfg["market"].get("research_lookback_bars", 800))
    runs = int(cfg.get("research", {}).get("monte_carlo_runs", 300))
    block_size = int(cfg.get("research", {}).get("block_bootstrap_block_size", 24) or 24)
    data = exchange.fetch_ohlcv(cfg["market"]["timeframe"], bars)
    result = run_monte_carlo_on_dataframe(cfg, data, runs=runs, block_size=block_size)
    if store is not None:
        store.add_research_run(
            "monte_carlo",
            "research.montecarlo",
            {"bars": bars, "runs": runs, "block_size": block_size},
            result,
        )
    return result
