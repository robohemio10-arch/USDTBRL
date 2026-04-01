from pathlib import Path

import pytest

from smartcrypto.runtime.orchestrator import bootstrap_feature_flags, resolve_config_path


def test_resolve_config_path_defaults() -> None:
    assert resolve_config_path().name == "config.yml"


def test_bootstrap_feature_flags(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "feature_flags.yaml").write_text("runtime_v2: true\n", encoding="utf-8")

    assert bootstrap_feature_flags(config_dir) == {"runtime_v2": True}


class _DummyExchange:
    def __init__(self, config):
        self.config = config
        self.symbol = "USDTBRL"

    def fetch_ohlcv(self, *args, **kwargs):
        return []

    def get_last_price(self):
        return 5.0


def _write_runtime_config(
    config_path: Path,
    db_path: Path,
    *,
    mode: str = "paper",
    allow_live: bool = False,
    runtime_block: str = "",
) -> None:
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
  mode: {mode}
  allow_live: {str(allow_live).lower()}
strategy:
  enabled: true
  first_buy_brl: 10
  max_cycle_brl: 100
risk:
  max_open_brl: 100
notifications:
  ntfy:
    enabled: false
runtime:
  environment: test
  single_instance_enabled: true
  instance_lock_path: data/runtime/test.lock.json
{runtime_block}
logging:
  dir: data/logs
""",
        encoding="utf-8",
    )


def test_bootstrap_runtime_context_exposes_state_layers(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    db_path = tmp_path / "runtime.sqlite"
    _write_runtime_config(config_dir / "config.yml", db_path)
    (config_dir / "feature_flags.yaml").write_text("runtime_v2: true\n", encoding="utf-8")

    monkeypatch.setattr("smartcrypto.runtime.orchestrator.ExchangeAdapter", _DummyExchange)

    from smartcrypto.runtime.orchestrator import bootstrap_runtime_context

    context = bootstrap_runtime_context(config_dir / "config.yml")

    assert Path(context.database.db_path) == db_path
    assert context.position_manager.current().status == "flat"
    assert context.portfolio.snapshot(mark_price_brl=5.0).equity_brl == 0.0
    assert context.feature_flags == {"runtime_v2": True}
    assert context.config["__run_id"].startswith("run-")
    assert context.store.get_flag("runtime_run_id")
    assert context.order_projections is context.store.order_projections
    assert context.order_events is context.store.order_events
    assert context.snapshots is context.store.snapshots
    assert context.bot_events is context.store.bot_events
    assert context.dispatch_locks is context.store.dispatch_locks
    assert context.reconciliation_audit is context.store.reconciliation_audit


def test_bootstrap_runtime_services_exposes_logger(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    db_path = tmp_path / "runtime.sqlite"
    _write_runtime_config(config_dir / "config.yml", db_path)
    (config_dir / "feature_flags.yaml").write_text("runtime_v2: true\n", encoding="utf-8")

    monkeypatch.setattr("smartcrypto.runtime.orchestrator.ExchangeAdapter", _DummyExchange)

    from smartcrypto.runtime.orchestrator import bootstrap_runtime_services

    services = bootstrap_runtime_services(config_dir / "config.yml")

    assert services.context.exchange.config["execution"]["mode"] == "paper"
    assert services.logger is not None
    assert services.config_path.endswith("config.yml")
    assert services.context.config["__config_path"].endswith("config.yml")
    assert services.context.config["__operational_manifest"]["run_id"] == services.context.config["__run_id"]


def test_bootstrap_runtime_services_injects_feature_flags_into_cfg(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    db_path = tmp_path / "runtime.sqlite"
    _write_runtime_config(config_dir / "config.yml", db_path)
    (config_dir / "feature_flags.yaml").write_text(
        "runtime_v2: true\nresearch.shadow_mode_enabled: true\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("smartcrypto.runtime.orchestrator.ExchangeAdapter", _DummyExchange)

    from smartcrypto.runtime.orchestrator import bootstrap_runtime_services

    services = bootstrap_runtime_services(config_dir / "config.yml")

    assert "__feature_flags" in services.context.config
    assert isinstance(services.context.config["__feature_flags"], dict)
    assert services.context.config["__feature_flags"]["runtime_v2"] is True
    assert services.context.config["__feature_flags"]["research.shadow_mode_enabled"] is True


def test_bootstrap_runtime_services_honors_profile_specific_config_and_flags(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    db_path = tmp_path / "paper.sqlite"
    _write_runtime_config(
        config_dir / "paper_7d.yml",
        db_path,
        runtime_block="""  experiment_profile: paper_7d
  experiment_profile_version: 2026.03.26
  protocol_version: paper-v1
  profile_frozen: true
  session_label: usdtbrl-paper-7d
""",
    )
    (config_dir / "feature_flags_paper_7d.yaml").write_text(
        "research.paper_decision_enabled: true\nresearch.shadow_mode_enabled: true\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("smartcrypto.runtime.orchestrator.ExchangeAdapter", _DummyExchange)

    from smartcrypto.runtime.orchestrator import bootstrap_runtime_services

    services = bootstrap_runtime_services(config_dir / "paper_7d.yml")

    assert services.config_path.endswith("paper_7d.yml")
    assert services.context.config["__config_path"].endswith("paper_7d.yml")
    assert services.context.config["__feature_flags"]["research.paper_decision_enabled"] is True


def test_bootstrap_runtime_services_fails_on_mode_ambiguity_between_selected_and_root_configs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    db_path = tmp_path / "runtime.sqlite"
    _write_runtime_config(config_dir / "config.yml", db_path, mode="paper")
    _write_runtime_config(tmp_path / "config.yml", db_path, mode="live")
    (config_dir / "feature_flags.yaml").write_text("runtime_v2: true\n", encoding="utf-8")

    monkeypatch.setattr("smartcrypto.runtime.orchestrator.ExchangeAdapter", _DummyExchange)

    from smartcrypto.runtime.orchestrator import bootstrap_runtime_services

    with pytest.raises(ValueError, match="Ambiguidade operacional detectada"):
        bootstrap_runtime_services(config_dir / "config.yml")


def test_bootstrap_runtime_services_blocks_live_without_confirmation(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    db_path = tmp_path / "live.sqlite"
    _write_runtime_config(config_dir / "config.yml", db_path, mode="live", allow_live=False)

    monkeypatch.setattr("smartcrypto.runtime.orchestrator.ExchangeAdapter", _DummyExchange)

    from smartcrypto.runtime.orchestrator import bootstrap_runtime_services

    with pytest.raises(ValueError, match="Modo live bloqueado sem confirmação explícita"):
        bootstrap_runtime_services(config_dir / "config.yml")