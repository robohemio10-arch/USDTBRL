from __future__ import annotations

from typing import Any

import pandas as pd

from smartcrypto.domain.enums import RegimeType
from smartcrypto.domain.models import RegimeSnapshot


def classify_regime(volatility_ratio: float) -> RegimeType:
    if volatility_ratio < 0:
        return RegimeType.UNKNOWN
    if volatility_ratio >= 2:
        return RegimeType.BEAR
    if volatility_ratio >= 1:
        return RegimeType.BULL
    return RegimeType.SIDEWAYS


def compute_regime(ohlcv: pd.DataFrame) -> tuple[str, float, dict[str, float]]:
    close = ohlcv["close"].astype(float)
    ret_1 = close.pct_change().fillna(0.0)
    ma_fast = close.rolling(12).mean().iloc[-1]
    ma_slow = close.rolling(48).mean().iloc[-1]
    trend = float((ma_fast / ma_slow) - 1.0) if ma_slow else 0.0
    vol = float(ret_1.rolling(20).std().fillna(0.0).iloc[-1])
    ret_5 = float(close.pct_change(5).fillna(0.0).iloc[-1])
    features = {"trend": trend, "vol": vol, "ret_5": ret_5}
    if trend > 0.003 and ret_5 > 0:
        return RegimeType.BULL.value, abs(trend), features
    if trend < -0.003 and ret_5 < 0:
        return RegimeType.BEAR.value, abs(trend), features
    return RegimeType.SIDEWAYS.value, abs(ret_5), features


def regime_snapshot(ohlcv: pd.DataFrame) -> RegimeSnapshot:
    regime, score, features = compute_regime(ohlcv)
    return RegimeSnapshot(regime=RegimeType(regime), score=score, features=features)
