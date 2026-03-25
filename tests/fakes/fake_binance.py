from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

import pandas as pd

from tests.fixtures.sample_data import make_ohlcv


@dataclass
class FakeBinanceAdapter:
    symbol: str
    mark_price: Decimal
    bars: int = 240
    start_price: float = 5.0
    step: float = 0.003
    dataset: pd.DataFrame | None = field(default=None)

    def get_symbol_ticker(self, symbol: str) -> dict[str, str]:
        if symbol != self.symbol:
            raise ValueError(f"Unsupported symbol: {symbol}")
        return {"symbol": symbol, "price": str(self.mark_price)}

    def fetch_ohlcv(self, timeframe: str, limit: int) -> pd.DataFrame:
        data = self.dataset.copy() if self.dataset is not None else make_ohlcv(self.bars, self.start_price, self.step)
        return data.tail(limit).reset_index(drop=True)
