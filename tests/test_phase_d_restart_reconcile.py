from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from smartcrypto.config import normalize_config
from smartcrypto.runtime.bot_runtime import recover_dispatch_locks, reconcile_live_exchange_state
from smartcrypto.state.store import StateStore


class FakeExchangeRecover:
    def __init__(
        self,
        qty_total: float = 0.0,
        open_orders: list[dict] | None = None,
        recovered_order: dict | None = None,
    ) -> None:
        self.qty_total = qty_total
        self._open_orders = open_orders or []
        self._recovered_order = recovered_order

    def get_account_balances(self):
        return {"USDT": {"total": self.qty_total}}

    def base_asset_symbol(self) -> str:
        return "USDT"

    def get_open_orders(self):
        return list(self._open_orders)

    def get_order(self, order_id=None, client_order_id=None, raise_if_missing=True):
        if self._recovered_order is not None and client_order_id in {
            self._recovered_order.get("client_order_id"),
            "SCLOCK-L1",
        }:
            return dict(self._recovered_order)
        if raise_if_missing:
            raise RuntimeError("order not found")
        return None

    def _normalize_order_snapshot(self, row):
        return dict(row)

    def _min_qty(self, for_market=False):
        return 0.0001


class PhaseDRestartTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.cfg = normalize_config(
            {
                "__config_path": str(root / "config.yml"),
                "storage": {"db_path": str(root / "state.sqlite")},
                "execution": {"mode": "live"},
            },
            config_path=root / "config.yml",
        )
        self.store = StateStore(str(self.cfg["storage"]["db_path"]))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_reconcile_pauses_on_exchange_position_mismatch(self):
        exchange = FakeExchangeRecover(qty_total=7.5)
        reconcile_live_exchange_state(self.cfg, self.store, exchange, last_price=5.2)
        self.assertTrue(self.store.get_flag("live_reconcile_required", False))
        self.assertTrue(self.store.get_flag("paused", False))

    def test_recover_dispatch_lock_marks_event(self):
        self.store.upsert_dispatch_lock(
            bot_order_id="bot-1",
            side="buy",
            reason="entry",
            order_type="limit",
            status="submit_unknown",
            client_order_id="SCLOCK-L1",
            details={"client_order_id_prefix": "SCLOCK"},
        )
        exchange = FakeExchangeRecover(
            recovered_order={
                "order_id": "123",
                "client_order_id": "SCLOCK-L1",
                "side": "buy",
                "order_type": "limit",
                "status": "FILLED",
                "price_brl": 5.2,
                "qty_usdt": 10.0,
                "executed_qty_usdt": 10.0,
                "quote_brl": 52.0,
                "updated_at": "2026-03-18T00:00:02Z",
            }
        )
        recover_dispatch_locks(self.cfg, self.store, exchange)
        events = self.store.read_df("order_events", 20)
        self.assertFalse(events.empty)
        self.assertIn("filled", set(events["state"].astype(str).str.lower()))
        self.assertEqual(self.store.get_position().status, "open")
        self.assertGreater(self.store.get_position().qty_usdt, 0.0)


if __name__ == "__main__":
    unittest.main()
