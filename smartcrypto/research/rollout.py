from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


def rollout_flags(feature_flags: Mapping[str, bool] | None) -> dict[str, bool]:
    flags = dict(feature_flags or {})
    return {
        "shadow_enabled": bool(flags.get("research.shadow_mode_enabled") or flags.get("shadow_mode_enabled") or flags.get("shadow_mode")),
        "paper_enabled": bool(flags.get("research.paper_decision_enabled") or flags.get("paper_decision_enabled") or flags.get("research.ai_paper_enabled") or flags.get("ai_paper_enabled")),
        "live_partial_enabled": bool(flags.get("research.live_partial_enabled") or flags.get("live_partial_enabled") or flags.get("research.ai_live_partial_enabled") or flags.get("ai_live_partial_enabled")),
        "apply_entry_filter": bool(flags.get("research.apply_entry_filter", True)),
        "apply_execution_quality": bool(flags.get("research.apply_execution_quality", True)),
        "apply_position_manager": bool(flags.get("research.apply_position_manager", False)),
    }


@dataclass
class RolloutDecision:
    stage: str
    methodology: str
    ready: bool
    entry_gate: bool
    execution_gate: bool
    final_gate: bool
    position_action: str
    reason: str
    metrics: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)



def _base_thresholds(cfg: Mapping[str, Any]) -> dict[str, float]:
    research = cfg.get("research", {}) if isinstance(cfg, Mapping) else {}
    return {
        "min_shadow_rows": float(research.get("ai_rollout_min_rows", 40) or 40),
        "min_entry_lift": float(research.get("ai_rollout_min_entry_lift", 0.0) or 0.0),
        "min_execution_lift": float(research.get("ai_rollout_min_execution_lift", 0.0) or 0.0),
        "min_position_lift": float(research.get("ai_rollout_min_position_lift", -0.002) or -0.002),
        "min_entry_positive_rate": float(research.get("ai_rollout_min_entry_positive_rate", 0.50) or 0.50),
        "min_fill_hit_rate": float(research.get("ai_rollout_min_fill_hit_rate", 0.50) or 0.50),
    }



def promotion_readiness(cfg: Mapping[str, Any], shadow_result: Mapping[str, Any]) -> dict[str, Any]:
    scope_ok, scope = market_scope_allowed(cfg)
    thresholds = _thresholds_for_scope(cfg, scope)
    validation = dict(shadow_result.get("validation", {}))
    entry = dict(validation.get("entry_filter_comparison", {}))
    execution = dict(validation.get("execution_quality_comparison", {}))
    position = dict(validation.get("position_manager_comparison", {}))
    rows = int(shadow_result.get("rows", 0) or 0)

    entry_baseline = dict(entry.get("baseline", {}))
    execution_baseline = dict(execution.get("baseline", {}))

    entry_ready = bool(
        rows >= thresholds["min_shadow_rows"]
        and float(entry.get("baseline_lift_vs_heuristic", 0.0) or 0.0) >= thresholds["min_entry_lift"]
        and float(entry_baseline.get("gated_positive_rate", 0.0) or 0.0) >= thresholds["min_entry_positive_rate"]
    )
    execution_ready = bool(
        rows >= thresholds["min_shadow_rows"]
        and float(execution.get("baseline_lift_vs_heuristic", 0.0) or 0.0) >= thresholds["min_execution_lift"]
        and float(execution_baseline.get("gated_fill_hit_rate", 0.0) or 0.0) >= thresholds["min_fill_hit_rate"]
    )
    position_ready = bool(
        rows >= thresholds["min_shadow_rows"]
        and float(position.get("baseline_lift_vs_heuristic", 0.0) or 0.0) >= thresholds["min_position_lift"]
    )
    overall_ready = bool(entry_ready and execution_ready and scope_ok)
    return {
        "rows": rows,
        "thresholds": thresholds,
        "entry_filter_ready": entry_ready,
        "execution_quality_ready": execution_ready,
        "position_manager_ready": position_ready,
        "overall_ready": overall_ready,
        "market_scope": scope,
    }



def _position_action(shadow_result: Mapping[str, Any], flags: Mapping[str, bool]) -> str:
    if not flags.get("apply_position_manager", False):
        return "disabled"
    position_manager = dict(shadow_result.get("position_manager", {}))
    selected = dict(position_manager.get("selected", {}))
    return str(selected.get("action", "wait"))



