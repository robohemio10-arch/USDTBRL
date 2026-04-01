from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from smartcrypto.config import normalize_config
from smartcrypto.runtime.bot_runtime import (
    execute_buy,
    recover_dispatch_locks,
    reconcile_live_exchange_state,
    tick,
)
from smartcrypto.state.store import StateStore


class FakeExchange:
    def __init__(self) -> None:
        self.orders_by_client_id = {}
        self.entry_fill = {
            "qty_usdt": 10.0,
            "quote_brl": 52.0,
            "price_brl": 5.2,
            "execution_report": {
                "requested_order_type": "limit",
                "final_state": "filled",
                "fallback_used": False,
                "attempts": [
                    {
                        "attempt_no": 1,
                        "submitted": {
                            "order_id": 123,
                            "client_order_id": "SC123-L1",
                            "side": "buy",
                            "order_type": "limit",
                            "status": "NEW",
                            "price_brl": 5.2,
                            "qty_usdt": 10.0,
                            "executed_qty_usdt": 0.0,
                            "quote_brl": 0.0,
                            "updated_at": "2026-03-18T00:00:00Z",
                        },
                        "latest": {
                            "order_id": 123,
                            "client_order_id": "SC123-L1",
                            "side": "buy",
                            "order_type": "limit",
                            "status": "FILLED",
                            "price_brl": 5.2,
                            "qty_usdt": 10.0,
                            "executed_qty_usdt": 10.0,
                            "quote_brl": 52.0,
                            "updated_at": "2026-03-18T00:00:02Z",
                        },
                        "remaining_quote_brl": 0.0,
                        "fallback_market": False,
                    }
                ],
            },
        }
        self.open_orders = []
        self.balance_total = 0.0

    def fetch_ohlcv(self, timeframe: str, limit: int) -> pd.DataFrame:
        rows = []
        base = pd.Timestamp("2026-03-18T00:00:00Z")
        for i in range(limit):
            rows.append(
                {
                    "open_time": base + pd.Timedelta(minutes=i),
                    "open": 5.18,
                    "high": 5.22,
                    "low": 5.17,
                    "close": 5.20,
                    "volume": 1000.0,
                    "close_time": base + pd.Timedelta(minutes=i + 1),
                }
            )
        return pd.DataFrame(rows)

    def get_last_price(self) -> float:
        return 5.2

    def get_account_balances(self):
        return {"USDT": {"free": self.balance_total, "locked": 0.0, "total": self.balance_total}}

    def base_asset_symbol(self) -> str:
        return "USDT"

    def get_open_orders(self):
        return list(self.open_orders)

    def _normalize_order_snapshot(self, row):
        return row

    def get_order(self, order_id=None, client_order_id=None, raise_if_missing=True):
        result = self.orders_by_client_id.get(client_order_id)
        if result is None and raise_if_missing:
            raise RuntimeError("order not found")
        return result

    def execute_entry(
        self, *, brl_value, price_brl, order_type, fallback_market, client_order_id_prefix
    ):
        return dict(self.entry_fill)


class PhaseBHardeningTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "state.sqlite")
        self.cfg = normalize_config(
            {
                "storage": {"db_path": self.db_path},
                "execution": {"mode": "live"},
                "exchange": {"api_key": "x", "api_secret": "y"},
            },
            config_path=Path(self.temp_dir.name) / "config.yml",
        )
        self.store = StateStore(self.db_path)
        self.exchange = FakeExchange()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_reconcile_flags_mismatch_when_exchange_has_position_and_local_flat(self):
        self.exchange.balance_total = 10.0
        reconcile_live_exchange_state(self.cfg, self.store, self.exchange, last_price=5.2)
        self.assertTrue(self.store.get_flag("live_reconcile_required", False))
        self.assertTrue(self.store.get_flag("paused", False))
        audit = self.store.read_df("reconciliation_audit", 5)
        self.assertFalse(audit.empty)
        self.assertEqual(str(audit.iloc[0]["action"]), "mismatch")

    def test_recover_dispatch_lock_marks_terminal_when_exchange_order_exists(self):
        self.store.upsert_dispatch_lock(
            bot_order_id="BOT-1",
            side="buy",
            reason="initial_entry",
            order_type="limit",
            client_order_id="SCLOCK-L1",
            status="submit_unknown",
            requested_price_brl=5.2,
            requested_brl_value=25.0,
            details={"client_order_id_prefix": "SCLOCK"},
        )
        self.exchange.orders_by_client_id["SCLOCK-L1"] = {
            "order_id": 999,
            "client_order_id": "SCLOCK-L1",
            "side": "buy",
            "order_type": "limit",
            "status": "FILLED",
            "price_brl": 5.2,
            "qty_usdt": 5.0,
            "executed_qty_usdt": 5.0,
            "quote_brl": 26.0,
            "updated_at": "2026-03-18T00:00:01Z",
        }
        recover_dispatch_locks(self.cfg, self.store, self.exchange)
        lock = self.store.get_dispatch_lock("BOT-1")
        self.assertEqual(lock["status"], "terminal")
        self.assertTrue((self.store.read_df("order_events", 20)["bot_order_id"] == "BOT-1").any())
        self.assertEqual(self.store.get_position().status, "open")
        trades = self.store.read_df("trades", 20)
        self.assertFalse(trades.empty)
        self.assertEqual(str(trades.iloc[0]["bot_order_id"]), "BOT-1")

    def test_execute_buy_live_clears_dispatch_lock_and_updates_position(self):
        position = self.store.get_position()
        params = {
            "first_buy_brl": 25.0,
            "max_cycle_brl": 2500.0,
            "tp": 0.0065,
            "trailing_enabled": True,
            "trailing_activation": 0.0045,
            "trailing_callback": 0.0018,
            "stop_loss_enabled": True,
            "stop": 0.024,
            "stop_loss_market": True,
        }
        updated = execute_buy(
            store=self.store,
            position=position,
            exchange=self.exchange,
            price_brl=5.2,
            brl_value=25.0,
            reason="initial_entry",
            regime="sideways",
            cfg=self.cfg,
            params=params,
        )
        self.assertEqual(updated.status, "open")
        locks = self.store.read_df("order_dispatch_locks", 10)
        self.assertFalse(locks.empty)
        self.assertEqual(str(locks.iloc[0]["status"]), "terminal")

    def test_tick_blocks_when_dispatch_lock_active(self):
        self.store.upsert_dispatch_lock(
            bot_order_id="LOCK-2",
            side="buy",
            reason="initial_entry",
            order_type="limit",
            client_order_id="SCLOCK2-L1",
            status="submit_unknown",
            requested_price_brl=5.2,
            requested_brl_value=25.0,
            details={"client_order_id_prefix": "SCLOCK2"},
        )
        result = tick(self.cfg, self.store, self.exchange)
        self.assertEqual(result["position"]["status"], "flat")
        self.assertTrue(result["live_hardening"]["active_dispatch_locks"])


if __name__ == "__main__":
    unittest.main()
