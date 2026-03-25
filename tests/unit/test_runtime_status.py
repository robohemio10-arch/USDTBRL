from __future__ import annotations

from pathlib import Path

from smartcrypto.runtime.status import log_snapshot, status_payload
from smartcrypto.state.position_manager import PositionManager
from smartcrypto.state.store import StateStore


def _cfg(tmp_path: Path) -> dict[str, object]:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return {
        "__config_path": str(config_dir / "config.yml"),
        "dashboard": {"cache_dir": "data/dashboard_cache"},
        "market": {"symbol": "USDT/BRL", "timeframe": "1m"},
        "execution": {"mode": "paper"},
        "portfolio": {"initial_cash_brl": 1000.0},
        "health": {"stale_runtime_minutes": 20, "stale_market_cache_minutes": 240},
    }


def test_status_payload_includes_health_and_portfolio(tmp_path: Path) -> None:
    store = StateStore(str(tmp_path / "status.sqlite"))
    manager = PositionManager(store)
    manager.open_position(regime="bullish", entry_price_brl=5.0, qty_usdt=10.0, brl_spent=50.0)
    cfg = _cfg(tmp_path)

    payload = status_payload(store, 5.4, cfg)

    assert payload["portfolio"]["equity_brl"] == 1004.0
    assert payload["position"]["status"] == "open"
    assert payload["health"]["status"] in {"ok", "warning"}


def test_log_snapshot_persists_runtime_view(tmp_path: Path) -> None:
    store = StateStore(str(tmp_path / "snapshot.sqlite"))
    manager = PositionManager(store)
    manager.open_position(regime="bullish", entry_price_brl=5.0, qty_usdt=10.0, brl_spent=50.0)
    cfg = _cfg(tmp_path)

    log_snapshot(store, price=5.4, position=manager.current(), cfg=cfg, regime="bullish")

    snapshots = store.read_df("snapshots", 5)
    assert not snapshots.empty
    assert float(snapshots.iloc[0]["equity_brl"]) == 1004.0
