from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pandas as pd


SAMPLE_PRICES = {
    "USDTBRL": [Decimal("4.95"), Decimal("5.00"), Decimal("5.05")],
}


def make_ohlcv(rows: int = 180, start_price: float = 5.0, step: float = 0.003) -> pd.DataFrame:
    price = start_price
    records: list[dict[str, float]] = []
    for index in range(rows):
        open_price = price
        close_price = price + step
        high_price = max(open_price, close_price) + 0.01
        low_price = min(open_price, close_price) - 0.01
        volume = 1000.0 + (index % 10) * 25.0
        records.append(
            {
                "open": round(open_price, 6),
                "high": round(high_price, 6),
                "low": round(low_price, 6),
                "close": round(close_price, 6),
                "volume": round(volume, 2),
            }
        )
        price = close_price
    return pd.DataFrame(records)
