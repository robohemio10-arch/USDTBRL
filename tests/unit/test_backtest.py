from smartcrypto.research.backtest import run_backtest, run_backtest_on_dataframe
from tests.fakes.fake_binance import FakeBinanceAdapter
from tests.fixtures.sample_data import make_ohlcv


def sample_cfg() -> dict:
    return {
        "market": {"symbol": "USDT/BRL", "timeframe": "1m", "research_lookback_bars": 180},
        "portfolio": {"initial_cash_brl": 500.0},
        "execution": {
            "fee_rate": 0.001,
            "reprice_attempts": 2,
            "reprice_wait_seconds": 10,
            "limit_orders_enabled": True,
            "entry_fallback_market": True,
        },
        "strategy": {
            "first_buy_brl": 50.0,
            "take_profit_pct": 0.6,
            "trailing_enabled": True,
            "trailing_activation_pct": 0.45,
            "trailing_callback_pct": 0.18,
            "return_rebuy_pct": 0.12,
            "stop_loss_enabled": True,
            "stop_loss_pct": 8.0,
            "min_profit_brl": 0.15,
            "max_cycle_brl": 500.0,
            "ramps": [{"drop_pct": 0.35, "multiplier": 1.0}],
        },
        "risk": {"max_open_brl": 500.0},
    }


def test_run_backtest_on_dataframe_returns_live_like_payload() -> None:
    result = run_backtest_on_dataframe(sample_cfg(), make_ohlcv(180))

    assert result["bars"] == 180
    assert "pnl_brl" in result
    assert "methodology" in result


def test_run_backtest_uses_exchange_adapter() -> None:
    exchange = FakeBinanceAdapter(symbol="USDTBRL", mark_price="5.2")  # type: ignore[arg-type]

    result = run_backtest(sample_cfg(), exchange)

    assert result["bars"] == 180
