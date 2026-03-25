from decimal import Decimal

import pytest

from tests.fakes.fake_binance import FakeBinanceAdapter


@pytest.fixture
def fake_binance() -> FakeBinanceAdapter:
    return FakeBinanceAdapter(symbol="USDTBRL", mark_price=Decimal("5.0"))
