from pathlib import Path

from smartcrypto.research.ml_store import MLStore
from smartcrypto.research.rollout import build_live_partial_decision, build_paper_decision, promotion_readiness
from smartcrypto.research.shadow_mode import run_shadow_mode_on_dataframe
from tests.fixtures.sample_data import make_ohlcv


def sample_cfg(tmp_path: Path) -> dict:
    return {
        "market": {"symbol": "USDT/BRL", "timeframe": "1m", "research_lookback_bars": 180},
        "execution": {"fee_rate": 0.001},
        "research": {"label_horizon": 1, "shadow_slippage_bps": 5.0, "walk_forward_purge_gap": 1},
        "storage": {"ml_store_path": str(tmp_path / "ml_store.sqlite")},
    }


def test_promotion_readiness_returns_shape(tmp_path: Path) -> None:
    shadow = run_shadow_mode_on_dataframe(sample_cfg(tmp_path), make_ohlcv(180), feature_flags={"research.shadow_mode_enabled": True})
    readiness = promotion_readiness(sample_cfg(tmp_path), shadow)
    assert "overall_ready" in readiness
    assert readiness["rows"] == shadow["rows"]


def test_build_paper_decision_respects_flags(tmp_path: Path) -> None:
    cfg = sample_cfg(tmp_path)
    shadow = run_shadow_mode_on_dataframe(cfg, make_ohlcv(180), feature_flags={"research.shadow_mode_enabled": True})
    decision = build_paper_decision(cfg, shadow, {"research.paper_decision_enabled": True})
    assert decision.stage == "paper_decision"
    assert isinstance(decision.final_gate, bool)


def test_build_live_partial_requires_explicit_flag(tmp_path: Path) -> None:
    cfg = sample_cfg(tmp_path)
    shadow = run_shadow_mode_on_dataframe(cfg, make_ohlcv(180), feature_flags={"research.shadow_mode_enabled": True, "research.paper_decision_enabled": True})
    blocked = build_live_partial_decision(cfg, shadow, {"research.paper_decision_enabled": True})
    allowed = build_live_partial_decision(cfg, shadow, {"research.paper_decision_enabled": True, "research.live_partial_enabled": True})
    assert blocked.stage == "live_partial"
    assert blocked.final_gate is False
    assert allowed.stage == "live_partial"


def test_ml_store_supports_rollout_events(tmp_path: Path) -> None:
    store = MLStore(str(tmp_path / "ml_store.sqlite"))
    store.add_rollout_event("USDT/BRL", "1m", "paper_decision", {"gate": True})
    frame = store.read_df("rollout_events")
    assert len(frame) == 1
