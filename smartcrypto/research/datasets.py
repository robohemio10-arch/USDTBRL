from __future__ import annotations

from typing import Any

import pandas as pd

from smartcrypto.research.features import build_feature_frame
from smartcrypto.research.labels import build_label_frame, label_config_from_cfg
from smartcrypto.research.execution_truth import load_empirical_execution_summary


def dataset_name(symbol: str) -> str:
    normalized = "".join(ch.lower() for ch in symbol if ch.isalnum())
    return f"{normalized}_dataset"


def _regime_bucket(frame: pd.DataFrame) -> pd.Series:
    momentum = pd.to_numeric(frame.get("return_5", 0.0), errors="coerce").fillna(0.0)
    volatility = pd.to_numeric(frame.get("volatility_20", 0.0), errors="coerce").fillna(0.0)
    labels: list[str] = []
    for mom, vol in zip(momentum, volatility, strict=False):
        if vol > 0.01:
            labels.append("volatile")
        elif mom > 0.003:
            labels.append("trend_up")
        elif mom < -0.003:
            labels.append("trend_down")
        else:
            labels.append("sideways")
    return pd.Series(labels, index=frame.index, dtype="object")


def build_training_dataset(symbol: str, ohlcv: pd.DataFrame, cfg: dict[str, Any] | None = None) -> pd.DataFrame:
    frame = build_feature_frame(ohlcv, include_target=False)
    if cfg is None:
        label_cfg = {"horizon": 1, "fee_rate": 0.001, "slippage_bps": 5.0}
    else:
        label_cfg = label_config_from_cfg(cfg)
    empirical = load_empirical_execution_summary(cfg or {}) if cfg is not None else {"available": False}
    empirical_execution = None
    if empirical.get("available"):
        empirical_execution = {
            "median_cost_bps": float(empirical.get("median_cost_bps", 0.0) or 0.0),
            "fill_rate": float(empirical.get("fill_rate", 0.0) or 0.0),
            "p90_latency_seconds": float(empirical.get("p90_latency_seconds", 0.0) or 0.0),
            "weight": min(0.65, max(0.15, int(empirical.get("rows", 0) or 0) / 200.0)),
        }
    labels = build_label_frame(
        ohlcv,
        horizon=int(label_cfg["horizon"]),
        fee_rate=float(label_cfg["fee_rate"]),
        slippage_bps=float(label_cfg["slippage_bps"]),
        empirical_execution=empirical_execution,
    )
    enriched = pd.concat([frame.reset_index(drop=True), labels.reset_index(drop=True)], axis=1)
    enriched.insert(0, "dataset", dataset_name(symbol))
    enriched.insert(1, "symbol", str(symbol))
    enriched["regime_bucket"] = _regime_bucket(enriched)
    if "ts" in ohlcv.columns:
        ts = pd.to_datetime(ohlcv["ts"], errors="coerce", utc=True)
        enriched["ts"] = ts.reset_index(drop=True)
        enriched["hour_bucket"] = ts.dt.hour.fillna(-1).astype(int).reset_index(drop=True)
    else:
        enriched["hour_bucket"] = -1
    enriched["timeframe"] = str((cfg or {}).get("market", {}).get("timeframe", "unknown"))
    if cfg is not None and empirical.get("available"):
        enriched.attrs["empirical_execution"] = empirical
    return enriched


def anchored_walkforward_splits(
    frame: pd.DataFrame,
    *,
    folds: int = 3,
    train_ratio: float = 0.65,
    min_train_rows: int = 80,
    min_test_rows: int = 20,
    purge_gap: int = 0,
) -> list[dict[str, Any]]:
    data = frame.reset_index(drop=True)
    if data.empty:
        return []
    min_train = max(min_train_rows, int(len(data) * train_ratio))
    remaining = max(0, len(data) - min_train)
    test_size = max(min_test_rows, remaining // max(1, folds))
    splits: list[dict[str, Any]] = []
    for fold in range(max(1, folds)):
        train_end = min(len(data) - min_test_rows, min_train + fold * test_size)
        test_end = min(len(data), train_end + test_size)
        if train_end < min_train_rows or test_end - train_end < min_test_rows:
            continue
        test_start = min(len(data), train_end + max(0, int(purge_gap)))
        if test_end - test_start < min_test_rows:
            continue
        splits.append(
            {
                "fold": fold + 1,
                "train": data.iloc[:train_end].copy().reset_index(drop=True),
                "test": data.iloc[test_start:test_end].copy().reset_index(drop=True),
                "purge_gap": int(max(0, int(purge_gap))),
            }
        )
    return splits
