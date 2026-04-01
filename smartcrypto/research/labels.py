from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _future_window_stats(series: pd.Series, horizon: int, reducer: str) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").ffill().bfill().to_numpy(dtype=float)
    out = np.zeros_like(values, dtype=float)
    for idx in range(len(values)):
        start = idx + 1
        stop = min(len(values), idx + 1 + horizon)
        window = values[start:stop]
        if window.size == 0:
            out[idx] = values[idx]
        elif reducer == "max":
            out[idx] = float(np.max(window))
        elif reducer == "min":
            out[idx] = float(np.min(window))
        elif reducer == "mean":
            out[idx] = float(np.mean(window))
        else:
            out[idx] = float(window[-1])
    return pd.Series(out, index=series.index, dtype=float)


def build_label_frame(
    ohlcv: pd.DataFrame,
    *,
    horizon: int = 1,
    fee_rate: float = 0.001,
    slippage_bps: float = 5.0,
    empirical_execution: dict[str, Any] | None = None,
) -> pd.DataFrame:
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    data = ohlcv.copy().reset_index(drop=True)
    if "close" not in data.columns:
        raise ValueError("OHLCV dataframe must contain a 'close' column.")
    close = pd.to_numeric(data["close"], errors="coerce").ffill().bfill()
    gross = close.shift(-horizon) / close - 1.0
    roundtrip_fee = float(fee_rate) * 2.0
    slippage_pct = float(slippage_bps) / 10_000.0
    net = gross - roundtrip_fee - slippage_pct

    high = pd.to_numeric(data.get("high", close), errors="coerce").ffill().bfill()
    low = pd.to_numeric(data.get("low", close), errors="coerce").ffill().bfill()
    open_ = pd.to_numeric(data.get("open", close), errors="coerce").ffill().bfill()
    volume = pd.to_numeric(data.get("volume", 0.0), errors="coerce").fillna(0.0)

    next_open = open_.shift(-1).fillna(close)
    future_high = _future_window_stats(high, horizon, "max")
    future_low = _future_window_stats(low, horizon, "min")
    future_avg_volume = _future_window_stats(volume, horizon, "mean")
    rolling_volume = volume.rolling(max(5, horizon), min_periods=1).mean().replace(0.0, np.nan)

    open_gap_bps = ((next_open / close) - 1.0).clip(lower=0.0) * 10_000.0
    adverse_excursion_bps = ((future_high / close) - 1.0).clip(lower=0.0) * 10_000.0
    favorable_excursion_bps = ((close / future_low) - 1.0).clip(lower=0.0) * 10_000.0
    future_range_bps = ((future_high - future_low) / close).clip(lower=0.0) * 10_000.0
    volume_ratio = (future_avg_volume / rolling_volume).replace([np.inf, -np.inf], np.nan).fillna(1.0)

    execution_cost_bps = (
        0.45 * open_gap_bps
        + 0.30 * future_range_bps
        + 0.25 * adverse_excursion_bps
        - np.clip(volume_ratio - 1.0, -0.5, 2.0) * 6.0
    ).clip(lower=0.0)

    empirical = empirical_execution or {}
    empirical_cost = float(empirical.get("median_cost_bps", 0.0) or 0.0)
    empirical_fill = float(empirical.get("fill_rate", 0.0) or 0.0)
    empirical_latency = float(empirical.get("p90_latency_seconds", 0.0) or 0.0)
    empirical_weight = float(empirical.get("weight", 0.0) or 0.0)
    if empirical_weight > 0.0:
        execution_cost_bps = execution_cost_bps * (1.0 - empirical_weight) + empirical_cost * empirical_weight + min(empirical_latency, 120.0) * 0.05

    acceptable_cost_bps = max(float(slippage_bps) * 2.0, 8.0)
    fill_raw = 0.90 - (execution_cost_bps / 180.0) + np.clip(volume_ratio - 1.0, -0.5, 1.5) * 0.10
    if empirical_weight > 0.0:
        fill_raw = fill_raw * (1.0 - empirical_weight) + empirical_fill * empirical_weight
    fill_probability = np.clip(fill_raw, 0.02, 0.995)
    realized_fill_success = (
        (execution_cost_bps <= acceptable_cost_bps) & (future_high >= close)
    ).astype(float)

    labels = pd.DataFrame(
        {
            "target_return_h": gross.fillna(0.0),
            "target_net_return_h": net.fillna(0.0),
            "target_direction_h": gross.fillna(0.0).apply(lambda value: 1 if value > 0 else 0),
            "target_positive_net_h": net.fillna(0.0).apply(lambda value: 1 if value > 0 else 0),
            "target_execution_cost_bps_h": execution_cost_bps.astype(float),
            "target_fill_probability_h": pd.Series(fill_probability, index=data.index).astype(float),
            "target_fill_success_h": realized_fill_success.astype(float),
            "target_adverse_excursion_bps_h": adverse_excursion_bps.astype(float),
            "target_favorable_excursion_bps_h": favorable_excursion_bps.astype(float),
        }
    )
    return labels


def label_config_from_cfg(cfg: dict[str, Any]) -> dict[str, float | int]:
    research_cfg = cfg.get("research", {})
    execution_cfg = cfg.get("execution", {})
    return {
        "horizon": int(research_cfg.get("label_horizon", 1) or 1),
        "fee_rate": float(execution_cfg.get("fee_rate", 0.001) or 0.001),
        "slippage_bps": float(research_cfg.get("shadow_slippage_bps", 5.0) or 5.0),
    }
