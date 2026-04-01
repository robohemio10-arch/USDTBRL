from smartcrypto.research.datasets import build_training_dataset
from smartcrypto.research.execution_quality import (
    ExecutionQualityModel,
    baseline_execution_decision,
    compare_execution_quality,
    heuristic_execution_decision,
)
from smartcrypto.research.features import BASE_FEATURE_NAMES
from tests.fixtures.sample_data import make_ohlcv


def sample_cfg() -> dict:
    return {
        "execution": {"fee_rate": 0.001},
        "research": {
            "label_horizon": 1,
            "shadow_slippage_bps": 5.0,
            "execution_quality_max_cost_bps": 18.0,
            "execution_quality_min_fill_probability": 0.60,
            "execution_quality_min_score": 0.10,
        },
    }


def test_execution_quality_baseline_predicts_valid_ranges() -> None:
    frame = build_training_dataset("USDT/BRL", make_ohlcv(160), sample_cfg())
    model = ExecutionQualityModel(feature_names=list(BASE_FEATURE_NAMES)).fit(frame.iloc[:-10].copy())
    decision = baseline_execution_decision(model, frame.iloc[-1], sample_cfg())
    assert decision.expected_cost_bps >= 0.0
    assert 0.0 <= decision.fill_probability <= 1.0
    assert -1.0 <= decision.score <= 1.0


def test_heuristic_execution_quality_returns_gate_fields() -> None:
    frame = build_training_dataset("USDT/BRL", make_ohlcv(120), sample_cfg())
    decision = heuristic_execution_decision(frame.iloc[-1], sample_cfg())
    assert isinstance(decision.gate, bool)
    assert "cost_" in decision.reason


def test_compare_execution_quality_returns_winner() -> None:
    rows = [
        {
            "realized_execution_cost_bps": 8.0,
            "realized_fill_success": 1.0,
            "baseline_expected_cost_bps": 7.0,
            "baseline_fill_probability": 0.80,
            "baseline_score": 0.60,
            "baseline_gate": True,
            "heuristic_expected_cost_bps": 10.0,
            "heuristic_fill_probability": 0.70,
            "heuristic_score": 0.40,
            "heuristic_gate": True,
        }
    ]
    comparison = compare_execution_quality(rows)
    assert comparison["winner"] in {"baseline_execution_quality", "heuristic_execution_quality", "tie"}
    assert comparison["rows"] == 1
