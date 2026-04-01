from pathlib import Path

from smartcrypto.runtime.runtime_manifest import build_runtime_manifest


def test_build_runtime_manifest_includes_run_id_protocol_and_profile(tmp_path: Path) -> None:
    cfg = {
        "__config_path": str(tmp_path / "config" / "config.yml"),
        "__boot_timestamp": "2026-03-26T12:00:00Z",
        "__run_id": "run-test-001",
        "__feature_flags": {"runtime_v2": True},
        "runtime": {
            "protocol_version": "paper-v1",
            "experiment_profile": "paper_7d",
            "experiment_profile_version": "2026.03.26",
            "profile_frozen": True,
            "session_label": "paper-session",
            "retention_days": 7,
            "environment": "paper",
        },
        "execution": {"mode": "paper"},
        "market": {"symbol": "USDT/BRL", "timeframe": "1m"},
        "storage": {"db_path": str(tmp_path / "runtime.sqlite")},
        "__preflight": {"status": "ok"},
    }

    manifest = build_runtime_manifest(cfg)

    assert manifest["run_id"] == "run-test-001"
    assert manifest["protocol_version"] == "paper-v1"
    assert manifest["experiment_profile"] == "paper_7d"
    assert manifest["profile_version"] == "2026.03.26"
    assert manifest["session_label"] == "paper-session"
    assert manifest["profile_frozen"] is True
    assert manifest["retention_days"] == 7