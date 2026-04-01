from __future__ import annotations

import pandas as pd

from smartcrypto.research.entry_filter import heuristic_entry_decision
from smartcrypto.research.execution_quality import heuristic_execution_decision
from smartcrypto.research.features import BASE_FEATURE_NAMES
from smartcrypto.research.position_manager import (
    PositionManagerModel,
    baseline_position_decision,
    compare_position_manager,
    heuristic_position_decision,
)


def _cfg() -> dict:
    return {
        "research": {
            "position_manager_take_profit_return": 0.004,
            "position_manager_hold_min_recovery": 0.56,
            "position_manager_reduce_max_drawdown": 0.012,
            "position_manager_risk_off_max_drawdown": 0.02,
            "position_manager_wait_min_confidence": 0.52,
        }
    }


def _row(**overrides: float) -> dict[str, float]:
    row = {name: 0.0 for name in BASE_FEATURE_NAMES}
    row.update(
        {
            "return_1": 0.004,
            "return_5": 0.008,
            "volatility_20": 0.002,
            "body_pct": 0.001,
            "close_above_sma_20": 1.0,
            "hl_range_pct": 0.003,
            "volume_zscore_20": 0.4,
        }
    )
    row.update(overrides)
    return row


def test_heuristic_position_manager_prefers_hold_on_constructive_signal() -> None:
    decision = heuristic_position_decision(_row(), _cfg())
    assert decision.action == "hold"
    assert decision.recovery_probability > 0.5


def test_heuristic_position_manager_take_profit_when_gain_is_locked_and_upside_is_small() -> None:
    decision = heuristic_position_decision(
        _row(return_1=-0.01, return_5=-0.02, volatility_20=0.001, close_above_sma_20=0.0, body_pct=-0.01),
        _cfg(),
        position_context={"unrealized_pnl_pct": 0.01},
    )
    assert decision.action == "take_profit"


def test_heuristic_position_manager_risk_off_when_drawdown_is_severe() -> None:
    decision = heuristic_position_decision(
        _row(return_1=-0.01, return_5=-0.02, volatility_20=0.03, hl_range_pct=0.04, body_pct=0.02, volume_zscore_20=-1.0),
        _cfg(),
        position_context={"distance_from_avg_price_pct": 0.03, "safety_count": 3},
    )
    assert decision.action in {"reduce", "risk_off"}
    assert decision.expected_drawdown > 0.01


def test_baseline_position_manager_uses_models() -> None:
    frame = pd.DataFrame([_row() for _ in range(8)])
    frame["target_net_return_h"] = [0.004, 0.005, 0.003, 0.006, -0.001, 0.002, 0.004, 0.005]
    frame["target_positive_net_h"] = [1, 1, 1, 1, 0, 1, 1, 1]
    model = PositionManagerModel(feature_names=list(BASE_FEATURE_NAMES)).fit(frame)
    decision = baseline_position_decision(_row(), _cfg(), model=model)
    assert decision.methodology == "baseline_position_manager"
    assert decision.action in {"hold", "wait", "take_profit", "reduce", "risk_off"}


def test_compare_position_manager_returns_winner() -> None:
    comparison = compare_position_manager(
        [
            {
                "realized_net_return": 0.003,
                "baseline_action": "hold",
                "baseline_confidence": 0.71,
                "baseline_expected_drawdown": 0.002,
                "heuristic_action": "wait",
                "heuristic_confidence": 0.55,
                "heuristic_expected_drawdown": 0.004,
            },
            {
                "realized_net_return": -0.002,
                "baseline_action": "reduce",
                "baseline_confidence": 0.66,
                "baseline_expected_drawdown": 0.003,
                "heuristic_action": "hold",
                "heuristic_confidence": 0.52,
                "heuristic_expected_drawdown": 0.006,
            },
        ]
    )
    assert comparison["rows"] == 2
    assert comparison["winner"] in {"baseline_position_manager", "heuristic_position_manager", "tie"}
