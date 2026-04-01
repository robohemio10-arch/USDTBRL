from __future__ import annotations

from typing import Any, Mapping

from smartcrypto.research.ml_store import MLStore
from smartcrypto.research.rollout import build_live_partial_decision, build_paper_decision, rollout_flags, market_scope_allowed
from smartcrypto.research.shadow_mode import run_shadow_mode_on_dataframe


def _ml_store(cfg: Mapping[str, Any]) -> MLStore:
    path = str(cfg.get("storage", {}).get("ml_store_path", "data/ml_store.sqlite"))
    return MLStore(path)


def _feature_flags(cfg: Mapping[str, Any]) -> dict[str, bool]:
    return dict(cfg.get("__feature_flags", {}) or {})


def should_run_ai(cfg: Mapping[str, Any], feature_flags: Mapping[str, bool] | None = None) -> bool:
    flags = rollout_flags(feature_flags or _feature_flags(cfg))
    return bool(flags.get("shadow_enabled") or flags.get("paper_enabled") or flags.get("live_partial_enabled"))


def evaluate_runtime_ai(cfg: Mapping[str, Any], store: Any, ohlcv: Any) -> dict[str, Any]:
    flags = _feature_flags(cfg)
    if not should_run_ai(cfg, flags):
        decision = {"enabled": False, "effective_entry_gate": True, "stage": "disabled", "reason": "ai_disabled"}
        store.set_flag("ai_runtime_decision", decision)
        return decision

    cadence = int(cfg.get("research", {}).get("ai_runtime_every_n_ticks", 1) or 1)
    tick_count = int(store.get_flag("ai_runtime_tick_count", 0) or 0) + 1
    store.set_flag("ai_runtime_tick_count", tick_count)
    if cadence > 1 and tick_count % cadence != 0:
        cached = store.get_flag("ai_runtime_decision", None)
        if isinstance(cached, dict):
            return cached

    shadow_flags = dict(flags)
    shadow_flags.setdefault("research.shadow_mode_enabled", True)
    shadow = run_shadow_mode_on_dataframe(dict(cfg), ohlcv, feature_flags=shadow_flags)
    scope_ok, scope = market_scope_allowed(cfg)
    paper = build_paper_decision(cfg, shadow, flags)
    live = build_live_partial_decision(cfg, shadow, flags)
    rollout = live if live.ready else paper
    selected_position = dict(shadow.get("position_manager", {})).get("selected", {})
    selected_exec = dict(shadow.get("execution_quality", {})).get("selected", {})
    selected_entry = dict(shadow.get("entry_filter", {})).get("selected", {})
    decision = {
        "enabled": True,
        "stage": rollout.stage,
        "ready": bool(rollout.ready),
        "effective_entry_gate": bool(rollout.final_gate),
        "entry_gate": bool(rollout.entry_gate),
        "execution_gate": bool(rollout.execution_gate),
        "position_action": str(rollout.position_action),
        "reason": str(rollout.reason),
        "symbol": str(cfg.get("market", {}).get("symbol", "UNKNOWN")),
        "timeframe": str(cfg.get("market", {}).get("timeframe", "unknown")),
        "entry_filter": selected_entry,
        "execution_quality": selected_exec,
        "position_manager": selected_position,
        "shadow": {
            "methodology": shadow.get("methodology", "unknown"),
            "rows": int(shadow.get("rows", 0) or 0),
            "metrics": shadow.get("metrics", {}),
            "validation": shadow.get("validation", {}),
        },
        "rollout": rollout.as_dict(),
        "market_scope": scope,
        "market_scope_ok": bool(scope_ok),
    }
    store.set_flag("ai_runtime_decision", decision)
    store.add_research_run("ai_runtime", "research.ai_runtime", {"rows": int(shadow.get("rows", 0) or 0)}, decision)
    store.add_event("INFO", "ai_runtime_decision", {"stage": decision["stage"], "effective_entry_gate": decision["effective_entry_gate"], "position_action": decision["position_action"]})
    ml_store = _ml_store(cfg)
    ml_store.add_rollout_event(decision["symbol"], decision["timeframe"], decision["stage"], decision)
    return decision
