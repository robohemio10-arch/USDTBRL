from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd

from smartcrypto.research.baseline_model import LinearBaselineModel
from smartcrypto.research.calibration import BinnedProbabilityCalibrator
from smartcrypto.research.features import BASE_FEATURE_NAMES


@dataclass
class ExecutionQualityDecision:
    methodology: str
    expected_cost_bps: float
    fill_probability: float
    latency_risk: float
    score: float
    gate: bool
    max_expected_cost_bps: float
    min_fill_probability: float
    min_score: float
    reason: str

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("expected_cost_bps", "fill_probability", "latency_risk", "score"):
            payload[key] = round(float(payload[key]), 8)
        return payload


class ExecutionQualityModel:
    def __init__(self, feature_names: list[str]) -> None:
        self.feature_names = list(feature_names)
        self.cost_model = LinearBaselineModel(feature_names=list(feature_names), ridge_alpha=1e-2)
        self.fill_model = LinearBaselineModel(feature_names=list(feature_names), ridge_alpha=1e-2)
        self.fill_calibrator = BinnedProbabilityCalibrator(bins=10)

    def fit(self, frame: pd.DataFrame) -> "ExecutionQualityModel":
        self.cost_model.fit(frame, target_column="target_execution_cost_bps_h")
        self.fill_model.fit(frame, target_column="target_fill_probability_h")
        if not frame.empty and "target_fill_success_h" in frame.columns:
            raw_fill = np.clip(self.fill_model.predict(frame), 0.01, 0.999)
            self.fill_calibrator.fit(raw_fill, frame["target_fill_success_h"].astype(float).to_numpy())
        return self

    def predict_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame(columns=["expected_cost_bps", "fill_probability", "latency_risk", "score"])
        cost = np.clip(self.cost_model.predict(frame), 0.0, 250.0)
        fill = np.clip(self.fill_model.predict(frame), 0.01, 0.999)
        fill = self.fill_calibrator.predict(fill)
        latency_risk = np.clip(1.0 - fill + np.minimum(cost / 100.0, 1.0) * 0.25, 0.0, 1.0)
        score = np.clip(fill - (cost / 100.0) - (latency_risk * 0.2), -1.0, 1.0)
        return pd.DataFrame(
            {
                "expected_cost_bps": cost.astype(float),
                "fill_probability": fill.astype(float),
                "latency_risk": latency_risk.astype(float),
                "score": score.astype(float),
            }
        )

    def as_dict(self) -> dict[str, Any]:
        metrics = dict(self.fill_model.calibration_metrics_ or {})
        metrics["fill_calibrator_bins"] = int(self.fill_calibrator.bins)
        return {
            "model_type": "execution_quality_baseline",
            "feature_names": list(self.feature_names),
            "cost_model": self.cost_model.as_dict(),
            "fill_model": self.fill_model.as_dict(),
            "fill_calibrator": self.fill_calibrator.as_dict(),
            "calibration_metrics": metrics,
        }


def execution_quality_config_from_cfg(cfg: Mapping[str, Any]) -> dict[str, float]:
    research_cfg = cfg.get("research", {}) if isinstance(cfg, Mapping) else {}
    return {
        "max_expected_cost_bps": float(research_cfg.get("execution_quality_max_cost_bps", 18.0) or 18.0),
        "min_fill_probability": float(research_cfg.get("execution_quality_min_fill_probability", 0.60) or 0.60),
        "min_score": float(research_cfg.get("execution_quality_min_score", 0.10) or 0.10),
    }


def _decision_from_values(
    *,
    methodology: str,
    expected_cost_bps: float,
    fill_probability: float,
    latency_risk: float,
    score: float,
    cfg: Mapping[str, Any],
) -> ExecutionQualityDecision:
    limits = execution_quality_config_from_cfg(cfg)
    gate = bool(
        expected_cost_bps <= limits["max_expected_cost_bps"]
        and fill_probability >= limits["min_fill_probability"]
        and score >= limits["min_score"]
    )
    reason_parts: list[str] = []
    reason_parts.append("cost_ok" if expected_cost_bps <= limits["max_expected_cost_bps"] else "cost_high")
    reason_parts.append("fill_ok" if fill_probability >= limits["min_fill_probability"] else "fill_low")
    reason_parts.append("score_ok" if score >= limits["min_score"] else "score_low")
    return ExecutionQualityDecision(
        methodology=methodology,
        expected_cost_bps=float(expected_cost_bps),
        fill_probability=float(fill_probability),
        latency_risk=float(latency_risk),
        score=float(score),
        gate=gate,
        max_expected_cost_bps=float(limits["max_expected_cost_bps"]),
        min_fill_probability=float(limits["min_fill_probability"]),
        min_score=float(limits["min_score"]),
        reason="|".join(reason_parts),
    )


