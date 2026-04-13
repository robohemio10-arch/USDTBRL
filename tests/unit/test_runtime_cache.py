from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from smartcrypto.runtime.cache import (
    dashboard_cache_dir,
    market_cache_file,
    open_orders_cache_file,
    persist_dashboard_runtime_state,
    read_market_cache_payload,
    read_runtime_status_payload,
    runtime_status_cache_file,
    write_market_cache,
    write_runtime_status_cache,
)


class _LiveExchange:
    def get_open_orders(self):
        return [{"order_id": "123", "updated_at": "2026-03-24T12:00:00Z"}]


def _cfg(tmp_path: Path, mode: str = "paper") -> dict[str, object]:
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    cfg = {
        "__config_path": str(config_dir / "config.yml"),
        "dashboard": {"cache_dir": "data/dashboard_cache"},
        "market": {"symbol": "USDT/BRL", "timeframe": "1m"},
        "execution": {"mode": mode},
    }
    return cfg


def test_cache_paths_resolve_from_config_root(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cache_dir = dashboard_cache_dir(cfg)

    assert cache_dir == tmp_path / "data" / "dashboard_cache"
    assert market_cache_file(cfg, "1m").name == "market_paper_USDTBRL_1m.json"
    assert runtime_status_cache_file(cfg).name == "runtime_status_paper_USDTBRL.json"
    assert open_orders_cache_file(cfg).name == "open_orders_paper_USDTBRL.json"


def test_cache_paths_are_scoped_by_profile_or_mode(tmp_path: Path) -> None:
    paper_cfg = _cfg(tmp_path, mode="paper")
    live_cfg = _cfg(tmp_path, mode="live")

    assert market_cache_file(paper_cfg, "1m").name != market_cache_file(live_cfg, "1m").name
    assert runtime_status_cache_file(paper_cfg).name != runtime_status_cache_file(live_cfg).name
    assert open_orders_cache_file(paper_cfg).name != open_orders_cache_file(live_cfg).name


def test_write_market_cache_normalizes_timestamps(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    df = pd.DataFrame([{"ts": "2026-03-24 12:00:00", "open": 5.0, "high": 5.1, "low": 4.9, "close": 5.05}])

    write_market_cache(cfg, "1m", df)

    payload = json.loads(market_cache_file(cfg, "1m").read_text(encoding="utf-8"))
    assert payload["rows"][0]["ts"] == "2026-03-24T12:00:00Z"
    assert payload["execution_mode"] == "paper"
    assert payload["cache_scope"] == "paper"


def test_persist_dashboard_runtime_state_writes_open_orders_for_live(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, mode="live")

    persist_dashboard_runtime_state(cfg, _LiveExchange(), {"ok": True})

    payload = json.loads(open_orders_cache_file(cfg).read_text(encoding="utf-8"))
    assert payload["execution_mode"] == "live"
    assert payload["cache_scope"] == "live"
    assert payload["orders"][0]["order_id"] == "123"



def test_read_runtime_status_payload_ignores_mismatched_scope(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, mode="paper")
    write_runtime_status_cache(cfg, {"ok": True})

    payload = json.loads(runtime_status_cache_file(cfg).read_text(encoding="utf-8"))
    payload["execution_mode"] = "live"
    runtime_status_cache_file(cfg).write_text(json.dumps(payload), encoding="utf-8")

    assert read_runtime_status_payload(cfg) == {}


def test_read_market_cache_payload_requires_matching_interval(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    df = pd.DataFrame([{"ts": "2026-03-24 12:00:00", "open": 5.0, "high": 5.1, "low": 4.9, "close": 5.05}])

    write_market_cache(cfg, "1m", df)

    assert read_market_cache_payload(cfg, "1m")["interval"] == "1m"
    assert read_market_cache_payload(cfg, "5m") == {}
