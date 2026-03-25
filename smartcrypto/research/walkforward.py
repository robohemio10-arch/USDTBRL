from __future__ import annotations

import json
from typing import Any

import pandas as pd

from smartcrypto.research.simulator import simulate_strategy
from smartcrypto.research.datasets import anchored_walkforward_splits
from smartcrypto.research.optimizer import optimize_on_dataset


def run_walkforward_on_dataframe(cfg: dict[str, Any], ohlcv: pd.DataFrame) -> dict[str, Any]:
    folds = max(2, int(cfg.get("research", {}).get("walk_forward_folds", 3) or 3))
    train_ratio = float(cfg.get("research", {}).get("walk_forward_train_ratio", 0.65) or 0.65)
    split_rows = anchored_walkforward_splits(
        ohlcv.reset_index(drop=True),
        folds=folds,
        train_ratio=train_ratio,
        min_train_rows=80,
        min_test_rows=20,
    )
    rows: list[dict[str, Any]] = []
    for split in split_rows:
        train = split["train"]
        test = split["test"]
        best = optimize_on_dataset(cfg, train)
        cfg_local = json.loads(json.dumps(cfg))
        cfg_local.setdefault("strategy", {})
        cfg_local["strategy"]["take_profit_pct"] = float(best["take_profit_pct"])
        cfg_local["strategy"]["first_buy_brl"] = float(best["first_buy_brl"])
        cfg_local["strategy"]["trailing_activation_pct"] = float(best["trailing_activation_pct"])
        cfg_local["strategy"]["trailing_callback_pct"] = float(best["trailing_callback_pct"])
        test_result = simulate_strategy(cfg_local, test)
        rows.append(
            {
                "fold": int(split["fold"]),
                "train_bars": int(len(train)),
                "test_bars": int(len(test)),
                "take_profit_pct": float(best["take_profit_pct"]),
                "first_buy_brl": float(best["first_buy_brl"]),
                "trailing_activation_pct": float(best["trailing_activation_pct"]),
                "trailing_callback_pct": float(best["trailing_callback_pct"]),
                "test_pnl_brl": float(test_result["pnl_brl"]),
                "test_max_drawdown_pct": float(test_result["max_drawdown_pct"]),
                "test_win_rate_pct": float(test_result["win_rate_pct"]),
            }
        )
    frame = pd.DataFrame(rows)
    return {
        "folds": int(len(rows)),
        "avg_test_pnl_brl": round(float(frame["test_pnl_brl"].mean()), 2) if not frame.empty else 0.0,
        "median_test_pnl_brl": round(float(frame["test_pnl_brl"].median()), 2) if not frame.empty else 0.0,
        "avg_test_max_drawdown_pct": round(float(frame["test_max_drawdown_pct"].mean()), 2) if not frame.empty else 0.0,
        "avg_test_win_rate_pct": round(float(frame["test_win_rate_pct"].mean()), 2) if not frame.empty else 0.0,
        "fold_details": rows,
        "methodology": "anchored_walk_forward_live_like",
    }


def run_walkforward(cfg: dict[str, Any], exchange: Any, store: Any | None = None) -> dict[str, Any]:
    bars = int(cfg["market"].get("research_lookback_bars", 800))
    data = exchange.fetch_ohlcv(cfg["market"]["timeframe"], bars)
    result = run_walkforward_on_dataframe(cfg, data)
    if store is not None:
        store.add_research_run(
            "walk_forward",
            "research.walkforward",
            {
                "bars": bars,
                "folds": int(cfg.get("research", {}).get("walk_forward_folds", 3) or 3),
                "train_ratio": float(cfg.get("research", {}).get("walk_forward_train_ratio", 0.65) or 0.65),
            },
            result,
        )
    return result
