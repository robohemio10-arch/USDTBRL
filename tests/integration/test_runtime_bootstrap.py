from pathlib import Path

from smartcrypto.runtime.cache import read_preflight_cache, read_runtime_manifest_cache


class _DummyExchange:
    def __init__(self, config):
        self.config = config


def _write_runtime_config(config_path: Path, db_path: Path) -> None:
    config_path.write_text(
        f"""
storage:
  db_path: "{db_path.as_posix()}"
market:
  symbol: USDT/BRL
  timeframe: 1m
portfolio:
  initial_cash_brl: 1000
execution:
  mode: paper
strategy:
  enabled: true
  first_buy_brl: 10
  max_cycle_brl: 100
risk:
  max_open_brl: 100
notifications:
  ntfy:
    enabled: false
""",
        encoding="utf-8",
    )


def test_runtime_bootstrap_persists_manifest_and_preflight(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    db_path = tmp_path / "runtime.sqlite"
    _write_runtime_config(config_dir / "config.yml", db_path)
    (config_dir / "feature_flags.yaml").write_text("runtime_v2: true\n", encoding="utf-8")

    monkeypatch.setattr("smartcrypto.runtime.orchestrator.ExchangeAdapter", _DummyExchange)

    from smartcrypto.runtime.orchestrator import bootstrap_runtime_services

    services = bootstrap_runtime_services(config_dir / "config.yml")

    manifest = read_runtime_manifest_cache(services.context.config)
    preflight = read_preflight_cache(services.context.config)

    assert manifest["mode"] == "paper"
    assert manifest["run_id"].startswith("run-")
    assert preflight["status"] == "ok"
    assert services.context.database.table_exists("runtime_manifest")
    assert services.context.database.table_exists("runtime_events")
