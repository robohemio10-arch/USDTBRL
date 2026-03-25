from smartcrypto.research.features import build_feature_frame, build_feature_names, latest_feature_row
from tests.fixtures.sample_data import make_ohlcv


def test_build_feature_frame_contains_expected_columns() -> None:
    frame = build_feature_frame(make_ohlcv(120))

    assert build_feature_names(include_target=True) == list(frame.columns)
    assert len(frame) == 120


def test_latest_feature_row_returns_scalar_snapshot() -> None:
    snapshot = latest_feature_row(make_ohlcv(100))

    assert "return_1" in snapshot
    assert "volatility_20" in snapshot
    assert isinstance(snapshot["return_1"], float)
