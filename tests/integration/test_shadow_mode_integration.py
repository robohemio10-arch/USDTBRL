from pathlib import Path

from smartcrypto.research.shadow_mode import run_shadow_mode
from smartcrypto.state.store import StateStore
from tests.fakes.fake_binance import FakeBinanceAdapter


def test_run_shadow_mode_records_research_run(tmp_path: Path) -> None:
    store = StateStore(str(tmp_path / "shadow.sqlite"))
    exchange = FakeBinanceAdapter(symbol="USDTBRL", mark_price="5.2")  # type: ignore[arg-type]
    cfg = {"market": {"timeframe": "1m", "research_lookback_bars": 120}}

    result = run_shadow_mode(
        cfg,
        exchange,
        store,
        feature_flags={"research.shadow_mode_enabled": True},
    )

    assert result["enabled"] is True
    rows = store.database.read_sql(
        "select run_type, name from research_runs where run_type = ?",
        ("shadow_mode",),
    )
    assert len(rows) == 1
