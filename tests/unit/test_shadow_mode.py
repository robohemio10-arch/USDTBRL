from smartcrypto.research.shadow_mode import (
    predict_next_return,
    run_shadow_mode_on_dataframe,
    shadow_mode_enabled,
)
from tests.fixtures.sample_data import make_ohlcv


def sample_cfg() -> dict:
    return {"market": {"research_lookback_bars": 160, "timeframe": "1m"}}


def test_shadow_mode_enabled_accepts_nested_research_flag() -> None:
    assert shadow_mode_enabled({"research.shadow_mode_enabled": True}) is True


def test_predict_next_return_is_bounded() -> None:
    result = predict_next_return(
        {
            "return_1": 0.2,
            "return_5": 0.4,
            "volatility_20": 0.01,
            "body_pct": 0.05,
            "close_above_sma_20": 1.0,
        }
    )

    assert -0.05 <= result <= 0.05


def test_run_shadow_mode_on_dataframe_returns_metrics_when_enabled() -> None:
    result = run_shadow_mode_on_dataframe(
        sample_cfg(),
        make_ohlcv(160),
        feature_flags={"research.shadow_mode_enabled": True},
    )

    assert result["enabled"] is True
    assert result["rows"] == 160
    assert result["metrics"]["rows"] == 160.0


def test_run_shadow_mode_on_dataframe_short_circuits_when_disabled() -> None:
    result = run_shadow_mode_on_dataframe(sample_cfg(), make_ohlcv(160), feature_flags={})

    assert result["enabled"] is False
    assert result["rows"] == 0
