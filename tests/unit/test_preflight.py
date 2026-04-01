from pathlib import Path

import pytest

from smartcrypto.runtime.preflight import assert_preflight_ok, live_confirmation_enabled, perform_preflight


def _cfg(tmp_path: Path, *, mode: str = "paper", allow_live: bool = False) -> tuple[dict, Path]:
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    resolved = config_dir / "config.yml"
    db_path = tmp_path / "runtime.sqlite"
    cfg = {
        "__config_path": str(resolved),
        "__boot_timestamp": "2026-03-26T00:00:00+00:00",
        "__run_id": "run-test-001",
        "storage": {"db_path": str(db_path)},
        "market": {"symbol": "USDT/BRL", "timeframe": "1m"},
        "execution": {"mode": mode, "allow_live": allow_live},
        "runtime": {"environment": "test"},
        "__feature_flags": {"runtime_v2": True},
    }
    resolved.write_text("execution:\n  mode: %s\n" % mode, encoding="utf-8")
    return cfg, resolved


def test_preflight_ok_for_paper(tmp_path: Path) -> None:
    cfg, resolved = _cfg(tmp_path, mode="paper")
    report = perform_preflight(cfg, resolved_config_path=resolved, config_is_canonical=True)
    assert report["status"] == "ok"
    assert report["mode"] == "paper"
    assert report["feature_flags_present"] is True
    assert report["run_id"] == "run-test-001"


def test_preflight_blocks_live_without_confirmation(tmp_path: Path) -> None:
    cfg, resolved = _cfg(tmp_path, mode="live", allow_live=False)
    report = perform_preflight(cfg, resolved_config_path=resolved, config_is_canonical=True)
    assert report["status"] == "failed"
    assert any("Modo live bloqueado" in item for item in report["errors"])
    with pytest.raises(ValueError, match="Preflight operacional falhou"):
        assert_preflight_ok(report)


def test_live_confirmation_enabled_accepts_explicit_flag(tmp_path: Path) -> None:
    cfg, resolved = _cfg(tmp_path, mode="live", allow_live=True)
    report = perform_preflight(
        cfg,
        resolved_config_path=resolved,
        config_is_canonical=True,
        adapter_probe=lambda _cfg: {
            "accessible": True,
            "normalized_symbol": "USDTBRL",
            "has_fetch_ohlcv": True,
            "has_get_last_price": True,
        },
    )
    assert live_confirmation_enabled(cfg) is True
    assert report["status"] == "ok"

def test_preflight_fails_closed_when_adapter_probe_errors(tmp_path: Path) -> None:
    cfg, resolved = _cfg(tmp_path, mode="paper")
    report = perform_preflight(
        cfg,
        resolved_config_path=resolved,
        config_is_canonical=True,
        adapter_probe=lambda _cfg: {
            "accessible": False,
            "normalized_symbol": "USDTBRL",
            "has_fetch_ohlcv": False,
            "has_get_last_price": False,
        },
    )
    assert report["status"] == "failed"
    assert any("Adapter/exchange inacessível" in item for item in report["errors"])
