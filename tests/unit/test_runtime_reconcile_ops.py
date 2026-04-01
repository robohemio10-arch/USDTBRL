from __future__ import annotations

from pathlib import Path

from smartcrypto.config import normalize_config
from smartcrypto.runtime import bot_runtime
from smartcrypto.runtime import reconcile_ops
from smartcrypto.state.store import StateStore


class FakeExchange:
    def __init__(self, qty_total: float = 0.0, open_orders: list[dict] | None = None, min_qty: float = 0.001) -> None:
        self.qty_total = qty_total
        self._open_orders = list(open_orders or [])
        self._min = min_qty

    def get_account_balances(self):
        return {"USDT": {"total": self.qty_total}}

    def base_asset_symbol(self) -> str:
        return "USDT"

    def get_open_orders(self):
        return list(self._open_orders)

    def _min_qty(self, for_market: bool = False):
        return self._min


def make_cfg(tmp_path: Path, *, mode: str = "live", allow_extra_balance: bool = False) -> dict:
    return normalize_config(
        {
            "__config_path": str(tmp_path / "config.yml"),
            "storage": {"db_path": str(tmp_path / "state.sqlite")},
            "execution": {"mode": mode},
            "runtime": {
                "reconcile_pause_on_mismatch": True,
                "reconcile_allow_extra_base_asset_balance": allow_extra_balance,
                "reconcile_qty_tolerance_usdt": 0.0001,
            },
        },
        config_path=tmp_path / "config.yml",
    )


def test_reconcile_live_exchange_state_short_circuits_in_paper(tmp_path):
    cfg = make_cfg(tmp_path, mode="paper")
    store = StateStore(str(cfg["storage"]["db_path"]))
    exchange = FakeExchange(qty_total=5.0)

    result = reconcile_ops.reconcile_live_exchange_state(cfg, store, exchange, last_price=5.2)

    assert result.reason == "mode_not_live"
    assert result.needs_action is False
    assert store.get_flag("live_reconcile_required", False) is False


def test_reconcile_live_exchange_state_flags_mismatch_and_pauses(tmp_path):
    cfg = make_cfg(tmp_path, mode="live", allow_extra_balance=False)
    store = StateStore(str(cfg["storage"]["db_path"]))
    exchange = FakeExchange(qty_total=2.5)

    result = reconcile_ops.reconcile_live_exchange_state(cfg, store, exchange, last_price=5.2)

    assert result.reason == "exchange_position_exists_while_local_flat"
    assert result.needs_action is True
    assert store.get_flag("live_reconcile_required", False) is True
    assert store.get_flag("paused", False) is True
    audits = store.read_df("reconciliation_audit", 10)
    assert not audits.empty


def test_live_reconcile_qty_tolerance_respects_exchange_min_qty(tmp_path):
    cfg = make_cfg(tmp_path, mode="live")
    tolerance = reconcile_ops.live_reconcile_qty_tolerance(cfg, FakeExchange(min_qty=0.005))
    assert tolerance == 0.005


def test_bot_runtime_reexports_reconcile_functions():
    assert bot_runtime.recover_dispatch_locks is reconcile_ops.recover_dispatch_locks
    assert bot_runtime.reconcile_live_exchange_state is reconcile_ops.reconcile_live_exchange_state
