
from smartcrypto.runtime.orchestrator import bootstrap_runtime_context


def test_bootstrap_runtime_context_injects_feature_flags_into_config(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    db_path = tmp_path / "state.sqlite"

    (config_dir / "config.yml").write_text(
        f"""
storage:
  db_path: "{db_path.as_posix()}"
market:
  symbol: USDTBRL
  timeframe: 1m
portfolio:
  initial_cash_brl: 1000
execution:
  mode: paper
strategy:
  enabled: true
  max_cycle_brl: 1000
risk:
  max_open_brl: 1000
notifications:
  ntfy:
    enabled: false
"""
    )

    (config_dir / "feature_flags.yaml").write_text(
        """
research:
  shadow_mode_enabled: true
  paper_decision_enabled: true
"""
    )

    context = bootstrap_runtime_context(config_dir / "config.yml")

    assert context.feature_flags["research.shadow_mode_enabled"] is True
    assert context.feature_flags["research.paper_decision_enabled"] is True
    assert context.config["__feature_flags"]["research.shadow_mode_enabled"] is True
    assert context.config["__feature_flags"]["research.paper_decision_enabled"] is True
