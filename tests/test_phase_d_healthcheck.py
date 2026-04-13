from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from smartcrypto.common.health import health_report
from smartcrypto.config import normalize_config
from smartcrypto.runtime.bot_runtime import write_runtime_status_cache
from smartcrypto.runtime.cache import market_cache_file
from smartcrypto.state.store import StateStore


class PhaseDHealthTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.cfg = normalize_config(
            {
                "__config_path": str(root / "config.yml"),
                "storage": {"db_path": str(root / "state.sqlite")},
                "dashboard": {"cache_dir": str(root / "cache")},
                "logging": {"dir": str(root / "logs"), "console": False},
                "health": {"stale_runtime_minutes": 20, "stale_market_cache_minutes": 240},
            },
            config_path=root / "config.yml",
        )
        self.store = StateStore(str(self.cfg["storage"]["db_path"]))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_health_report_warns_without_cache(self):
        report = health_report(self.cfg, self.store, interval="15m")
        self.assertEqual(report["status"], "warning")
        codes = {item["code"] for item in report["issues"]}
        self.assertIn("no_runtime_cache", codes)
        self.assertIn("no_market_cache", codes)

    def test_health_report_ok_with_snapshot_and_caches(self):
        self.store.add_snapshot(
            last_price_brl=5.2,
            equity_brl=10000.0,
            cash_brl=10000.0,
            pos_value_brl=0.0,
            realized_pnl_brl=0.0,
            unrealized_pnl_brl=0.0,
            drawdown_pct=0.0,
            regime="sideways",
        )
        write_runtime_status_cache(self.cfg, {"price_brl": 5.2, "equity_brl": 10000.0})
        cache_dir = Path(self.cfg["dashboard"]["cache_dir"])
        cache_dir.mkdir(parents=True, exist_ok=True)
        market_cache_file(self.cfg, "15m").write_text(
            json.dumps(
                {
                    "interval": "15m",
                    "rows": [],
                    "execution_mode": "paper",
                    "cache_scope": "paper",
                }
            ),
            encoding="utf-8",
        )
        report = health_report(self.cfg, self.store, interval="15m")
        self.assertEqual(report["status"], "ok")


    def test_health_report_ignores_mismatched_runtime_cache_payload(self):
        runtime_cache = Path(self.cfg["dashboard"]["cache_dir"]) / "runtime_status_paper_USDTBRL.json"
        runtime_cache.parent.mkdir(parents=True, exist_ok=True)
        runtime_cache.write_text(
            json.dumps(
                {
                    "saved_at": "2026-03-24T12:00:00Z",
                    "execution_mode": "live",
                    "cache_scope": "live",
                    "status": {"price_brl": 5.2},
                }
            ),
            encoding="utf-8",
        )
        report = health_report(self.cfg, self.store, interval="15m")
        codes = {item["code"] for item in report["issues"]}
        self.assertIn("no_runtime_cache", codes)


if __name__ == "__main__":
    unittest.main()
