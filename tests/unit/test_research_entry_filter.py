from __future__ import annotations

import pandas as pd

from smartcrypto.research.baseline_model import LinearBaselineModel
from smartcrypto.research.entry_filter import baseline_entry_decision, compare_entry_filters, heuristic_entry_decision
from smartcrypto.research.features import BASE_FEATURE_NAMES


def test_heuristic_entry_filter_returns_explicit_decision() -> None:
    decision = heuristic_entry_decision(
        {
            "return_1": 0.01,
            "return_5": 0.03,
            "volatility_20": 0.002,
            "body_pct": 0.008,
            "close_above_sma_20": 1.0,
        },
        {"research": {"entry_filter_prob_threshold": 0.5}},
    )
    assert decision.methodology == "heuristic_entry_filter"
    assert isinstance(decision.gate, bool)
    assert "prob_" in decision.reason


def test_baseline_entry_filter_uses_trained_model() -> None:
    frame = pd.DataFrame(
        [
            {**{name: 0.01 for name in BASE_FEATURE_NAMES}, "target_net_return_h": 0.005},
            {**{name: 0.02 for name in BASE_FEATURE_NAMES}, "target_net_return_h": 0.01},
            {**{name: -0.01 for name in BASE_FEATURE_NAMES}, "target_net_return_h": -0.004},
            {**{name: 0.03 for name in BASE_FEATURE_NAMES}, "target_net_return_h": 0.012},
            {**{name: -0.02 for name in BASE_FEATURE_NAMES}, "target_net_return_h": -0.008},
            {**{name: 0.015 for name in BASE_FEATURE_NAMES}, "target_net_return_h": 0.006},
        ]
    )
    model = LinearBaselineModel(feature_names=list(BASE_FEATURE_NAMES)).fit(frame)
    decision = baseline_entry_decision(model, frame.iloc[-1], {"research": {"entry_filter_prob_threshold": 0.5}})
    assert decision.methodology == "baseline_entry_filter"
    assert 0.0 <= decision.predicted_positive_net_prob <= 1.0


def test_compare_entry_filters_reports_winner() -> None:
    comparison = compare_entry_filters(
        [
            {
                "realized_net_return": 0.01,
                "target_positive_net": 1.0,
                "baseline_predicted_net_return": 0.008,
                "baseline_predicted_positive_net_prob": 0.62,
                "baseline_gate": True,
                "heuristic_predicted_net_return": 0.004,
                "heuristic_predicted_positive_net_prob": 0.54,
                "heuristic_gate": True,
            },
            {
                "realized_net_return": -0.006,
                "target_positive_net": 0.0,
                "baseline_predicted_net_return": -0.002,
                "baseline_predicted_positive_net_prob": 0.45,
                "baseline_gate": False,
                "heuristic_predicted_net_return": 0.002,
                "heuristic_predicted_positive_net_prob": 0.53,
                "heuristic_gate": True,
            },
        ]
    )
    assert comparison["rows"] == 2
    assert comparison["winner"] == "baseline_entry_filter"