def build_paper_decision(cfg: Mapping[str, Any], shadow_result: Mapping[str, Any], feature_flags: Mapping[str, bool] | None = None) -> RolloutDecision:
    flags = rollout_flags(feature_flags)
    readiness = promotion_readiness(cfg, shadow_result)
    entry_filter = dict(shadow_result.get("entry_filter", {}))
    execution_quality = dict(shadow_result.get("execution_quality", {}))
    selected_entry = dict(entry_filter.get("selected", {}))
    selected_execution = dict(execution_quality.get("selected", {}))

    entry_gate = bool(selected_entry.get("gate", False)) if flags["apply_entry_filter"] else True
    execution_gate = bool(selected_execution.get("gate", False)) if flags["apply_execution_quality"] else True
    final_gate = bool(entry_gate and execution_gate and flags["paper_enabled"])

    reasons: list[str] = []
    reasons.append("paper_enabled" if flags["paper_enabled"] else "paper_disabled")
    reasons.append("entry_ok" if entry_gate else "entry_blocked")
    reasons.append("execution_ok" if execution_gate else "execution_blocked")
    reasons.append("shadow_ready" if readiness["overall_ready"] else "shadow_not_ready")

    return RolloutDecision(
        stage="paper_decision",
        methodology=str(shadow_result.get("methodology", "unknown")),
        ready=bool(readiness["overall_ready"]),
        entry_gate=entry_gate,
        execution_gate=execution_gate,
        final_gate=final_gate,
        position_action=_position_action(shadow_result, flags),
        reason="|".join(reasons),
        metrics={
            "readiness": readiness,
            "entry_filter": shadow_result.get("entry_filter", {}),
            "execution_quality": shadow_result.get("execution_quality", {}),
            "position_manager": shadow_result.get("position_manager", {}),
        },
    )



def build_live_partial_decision(cfg: Mapping[str, Any], shadow_result: Mapping[str, Any], feature_flags: Mapping[str, bool] | None = None) -> RolloutDecision:
    flags = rollout_flags(feature_flags)
    paper = build_paper_decision(cfg, shadow_result, feature_flags)
    ready = bool(paper.ready and flags["live_partial_enabled"])
    final_gate = bool(paper.final_gate and ready)
    reasons = [paper.reason, "live_partial_enabled" if flags["live_partial_enabled"] else "live_partial_disabled"]
    return RolloutDecision(
        stage="live_partial",
        methodology=paper.methodology,
        ready=ready,
        entry_gate=paper.entry_gate,
        execution_gate=paper.execution_gate,
        final_gate=final_gate,
        position_action=paper.position_action,
        reason="|".join(reasons),
        metrics=paper.metrics,
    )


def market_scope_allowed(cfg: Mapping[str, Any]) -> tuple[bool, dict[str, Any]]:
    market = cfg.get("market", {}) if isinstance(cfg, Mapping) else {}
    research = cfg.get("research", {}) if isinstance(cfg, Mapping) else {}
    symbol = str(market.get("symbol", "UNKNOWN"))
    timeframe = str(market.get("timeframe", "unknown"))
    allowed_symbols = {str(item) for item in (research.get("ai_rollout_allowed_symbols", []) or []) if str(item).strip()}
    allowed_timeframes = {str(item) for item in (research.get("ai_rollout_allowed_timeframes", []) or []) if str(item).strip()}
    policies = list(research.get("ai_rollout_market_policies", []) or [])
    matched_policy: dict[str, Any] | None = None
    for policy in policies:
        if not isinstance(policy, Mapping):
            continue
        p_symbol = str(policy.get("symbol", "") or "")
        p_timeframe = str(policy.get("timeframe", "") or "")
        if p_symbol and p_symbol != symbol:
            continue
        if p_timeframe and p_timeframe != timeframe:
            continue
        matched_policy = dict(policy)
        break
    symbol_ok = True if not allowed_symbols else symbol in allowed_symbols
    timeframe_ok = True if not allowed_timeframes else timeframe in allowed_timeframes
    policy_enabled = bool(matched_policy.get("enabled", True)) if matched_policy is not None else True
    return bool(symbol_ok and timeframe_ok and policy_enabled), {
        "symbol": symbol,
        "timeframe": timeframe,
        "allowed_symbols": sorted(allowed_symbols),
        "allowed_timeframes": sorted(allowed_timeframes),
        "symbol_ok": symbol_ok,
        "timeframe_ok": timeframe_ok,
        "policy": matched_policy or {},
        "policy_enabled": policy_enabled,
    }


def _thresholds_for_scope(cfg: Mapping[str, Any], scope: Mapping[str, Any]) -> dict[str, float]:
    thresholds = _base_thresholds(cfg)
    policy = dict(scope.get("policy", {}) or {})
    overrides = {
        "min_shadow_rows": policy.get("min_shadow_rows"),
        "min_entry_lift": policy.get("min_entry_lift"),
        "min_execution_lift": policy.get("min_execution_lift"),
        "min_position_lift": policy.get("min_position_lift"),
        "min_entry_positive_rate": policy.get("min_entry_positive_rate"),
        "min_fill_hit_rate": policy.get("min_fill_hit_rate"),
    }
    for key, value in overrides.items():
        if value is None:
            continue
        thresholds[key] = float(value)
    return thresholds
