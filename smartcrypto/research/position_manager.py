from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd

from smartcrypto.research.baseline_model import LinearBaselineModel
from smartcrypto.research.calibration import BinnedProbabilityCalibrator
from smartcrypto.research.entry_filter import baseline_entry_decision, heuristic_entry_decision
from smartcrypto.research.execution_quality import (
    ExecutionQualityModel,
    baseline_execution_decision,
    heuristic_execution_decision,
)
from smartcrypto.research.features import BASE_FEATURE_NAMES


@dataclass
class PositionDecision:
    methodology: str
    action: str
    confidence: float
    expected_return: float
    expected_drawdown: float
    recovery_probability: float
    reason: str

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("confidence", "expected_return", "expected_drawdown", "recovery_probability"):
            payload[key] = round(float(payload[key]), 8)
        return payload


class PositionManagerModel:
    def __init__(self, feature_names: list[str]) -> None:
        self.feature_names = list(feature_names)
        self.return_model = LinearBaselineModel(feature_names=list(feature_names), ridge_alpha=1e-2)
        self.recovery_model = LinearBaselineModel(feature_names=list(feature_names), ridge_alpha=1e-2)
        self.recovery_calibrator = BinnedProbabilityCalibrator(bins=10)

    def fit(self, frame: pd.DataFrame) -> "PositionManagerModel":
        self.return_model.fit(frame, target_column="target_net_return_h")
        self.recovery_model.fit(frame, target_column="target_positive_net_h")
        if not frame.empty and "target_positive_net_h" in frame.columns:
            raw = np.clip(self.recovery_model.predict(frame), 0.01, 0.999)
            self.recovery_calibrator.fit(raw, frame["target_positive_net_h"].astype(float).to_numpy())
        return self

    def predict_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame(columns=["expected_return", "recovery_probability"])
        returns = self.return_model.predict(frame)
        recovery_raw = self.recovery_model.predict(frame)
        recovery = self.recovery_calibrator.predict(np.clip(recovery_raw, 0.01, 0.999))
        return pd.DataFrame(
            {
                "expected_return": returns.astype(float),
                "recovery_probability": recovery.astype(float),
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_type": "position_manager_baseline",
            "feature_names": list(self.feature_names),
            "return_model": self.return_model.as_dict(),
            "recovery_model": self.recovery_model.as_dict(),
            "recovery_calibrator": self.recovery_calibrator.as_dict(),
        }


def position_manager_config_from_cfg(cfg: Mapping[str, Any]) -> dict[str, float]:
    research_cfg = cfg.get("research", {}) if isinstance(cfg, Mapping) else {}
    return {
        "take_profit_return": float(research_cfg.get("position_manager_take_profit_return", 0.004) or 0.004),
        "hold_min_recovery": float(research_cfg.get("position_manager_hold_min_recovery", 0.56) or 0.56),
        "reduce_max_drawdown": float(research_cfg.get("position_manager_reduce_max_drawdown", 0.012) or 0.012),
        "risk_off_max_drawdown": float(research_cfg.get("position_manager_risk_off_max_drawdown", 0.02) or 0.02),
        "wait_min_confidence": float(research_cfg.get("position_manager_wait_min_confidence", 0.52) or 0.52),
    }


def _position_context(position_context: Mapping[str, Any] | None) -> dict[str, float]:
    context = position_context or {}
    return {
        "unrealized_pnl_pct": float(context.get("unrealized_pnl_pct", 0.0) or 0.0),
        "distance_from_avg_price_pct": float(context.get("distance_from_avg_price_pct", 0.0) or 0.0),
        "safety_count": float(context.get("safety_count", 0.0) or 0.0),
    }


def _decision_from_signals(
    *,
    methodology: str,
    expected_return: float,
    expected_drawdown: float,
    recovery_probability: float,
    cfg: Mapping[str, Any],
    position_context: Mapping[str, Any] | None = None,
) -> PositionDecision:
    limits = position_manager_config_from_cfg(cfg)
    ctx = _position_context(position_context)
    unrealized = float(ctx["unrealized_pnl_pct"])
    distance = abs(float(ctx["distance_from_avg_price_pct"]))
    safety_count = float(ctx["safety_count"])

    confidence = float(np.clip(0.5 * recovery_probability + 0.5 * max(0.0, min(1.0, 0.5 + expected_return * 20.0)), 0.0, 1.0))

    if unrealized > max(limits["take_profit_return"], expected_return * 0.75) and expected_return <= limits["take_profit_return"] * 0.5:
        action = "take_profit"
        reason = "locked_gain_low_forward_upside"
    elif expected_drawdown >= limits["risk_off_max_drawdown"] and recovery_probability < 0.42:
        action = "risk_off"
        reason = "drawdown_critical_recovery_low"
    elif expected_drawdown >= limits["reduce_max_drawdown"] and (recovery_probability < 0.50 or expected_return < 0.0 or safety_count >= 2.0):
        action = "reduce"
        reason = "drawdown_high_or_recovery_soft"
    elif expected_return > 0.0 and recovery_probability >= limits["hold_min_recovery"] and confidence >= limits["wait_min_confidence"]:
        action = "hold"
        reason = "positive_forward_and_recovery_ok"
    else:
        action = "wait"
        if distance > expected_drawdown * 2.0:
            reason = "waiting_for_reentry_near_mean"
        else:
            reason = "signal_not_strong_enough"

    return PositionDecision(
        methodology=methodology,
        action=action,
        confidence=float(confidence),
        expected_return=float(expected_return),
        expected_drawdown=float(max(0.0, expected_drawdown)),
        recovery_probability=float(np.clip(recovery_probability, 0.0, 1.0)),
        reason=reason,
    )


def heuristic_position_decision(
    feature_row: Mapping[str, Any],
    cfg: Mapping[str, Any],
    *,
    position_context: Mapping[str, Any] | None = None,
) -> PositionDecision:
    entry = heuristic_entry_decision(feature_row, cfg)
    execution = heuristic_execution_decision(feature_row, cfg)
    expected_drawdown = max(
        0.0,
        float(execution.expected_cost_bps) / 10_000.0 + float(feature_row.get("volatility_20", 0.0)) * 0.35,
    )
    recovery_probability = np.clip(
        entry.predicted_positive_net_prob - execution.latency_risk * 0.15 + max(0.0, float(feature_row.get("close_above_sma_20", 0.0))) * 0.03,
        0.01,
        0.999,
    )
    return _decision_from_signals(
        methodology="heuristic_position_manager",
        expected_return=float(entry.predicted_net_return),
        expected_drawdown=float(expected_drawdown),
        recovery_probability=float(recovery_probability),
        cfg=cfg,
        position_context=position_context,
    )


def baseline_position_decision(
    feature_row: Mapping[str, Any] | pd.Series,
    cfg: Mapping[str, Any],
    *,
    position_context: Mapping[str, Any] | None = None,
    model: PositionManagerModel | None = None,
    entry_model: LinearBaselineModel | None = None,
    execution_model: ExecutionQualityModel | None = None,
) -> PositionDecision:
    if model is not None:
        row = {name: float(feature_row.get(name, 0.0)) for name in BASE_FEATURE_NAMES}
        frame = pd.DataFrame([row], columns=list(BASE_FEATURE_NAMES))
        prediction = model.predict_frame(frame).iloc[0]
        expected_return = float(prediction["expected_return"])
        recovery_probability = float(prediction["recovery_probability"])
    elif entry_model is not None:
        entry = baseline_entry_decision(entry_model, feature_row, cfg)
        expected_return = float(entry.predicted_net_return)
        recovery_probability = float(entry.predicted_positive_net_prob)
    else:
        return heuristic_position_decision(feature_row, cfg, position_context=position_context)

    if execution_model is not None:
        execution = baseline_execution_decision(execution_model, feature_row, cfg)
        expected_drawdown = max(0.0, float(execution.expected_cost_bps) / 10_000.0 + float(execution.latency_risk) * 0.01)
    else:
        expected_drawdown = max(0.0, float(feature_row.get("volatility_20", 0.0)) * 0.5)

    return _decision_from_signals(
        methodology="baseline_position_manager",
        expected_return=expected_return,
        expected_drawdown=float(expected_drawdown),
        recovery_probability=recovery_probability,
        cfg=cfg,
        position_context=position_context,
    )


def compare_position_manager(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"rows": 0, "baseline": {}, "heuristic": {}, "winner": "insufficient_data"}

    frame = pd.DataFrame(rows)

    def method_metrics(prefix: str) -> dict[str, Any]:
        action_col = f"{prefix}_action"
        conf_col = f"{prefix}_confidence"
        draw_col = f"{prefix}_expected_drawdown"
        take_profit = frame[frame[action_col] == "take_profit"]
        defensive = frame[frame[action_col].isin(["reduce", "risk_off"])]
        holds = frame[frame[action_col] == "hold"]
        return {
            "rows": int(len(frame)),
            "avg_confidence": round(float(frame[conf_col].mean()), 8),
            "avg_expected_drawdown": round(float(frame[draw_col].mean()), 8),
            "hold_rate": round(float((frame[action_col] == "hold").mean()), 8),
            "defensive_rate": round(float(frame[action_col].isin(["reduce", "risk_off"]).mean()), 8),
            "avg_realized_return_hold": round(float(holds["realized_net_return"].mean()) if len(holds) else 0.0, 8),
            "avg_realized_return_take_profit": round(float(take_profit["realized_net_return"].mean()) if len(take_profit) else 0.0, 8),
            "avg_realized_return_defensive": round(float(defensive["realized_net_return"].mean()) if len(defensive) else 0.0, 8),
        }

    baseline = method_metrics("baseline")
    heuristic = method_metrics("heuristic")
    baseline_quality = baseline["avg_realized_return_hold"] - baseline["avg_expected_drawdown"]
    heuristic_quality = heuristic["avg_realized_return_hold"] - heuristic["avg_expected_drawdown"]
    if baseline_quality > heuristic_quality:
        winner = "baseline_position_manager"
    elif heuristic_quality > baseline_quality:
        winner = "heuristic_position_manager"
    else:
        winner = "tie"
    return {
        "rows": int(len(frame)),
        "baseline": baseline,
        "heuristic": heuristic,
        "winner": winner,
        "baseline_lift_vs_heuristic": round(float(baseline_quality - heuristic_quality), 8),
    }
