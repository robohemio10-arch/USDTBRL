from pathlib import Path

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


def test_bootstrap_runtime_context_exposes_state_layers(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    db_path = tmp_path / "runtime.sqlite"
    (config_dir / "config.yml").write_text(
        """
storage:
  db_path: {db_path}
execution:
  mode: paper
notifications:
  ntfy:
    enabled: false
""".format(db_path=db_path.as_posix()),
        encoding="utf-8",
    )
    (config_dir / "feature_flags.yaml").write_text("runtime_v2: true\n", encoding="utf-8")

    monkeypatch.setattr("smartcrypto.runtime.orchestrator.ExchangeAdapter", _DummyExchange)

    from smartcrypto.runtime.orchestrator import bootstrap_runtime_context

    context = bootstrap_runtime_context(config_dir / "config.yml")

    assert context.database.db_path == str(db_path)
    assert context.position_manager.current().status == "flat"
    assert context.portfolio.snapshot(mark_price_brl=5.0).equity_brl == 0.0
    assert context.feature_flags == {"runtime_v2": True}
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
    (config_dir / "config.yml").write_text(
        """
storage:
  db_path: {db_path}
execution:
  mode: paper
notifications:
  ntfy:
    enabled: false
logging:
  path: {log_path}
""".format(db_path=db_path.as_posix(), log_path=(tmp_path / "bot.jsonl").as_posix()),
        encoding="utf-8",
    )
    (config_dir / "feature_flags.yaml").write_text("runtime_v2: true\n", encoding="utf-8")

    monkeypatch.setattr("smartcrypto.runtime.orchestrator.ExchangeAdapter", _DummyExchange)

    from smartcrypto.runtime.orchestrator import bootstrap_runtime_services

    services = bootstrap_runtime_services(config_dir / "config.yml")

    assert services.context.exchange.config["execution"]["mode"] == "paper"
    assert services.logger is not None
    assert services.config_path.endswith("config.yml")
    assert services.context.config["__config_path"].endswith("config.yml")


def test_run_startup_reconcile_success(monkeypatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    db_path = tmp_path / "runtime.sqlite"
    (config_dir / "config.yml").write_text(
        """
storage:
  db_path: {db_path}
execution:
  mode: paper
notifications:
  ntfy:
    enabled: false
logging:
  path: {log_path}
""".format(db_path=db_path.as_posix(), log_path=(tmp_path / "bot.jsonl").as_posix()),
        encoding="utf-8",
    )
    (config_dir / "feature_flags.yaml").write_text("runtime_v2: true\n", encoding="utf-8")
    monkeypatch.setattr("smartcrypto.runtime.orchestrator.ExchangeAdapter", _DummyExchange)

    from smartcrypto.runtime.orchestrator import bootstrap_runtime_context, run_startup_reconcile

    context = bootstrap_runtime_context(config_dir / "config.yml")

    calls = {"recover": 0, "reconcile": 0}

    class _DummyLogger:
        def __init__(self) -> None:
            self.codes = []

        def info(self, code: str, **kwargs) -> None:
            self.codes.append(code)

        def error(self, code: str, **kwargs) -> None:
            self.codes.append(code)

    class _PriceExchange(_DummyExchange):
        def get_last_price(self) -> float:
            return 5.0

    context = type(context)(
        **{**context.__dict__, "exchange": _PriceExchange(context.config)}
    )

    run_startup_reconcile(
        context,
        _DummyLogger(),
        build_id="build-test",
        recover_dispatch_locks_fn=lambda cfg, store, exchange: calls.__setitem__("recover", calls["recover"] + 1),
        reconcile_live_exchange_state_fn=lambda cfg, store, exchange, last_price: calls.__setitem__("reconcile", calls["reconcile"] + 1),
    )

    assert calls == {"recover": 1, "reconcile": 1}


def test_run_startup_reconcile_failure(monkeypatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    db_path = tmp_path / "runtime.sqlite"
    (config_dir / "config.yml").write_text(
        """
storage:
  db_path: {db_path}
execution:
  mode: paper
notifications:
  ntfy:
    enabled: false
logging:
  path: {log_path}
""".format(db_path=db_path.as_posix(), log_path=(tmp_path / "bot.jsonl").as_posix()),
        encoding="utf-8",
    )
    (config_dir / "feature_flags.yaml").write_text("runtime_v2: true\n", encoding="utf-8")
    monkeypatch.setattr("smartcrypto.runtime.orchestrator.ExchangeAdapter", _DummyExchange)

    from smartcrypto.runtime.orchestrator import bootstrap_runtime_context, run_startup_reconcile

    context = bootstrap_runtime_context(config_dir / "config.yml")

    class _DummyLogger:
        def __init__(self) -> None:
            self.info_codes = []
            self.error_codes = []

        def info(self, code: str, **kwargs) -> None:
            self.info_codes.append(code)

        def error(self, code: str, **kwargs) -> None:
            self.error_codes.append(code)

    logger = _DummyLogger()
    run_startup_reconcile(
        context,
        logger,
        build_id="build-test",
        recover_dispatch_locks_fn=lambda cfg, store, exchange: (_ for _ in ()).throw(RuntimeError("boom")),
        reconcile_live_exchange_state_fn=lambda *args, **kwargs: None,
    )

    assert "live_startup_reconcile_failed" in logger.error_codes
