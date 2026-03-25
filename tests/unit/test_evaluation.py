from smartcrypto.research.evaluation import (
    directional_accuracy,
    evaluate_shadow_predictions,
    mean_absolute_error,
    score_shadow_run,
)


def test_score_shadow_run_returns_residual() -> None:
    assert score_shadow_run(0.01, 0.03) == 0.02


def test_mean_absolute_error() -> None:
    assert round(mean_absolute_error([1.0, 2.0], [1.5, 1.5]), 4) == 0.5


def test_directional_accuracy() -> None:
    assert directional_accuracy([0.1, -0.2, 0.0], [0.2, -0.1, 0.0]) == 1.0


def test_evaluate_shadow_predictions() -> None:
    metrics = evaluate_shadow_predictions(
        [
            {"predicted_return": 0.01, "realized_return": 0.02},
            {"predicted_return": -0.02, "realized_return": -0.01},
        ]
    )

    assert metrics["rows"] == 2.0
    assert metrics["directional_accuracy_pct"] == 100.0
