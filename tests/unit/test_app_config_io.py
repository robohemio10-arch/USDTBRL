from pathlib import Path

from smartcrypto.app import config_io


def test_config_consistency_status_detects_mode_mismatch(tmp_path, monkeypatch) -> None:
    root = tmp_path
    config_dir = root / "config"
    config_dir.mkdir()
    (config_dir / "config.yml").write_text("""execution:
  mode: paper
""", encoding="utf-8")
    (root / "config.yml").write_text("""execution:
  mode: live
""", encoding="utf-8")

    monkeypatch.setattr(config_io, "root_dir", lambda: root)

    status = config_io.config_consistency_status()

    assert status["both_exist"] is True
    assert status["same_content"] is False
    assert status["mode_mismatch"] is True
    assert status["canonical_path"] == config_dir / "config.yml"
