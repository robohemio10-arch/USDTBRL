from smartcrypto.research.simulator import (
    block_bootstrap_ohlcv,
    build_synthetic_ohlcv_from_close,
    research_wait_bars,
    simulate_strategy,
    synthetic_limit_fill_ratio,
    timeframe_to_seconds,
)
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
            "ramps": [{"drop_pct": 0.5, "size_mult": 1.0}],
        },
        "risk": {"max_open_brl": 200.0},
    }


def test_timeframe_to_seconds_and_wait_bars() -> None:
    assert timeframe_to_seconds("1m") == 60
    assert research_wait_bars(sample_cfg()) >= 1


def test_synthetic_limit_fill_ratio_range() -> None:
    row = make_ohlcv(5).iloc[-1]
    ratio = synthetic_limit_fill_ratio("buy", float(row["close"]), row)
    assert 0.0 <= ratio <= 1.0


def test_build_and_bootstrap_ohlcv_keep_shape() -> None:
    data = make_ohlcv(120)
    synthetic = build_synthetic_ohlcv_from_close(data, data["close"])
    boot = block_bootstrap_ohlcv(data, runs_seed=7, block_size=8)
    assert len(synthetic) == len(data)
    assert len(boot) == len(data)


def test_simulate_strategy_runs_from_simulator_module() -> None:
    result = simulate_strategy(sample_cfg(), make_ohlcv(180))
    assert "final_equity_brl" in result
    assert result["bars"] == 180
