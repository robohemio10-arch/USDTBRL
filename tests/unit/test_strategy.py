from smartcrypto.domain.strategy import (
    can_execute_sell_reason,
    compute_exit_targets,
    normalize_ramps,
    strategy_params,
)


def sample_cfg() -> dict:
    return {
        "strategy": {
            "enabled": True,
            "first_buy_brl": 300.0,
            "take_profit_pct": 0.8,
            "stop_loss_pct": 3.0,
            "trailing_activation_pct": 0.45,
            "trailing_callback_pct": 0.22,
            "trailing_enabled": True,
            "stop_loss_enabled": True,
            "stop_loss_market": True,
            "return_rebuy_pct": 0.40,
            "safety_step_pct": 0.7,
            "safety_volume_scale": 1.45,
            "safety_orders": 5,
            "min_profit_brl": 0.15,
        },
        "risk": {"max_open_brl": 3000.0},
        "portfolio": {"initial_cash_brl": 5000.0},
        "runtime": {"deactivate_after_sell": False},
        "execution": {"fee_rate": 0.001},
    }


def test_strategy_params_trim_to_cycle() -> None:
    cfg = sample_cfg()
    cfg["strategy"]["max_cycle_brl"] = 700.0

    params = strategy_params(cfg, "bull")

    assert params["first_buy_brl"] > 300.0
    assert params["safety_orders"] >= 1
    assert params["configured_ramps"] >= params["safety_orders"]


def test_compute_exit_targets_respects_profit_floor() -> None:
    params = {"tp": 0.008, "stop": 0.03}
    cfg = sample_cfg()

    tp_price, stop_price = compute_exit_targets(
        qty_usdt=100.0,
        brl_spent=500.0,
        avg_price_brl=5.0,
        params=params,
        cfg=cfg,
    )

    assert tp_price >= 5.0
    assert stop_price < 5.0


def test_profit_floor_blocks_underwater_take_profit() -> None:
    cfg = sample_cfg()

    can_sell = can_execute_sell_reason(
        qty_usdt=100.0,
        brl_spent=500.0,
        price_brl=4.99,
        reason="take_profit",
        cfg=cfg,
    )

    assert can_sell is False


def test_normalize_ramps_generates_defaults() -> None:
    ramps = normalize_ramps(sample_cfg(), "sideways", 300.0)

    assert len(ramps) == 5
    assert ramps[0]["drop_pct"] > 0
