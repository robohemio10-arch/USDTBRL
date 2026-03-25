from smartcrypto.research.walkforward import run_walkforward_on_dataframe
from tests.fixtures.sample_data import make_ohlcv


def sample_cfg() -> dict:
    return {
        "market": {"research_lookback_bars": 240},
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
        "research": {"walk_forward_folds": 3, "walk_forward_train_ratio": 0.65},
    }


def test_run_walkforward_on_dataframe_returns_fold_summary(monkeypatch) -> None:
    monkeypatch.setattr(
        "smartcrypto.research.walkforward.optimize_on_dataset",
        lambda cfg, data: {
            "take_profit_pct": 0.6,
            "first_buy_brl": 50.0,
            "trailing_activation_pct": 0.45,
            "trailing_callback_pct": 0.18,
        },
    )

    result = run_walkforward_on_dataframe(sample_cfg(), make_ohlcv(240))

    assert result["folds"] >= 1
    assert "fold_details" in result
