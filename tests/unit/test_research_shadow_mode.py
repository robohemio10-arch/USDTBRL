import pandas as pd
from pathlib import Path

from smartcrypto.research.ml_store import MLStore
from smartcrypto.research.shadow_mode import run_shadow_mode_on_dataframe
from tests.fixtures.sample_data import make_ohlcv


def sample_cfg(tmp_path: Path) -> dict:
    return {
        "market": {"symbol": "USDT/BRL", "timeframe": "1m", "research_lookback_bars": 180},
        "execution": {"fee_rate": 0.001},
        "research": {"label_horizon": 1, "shadow_slippage_bps": 5.0, "walk_forward_purge_gap": 1},
        "storage": {"ml_store_path": str(tmp_path / "ml_store.sqlite")},
    }


def test_shadow_mode_uses_baseline_methodology_when_enough_rows(tmp_path: Path) -> None:
    result = run_shadow_mode_on_dataframe(sample_cfg(tmp_path), make_ohlcv(180), feature_flags={"research.shadow_mode_enabled": True})
    assert result["enabled"] is True
    assert result["rows"] > 0
    assert result["methodology"] in {"linear_baseline_walkforward_shadow", "feature_heuristic_shadow_mode"}
    assert "entry_filter" in result
    assert "execution_quality" in result
    assert "execution_adjusted_gate" in result["entry_filter"]


def test_ml_store_initializes_tables(tmp_path: Path) -> None:
    store = MLStore(str(tmp_path / "ml_store.sqlite"))
    assert store.read_df("feature_snapshots").empty
    assert store.read_df("shadow_predictions").empty
    assert store.read_df("model_registry").empty



def test_shadow_mode_exposes_position_manager_block() -> None:
    from smartcrypto.research.shadow_mode import run_shadow_mode_on_dataframe
    import pandas as pd

    cfg = {
        "market": {"symbol": "USDT/BRL", "research_lookback_bars": 120},
        "execution": {"fee_rate": 0.001},
        "research": {"shadow_slippage_bps": 5.0, "shadow_folds": 2, "walk_forward_purge_gap": 1},
    }
    close = [5.0 + i * 0.01 for i in range(140)]
    frame = pd.DataFrame({
        "open": close,
        "high": [x * 1.002 for x in close],
        "low": [x * 0.998 for x in close],
        "close": close,
        "volume": [1000 + i for i in range(140)],
    })
    result = run_shadow_mode_on_dataframe(cfg, frame, feature_flags={"shadow_mode_enabled": True})
    assert "position_manager" in result
    assert "selected" in result["position_manager"]


def test_shadow_mode_exposes_segment_comparison(tmp_path: Path) -> None:
    frame = make_ohlcv(180)
    frame["ts"] = pd.date_range("2026-01-01", periods=len(frame), freq="h", tz="UTC")
    result = run_shadow_mode_on_dataframe(sample_cfg(tmp_path), frame, feature_flags={"research.shadow_mode_enabled": True})
    assert "entry_filter_segment_comparison" in result["validation"]
    assert "by_regime" in result["validation"]["entry_filter_segment_comparison"]


def test_shadow_mode_exposes_execution_and_position_segments(tmp_path: Path) -> None:
    frame = make_ohlcv(180)
    frame["ts"] = pd.date_range("2026-01-01", periods=len(frame), freq="h", tz="UTC")
    result = run_shadow_mode_on_dataframe(sample_cfg(tmp_path), frame, feature_flags={"research.shadow_mode_enabled": True})
    assert "execution_quality_segment_comparison" in result["validation"]
    assert "position_manager_segment_comparison" in result["validation"]
