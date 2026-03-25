from __future__ import annotations

from typing import Any

import pandas as pd

from smartcrypto.research.features import build_feature_frame


def dataset_name(symbol: str) -> str:
    normalized = "".join(ch.lower() for ch in symbol if ch.isalnum())
    return f"{normalized}_dataset"


def build_training_dataset(symbol: str, ohlcv: pd.DataFrame) -> pd.DataFrame:
    frame = build_feature_frame(ohlcv, include_target=True)
    enriched = frame.copy()
    enriched.insert(0, "dataset", dataset_name(symbol))
    return enriched


def anchored_walkforward_splits(
    frame: pd.DataFrame,
    *,
    folds: int = 3,
    train_ratio: float = 0.65,
    min_train_rows: int = 80,
    min_test_rows: int = 20,
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
        splits.append(
            {
                "fold": fold + 1,
                "train": data.iloc[:train_end].copy().reset_index(drop=True),
                "test": data.iloc[train_end:test_end].copy().reset_index(drop=True),
            }
        )
    return splits
