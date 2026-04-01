from pathlib import Path

from smartcrypto.research.ml_store import MLStore
from smartcrypto.research.reporting import generate_rollout_report


def test_generate_rollout_report_summarizes_store(tmp_path: Path) -> None:
    store = MLStore(str(tmp_path / "ml_store.sqlite"))
    store.add_shadow_prediction(
        "USDT/BRL",
        "1m",
        "linear_baseline_walkforward_shadow",
        {
            "metrics": {"mae": 0.1},
            "validation": {
                "entry_filter_segment_comparison": {"by_regime": [{"regime_bucket": "sideways", "rows": 3}]},
                "execution_quality_segment_comparison": {"by_hour": [{"hour_bucket": "10", "rows": 3}]},
            },
            "entry_filter": {"baseline": {"calibration_metrics": {"brier_score": 0.11}}},
        },
    )
    store.add_rollout_event("USDT/BRL", "1m", "paper_decision", {"metrics": {"readiness": {"overall_ready": True}}})
    store.register_model("entry_filter_baseline", "v3", metrics={"mae": 0.1}, params={}, artifact={})
    report = generate_rollout_report(store)
    assert report["shadow_runs"] == 1
    assert report["rollout_events"] == 1
    assert report["registered_models"] == 1
    assert report["methodologies"]["linear_baseline_walkforward_shadow"] == 1
    assert report["rollout_stages"]["paper_decision"] == 1
    assert report["entry_filter_segments"]["by_regime"][0]["regime_bucket"] == "sideways"
    assert report["calibration"]["entry_filter"]["brier_score"] == 0.11
