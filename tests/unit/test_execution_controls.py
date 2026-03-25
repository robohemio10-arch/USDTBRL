from pathlib import Path

from smartcrypto.execution.controls import (
    build_safety_ladder,
    choose_exit_order_type,
    offset_price,
    order_type_for,
    post_sell_controls,
    reentry_price_threshold,
    reentry_remaining_seconds,
    replace_dashboard_orders,
    set_reentry_price_block,
)
from smartcrypto.state.store import StateStore


def _cfg() -> dict[str, object]:
    return {
        "execution": {
            "limit_orders_enabled": True,
            "entry_order_type": "limit",
            "exit_order_type": "limit",
            "buy_price_offset_bps": 10,
            "sell_price_offset_bps": 20,
            "force_sell_market": True,
        },
        "runtime": {
            "cooldown_after_force_sell_seconds": 30,
            "cooldown_after_stop_loss_seconds": 90,
            "cooldown_after_profit_sell_seconds": 15,
        },
    }


def test_order_type_and_offsets() -> None:
    cfg = _cfg()
    assert order_type_for("buy", cfg) == "limit"
    assert order_type_for("sell", cfg) == "limit"
    assert round(offset_price(5.0, "buy", cfg), 4) == 4.995
    assert round(offset_price(5.0, "sell", cfg), 4) == 5.01


def test_choose_exit_order_type() -> None:
    cfg = _cfg()
    assert choose_exit_order_type("force_sell", cfg, {}) == "market"
    assert choose_exit_order_type("stop_loss", cfg, {"stop_loss_market": True}) == "market"
    assert choose_exit_order_type("take_profit", cfg, {}) == "limit"


def test_post_sell_controls_and_reentry_flags(tmp_path: Path) -> None:
    store = StateStore(str(tmp_path / "flags.sqlite"))
    post_sell_controls(
        store,
        _cfg(),
        {"deactivate_after_sell": False},
        reason="force_sell",
        exit_price_brl=5.4,
    )
    assert bool(store.get_flag("paused", False)) is True
    assert reentry_remaining_seconds(store) >= 1

    set_reentry_price_block(
        store,
        exit_price_brl=5.0,
        params={"return_rebuy_pct": 0.05},
        reason="take_profit",
    )
    assert round(reentry_price_threshold(store), 2) == 4.75


def test_build_safety_ladder_and_replace_dashboard_orders(tmp_path: Path) -> None:
    store = StateStore(str(tmp_path / "orders.sqlite"))
    params = {
        "first_buy_brl": 100.0,
        "max_cycle_brl": 400.0,
        "ramps": [
            {"drop_pct": 1.0, "multiplier": 1.2},
            {"drop_pct": 2.0, "multiplier": 1.5},
            {"drop_pct": 3.0, "multiplier": 2.0},
        ],
    }
    ladder = build_safety_ladder(avg_price=5.0, params=params, filled_count=1, current_spent=100.0)
    assert len(ladder) == 2
    assert ladder[0]["status"] == "filled"
    assert ladder[1]["status"] == "ready"

    position = store.get_position()
    replace_dashboard_orders(store, position, ladder, _cfg(), params, allow_new_entries=True)
    planned = store.read_df("planned_orders")
    assert len(planned) == 1
    assert planned.iloc[0]["side"] == "buy"

    store.update_position(
        status="open",
        entry_price_brl=5.0,
        avg_price_brl=5.0,
        qty_usdt=10.0,
        brl_spent=50.0,
        tp_price_brl=5.4,
    )
    replace_dashboard_orders(store, store.get_position(), ladder, _cfg(), params, allow_new_entries=True)
    planned = store.read_df("planned_orders")
    assert set(planned["side"].tolist()) == {"buy", "sell"}
