from smartcrypto.research.labels import build_label_frame
from tests.fixtures.sample_data import make_ohlcv


def test_build_label_frame_includes_net_targets() -> None:
    labels = build_label_frame(make_ohlcv(20), horizon=2, fee_rate=0.001, slippage_bps=5.0)
    assert "target_return_h" in labels.columns
    assert "target_net_return_h" in labels.columns
    assert "target_positive_net_h" in labels.columns
    assert len(labels) == 20
    assert float(labels.iloc[0]["target_return_h"]) > float(labels.iloc[0]["target_net_return_h"])
    assert "target_execution_cost_bps_h" in labels.columns
    assert "target_fill_probability_h" in labels.columns
