from __future__ import annotations

from typing import Any

import pandas as pd

from smartcrypto.research.evaluation import evaluate_shadow_predictions
from smartcrypto.research.features import build_feature_frame


def shadow_mode_enabled(feature_flags: dict[str, bool]) -> bool:
    return bool(
        feature_flags.get("research.shadow_mode_enabled")
        or feature_flags.get("shadow_mode")
        or feature_flags.get("shadow_mode_enabled")
    )


def predict_next_return(feature_row: pd.Series) -> float:
    signal = (
        0.45 * float(feature_row.get("return_1", 0.0))
        + 0.35 * float(feature_row.get("return_5", 0.0))
        - 0.20 * float(feature_row.get("volatility_20", 0.0))
        + 0.05 * float(feature_row.get("body_pct", 0.0))
        + 0.02 * float(feature_row.get("close_above_sma_20", 0.0))
    )
    return max(-0.05, min(0.05, round(signal, 6)))


def run_shadow_mode_on_dataframe(
    cfg: dict[str, Any],
    ohlcv: pd.DataFrame,
    *,
    feature_flags: dict[str, bool] | None = None,
) -> dict[str, Any]:
    flags = feature_flags or {}
    enabled = shadow_mode_enabled(flags)
    if not enabled:
        return {"enabled": False, "rows": 0, "predictions": [], "metrics": evaluate_shadow_predictions([])}
    features = build_feature_frame(ohlcv, include_target=True).reset_index(drop=True)
    rows: list[dict[str, float]] = []
    for _, row in features.iterrows():
        predicted = predict_next_return(row)
        realized = float(row.get("target_return_1", 0.0))
        rows.append(
            {
                "predicted_return": float(predicted),
                "realized_return": float(realized),
                "score": float(realized - predicted),
            }
        )
    metrics = evaluate_shadow_predictions(rows)
    return {
        "enabled": True,
        "rows": int(len(rows)),
        "lookback_bars": int(cfg.get("market", {}).get("research_lookback_bars", len(ohlcv)) or len(ohlcv)),
        "predictions": rows[-25:],
        "metrics": metrics,
        "methodology": "feature_heuristic_shadow_mode",
    }


def run_shadow_mode(
    cfg: dict[str, Any],
    exchange: Any,
    store: Any | None = None,
    *,
    feature_flags: dict[str, bool] | None = None,
) -> dict[str, Any]:
    bars = int(cfg["market"].get("research_lookback_bars", 800))
    data = exchange.fetch_ohlcv(cfg["market"]["timeframe"], bars)
    result = run_shadow_mode_on_dataframe(cfg, data, feature_flags=feature_flags)
    if store is not None and result.get("enabled"):
        store.add_research_run(
            "shadow_mode",
            "research.shadow_mode",
            {"bars": bars, "timeframe": cfg["market"]["timeframe"]},
            result,
        )
    return result
