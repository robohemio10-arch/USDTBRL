from __future__ import annotations

from typing import Any

from smartcrypto.research.simulator import simulate_strategy


def run_backtest_on_dataframe(cfg: dict[str, Any], ohlcv) -> dict[str, Any]:
    result = simulate_strategy(cfg, ohlcv)
    return {
        **result,
        "bars": int(len(ohlcv)),
        "methodology": str(result.get("methodology", "v9_2_research_live_like_v2")),
    }


def run_backtest(cfg: dict[str, Any], exchange: Any, store: Any | None = None) -> dict[str, Any]:
    bars = int(cfg["market"].get("research_lookback_bars", 800))
    data = exchange.fetch_ohlcv(cfg["market"]["timeframe"], bars)
    result = run_backtest_on_dataframe(cfg, data)
    if store is not None and hasattr(store, "add_research_run"):
        store.add_research_run(
            run_type="backtest",
            symbol=str(cfg.get("market", {}).get("symbol", "USDT/BRL")),
            params={"timeframe": cfg["market"]["timeframe"], "bars": bars},
            metrics=result,
        )
    return result
