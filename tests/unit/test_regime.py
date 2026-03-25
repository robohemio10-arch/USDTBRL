import pandas as pd

from smartcrypto.domain.regime import compute_regime


def test_compute_regime_detects_bullish_bias() -> None:
    closes = list(range(100, 160))
    frame = pd.DataFrame({"close": closes})

    regime, score, features = compute_regime(frame)

    assert regime == "bull"
    assert score > 0
    assert "trend" in features