def heuristic_execution_decision(feature_row: Mapping[str, Any], cfg: Mapping[str, Any]) -> ExecutionQualityDecision:
    volatility = float(feature_row.get("volatility_20", 0.0))
    candle_range = float(feature_row.get("hl_range_pct", 0.0))
    volume_z = float(feature_row.get("volume_zscore_20", 0.0))
    body_pct = abs(float(feature_row.get("body_pct", 0.0)))
    expected_cost_bps = np.clip(5.0 + volatility * 9500.0 + candle_range * 2800.0 + body_pct * 800.0 - max(volume_z, -1.5) * 1.75, 1.0, 120.0)
    fill_probability = np.clip(0.86 - volatility * 20.0 - candle_range * 4.5 - body_pct * 2.0 + max(volume_z, 0.0) * 0.03, 0.05, 0.995)
    latency_risk = np.clip(1.0 - fill_probability + min(expected_cost_bps / 100.0, 1.0) * 0.20, 0.0, 1.0)
    score = np.clip(fill_probability - (expected_cost_bps / 100.0) - (latency_risk * 0.15), -1.0, 1.0)
    return _decision_from_values(
        methodology="heuristic_execution_quality",
        expected_cost_bps=float(expected_cost_bps),
        fill_probability=float(fill_probability),
        latency_risk=float(latency_risk),
        score=float(score),
        cfg=cfg,
    )


def baseline_execution_decision(
    model: ExecutionQualityModel,
    feature_row: Mapping[str, Any] | pd.Series,
    cfg: Mapping[str, Any],
) -> ExecutionQualityDecision:
    row = {name: float(feature_row.get(name, 0.0)) for name in BASE_FEATURE_NAMES}
    frame = pd.DataFrame([row], columns=list(BASE_FEATURE_NAMES))
    prediction = model.predict_frame(frame).iloc[0]
    return _decision_from_values(
        methodology="baseline_execution_quality",
        expected_cost_bps=float(prediction["expected_cost_bps"]),
        fill_probability=float(prediction["fill_probability"]),
        latency_risk=float(prediction["latency_risk"]),
        score=float(prediction["score"]),
        cfg=cfg,
    )


def compare_execution_quality(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"rows": 0, "baseline": {}, "heuristic": {}, "winner": "insufficient_data"}

    frame = pd.DataFrame(rows)

    def method_metrics(prefix: str) -> dict[str, Any]:
        gate_col = f"{prefix}_gate"
        cost_col = f"{prefix}_expected_cost_bps"
        fill_col = f"{prefix}_fill_probability"
        score_col = f"{prefix}_score"
        gated = frame[frame[gate_col].astype(bool)]
        return {
            "rows": int(len(frame)),
            "gated_rows": int(len(gated)),
            "gate_rate": round(float(len(gated) / len(frame)), 6),
            "avg_expected_cost_bps": round(float(frame[cost_col].mean()), 8),
            "avg_fill_probability": round(float(frame[fill_col].mean()), 8),
            "avg_score": round(float(frame[score_col].mean()), 8),
            "avg_realized_cost_bps_gated": round(float(gated["realized_execution_cost_bps"].mean()) if len(gated) else 0.0, 8),
            "gated_fill_hit_rate": round(float(gated["realized_fill_success"].mean()) if len(gated) else 0.0, 8),
        }

    baseline = method_metrics("baseline")
    heuristic = method_metrics("heuristic")
    baseline_quality = heuristic_quality = 0.0
    if baseline["gated_rows"]:
        baseline_quality = baseline["gated_fill_hit_rate"] - baseline["avg_realized_cost_bps_gated"] / 100.0
    if heuristic["gated_rows"]:
        heuristic_quality = heuristic["gated_fill_hit_rate"] - heuristic["avg_realized_cost_bps_gated"] / 100.0
    if baseline_quality > heuristic_quality:
        winner = "baseline_execution_quality"
    elif heuristic_quality > baseline_quality:
        winner = "heuristic_execution_quality"
    else:
        winner = "tie"
    return {
        "rows": int(len(frame)),
        "baseline": baseline,
        "heuristic": heuristic,
        "winner": winner,
        "baseline_lift_vs_heuristic": round(float(baseline_quality - heuristic_quality), 8),
    }
