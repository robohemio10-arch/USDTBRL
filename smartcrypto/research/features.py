from __future__ import annotations

from typing import Iterable

import pandas as pd


BASE_FEATURE_NAMES = [
    "return_1",
    "return_5",
    "volatility_20",
    "hl_range_pct",
    "body_pct",
    "volume_zscore_20",
    "close_above_sma_20",
]


def build_feature_names(include_target: bool = False) -> list[str]:
    names = list(BASE_FEATURE_NAMES)
    if include_target:
        names.append("target_return_1")
    return names


def ensure_ohlcv_columns(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    if "close" not in data.columns:
        if "Close" in data.columns:
            data["close"] = data["Close"]
        else:
            raise ValueError("OHLCV dataframe must contain a 'close' column.")
    for missing in ("open", "high", "low", "volume"):
        if missing not in data.columns:
            data[missing] = data["close"]
    return data


def build_feature_frame(
    ohlcv: pd.DataFrame,
    *,
    include_target: bool = True,
    target_horizon: int = 1,
) -> pd.DataFrame:
    data = ensure_ohlcv_columns(ohlcv).copy().reset_index(drop=True)
    data["return_1"] = data["close"].pct_change(1).fillna(0.0)
    data["return_5"] = data["close"].pct_change(5).fillna(0.0)
    data["volatility_20"] = data["return_1"].rolling(20, min_periods=3).std().fillna(0.0)
    data["hl_range_pct"] = ((data["high"] - data["low"]) / data["close"].replace(0, pd.NA)).fillna(0.0)
    data["body_pct"] = ((data["close"] - data["open"]) / data["open"].replace(0, pd.NA)).fillna(0.0)
    volume_mean = data["volume"].rolling(20, min_periods=3).mean()
    volume_std = data["volume"].rolling(20, min_periods=3).std().replace(0, pd.NA)
    data["volume_zscore_20"] = ((data["volume"] - volume_mean) / volume_std).fillna(0.0)
    sma_20 = data["close"].rolling(20, min_periods=3).mean()
    data["close_above_sma_20"] = (data["close"] >= sma_20).astype(float).fillna(0.0)
    if include_target:
        data["target_return_1"] = data["close"].shift(-target_horizon) / data["close"] - 1.0
        data["target_return_1"] = data["target_return_1"].fillna(0.0)
    feature_columns = build_feature_names(include_target=include_target)
    return data[feature_columns].copy()


def latest_feature_row(ohlcv: pd.DataFrame) -> dict[str, float]:
    features = build_feature_frame(ohlcv, include_target=False)
    if features.empty:
        return {name: 0.0 for name in build_feature_names(include_target=False)}
    row = features.iloc[-1]
    return {key: float(row[key]) for key in features.columns}


def feature_snapshot(ohlcv: pd.DataFrame, feature_names: Iterable[str] | None = None) -> dict[str, float]:
    available = latest_feature_row(ohlcv)
    if feature_names is None:
        return available
    return {str(name): float(available.get(str(name), 0.0)) for name in feature_names}
