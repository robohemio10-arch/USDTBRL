from __future__ import annotations

from smartcrypto.research import services
from smartcrypto.runtime import bot_runtime


class DummyStore:
    def add_research_run(self, *args, **kwargs):
        return None


class DummyExchange:
    def fetch_ohlcv(self, timeframe: str, bars: int):
        import pandas as pd

        rows = 120
        return pd.DataFrame(
            {
                "open": [1.0] * rows,
                "high": [1.01] * rows,
                "low": [0.99] * rows,
                "close": [1.0] * rows,
                "volume": [100.0] * rows,
            }
        )


def base_cfg() -> dict:
    return {
        "market": {"timeframe": "1m", "research_lookback_bars": 120},
        "portfolio": {"initial_cash_brl": 100.0},
        "strategy": {
            "take_profit_pct": 0.65,
            "first_buy_brl": 25.0,
            "trailing_activation_pct": 0.45,
            "trailing_callback_pct": 0.18,
        },
        "execution": {"fee_rate": 0.001},
        "risk": {"max_open_brl": 3000.0},
    }


def test_backtest_wrapper_matches_service():
    cfg = base_cfg()
    exchange = DummyExchange()
    store = DummyStore()
    runtime_result = bot_runtime.backtest(cfg, exchange, store)
    service_result = services.run_backtest_service(cfg, exchange, store)
    assert runtime_result["bars"] == service_result["bars"]


def test_optimize_wrapper_matches_service():
    cfg = base_cfg()
    exchange = DummyExchange()
    store = DummyStore()
    runtime_result = bot_runtime.optimize(cfg, exchange, store)
    service_result = services.run_optimize_service(cfg, exchange, store)
    assert runtime_result["score"] == service_result["score"]
