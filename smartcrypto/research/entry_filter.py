from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

import pandas as pd

from smartcrypto.research.baseline_model import LinearBaselineModel
from smartcrypto.research.features import BASE_FEATURE_NAMES


@dataclass
class EntryFilterDecision:
    methodology: str
    predicted_net_return: float
    predicted_positive_net_prob: float
    score: float
    gate: bool
    threshold_prob: float
    threshold_net_return: float
    threshold_score: float
    reason: str

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["predicted_net_return"] = round(float(self.predicted_net_return), 8)
        payload["predicted_positive_net_prob"] = round(float(self.predicted_positive_net_prob), 8)
        payload["score"] = round(float(self.score), 8)
        return payload


def entry_filter_config_from_cfg(cfg: Mapping[str, Any]) -> dict[str, float]:
    research_cfg = cfg.get("research", {}) if isinstance(cfg, Mapping) else {}
    return {
        "prob_threshold": float(research_cfg.get("entry_filter_prob_threshold", 0.53) or 0.53),
        "net_return_threshold": float(research_cfg.get("entry_filter_min_net_return", 0.0) or 0.0),
        "score_threshold": float(research_cfg.get("entry_filter_min_score", 0.0) or 0.0),
    }


def _decision_from_values(
    *,
    methodology: str,
    predicted_net_return: float,
    predicted_positive_net_prob: float,
    score: float,
    cfg: Mapping[str, Any],
) -> EntryFilterDecision:
    limits = entry_filter_config_from_cfg(cfg)
    gate = bool(
        predicted_positive_net_prob >= limits["prob_threshold"]
        and predicted_net_return >= limits["net_return_threshold"]
        and score >= limits["score_threshold"]
    )
    reason_parts: list[str] = []
    reason_parts.append("prob_ok" if predicted_positive_net_prob >= limits["prob_threshold"] else "prob_low")
    reason_parts.append("net_ok" if predicted_net_return >= limits["net_return_threshold"] else "net_low")
    reason_parts.append("score_ok" if score >= limits["score_threshold"] else "score_low")
    return EntryFilterDecision(
        methodology=methodology,
        predicted_net_return=float(predicted_net_return),
        predicted_positive_net_prob=float(predicted_positive_net_prob),
        score=float(score),
        gate=gate,
        threshold_prob=float(limits["prob_threshold"]),
        threshold_net_return=float(limits["net_return_threshold"]),
        threshold_score=float(limits["score_threshold"]),
        reason="|".join(reason_parts),
    )


def heuristic_entry_decision(feature_row: Mapping[str, Any], cfg: Mapping[str, Any]) -> EntryFilterDecision:
    predicted_net_return = max(
        -0.05,
        min(
            0.05,
            0.45 * float(feature_row.get("return_1", 0.0))
            + 0.35 * float(feature_row.get("return_5", 0.0))
            - 0.20 * float(feature_row.get("volatility_20", 0.0))
            + 0.05 * float(feature_row.get("body_pct", 0.0))
            + 0.02 * float(feature_row.get("close_above_sma_20", 0.0)),
        ),
    )
    predicted_positive_net_prob = 0.5 + max(-0.45, min(0.45, predicted_net_return * 18.0))
    score = predicted_positive_net_prob * predicted_net_return
    return _decision_from_values(
        methodology="heuristic_entry_filter",
        predicted_net_return=predicted_net_return,
        predicted_positive_net_prob=predicted_positive_net_prob,
        score=score,
        cfg=cfg,
    )


def baseline_entry_decision(
    model: LinearBaselineModel,
    feature_row: Mapping[str, Any] | pd.Series,
    cfg: Mapping[str, Any],
) -> EntryFilterDecision:
    row = {name: float(feature_row.get(name, 0.0)) for name in BASE_FEATURE_NAMES}
    frame = pd.DataFrame([row], columns=list(BASE_FEATURE_NAMES))
    prediction = model.predict_frame(frame).iloc[0]
    return _decision_from_values(
        methodology="baseline_entry_filter",
        predicted_net_return=float(prediction["predicted_net_return"]),
        predicted_positive_net_prob=float(prediction["predicted_positive_net_prob"]),
        score=float(prediction["score"]),
        cfg=cfg,
    )


def compare_entry_filters(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "rows": 0,
            "baseline": {},
            "heuristic": {},
            "winner": "insufficient_data",
        }

    frame = pd.DataFrame(rows)

    def method_metrics(prefix: str) -> dict[str, Any]:
        gate_col = f"{prefix}_gate"
        pred_col = f"{prefix}_predicted_net_return"
        prob_col = f"{prefix}_predicted_positive_net_prob"
        gated = frame[frame[gate_col].astype(bool)]
        metrics = {
            "rows": int(len(frame)),
            "gated_rows": int(len(gated)),
            "gate_rate": round(float(len(gated) / len(frame)), 6),
            "avg_predicted_net_return": round(float(frame[pred_col].mean()), 8),
            "avg_predicted_positive_prob": round(float(frame[prob_col].mean()), 8),
            "avg_realized_net_return_all": round(float(frame["realized_net_return"].mean()), 8),
            "avg_realized_net_return_gated": round(float(gated["realized_net_return"].mean()) if len(gated) else 0.0, 8),
            "gated_positive_rate": round(float(gated["target_positive_net"].mean()) if len(gated) else 0.0, 8),
        }
        return metrics

    baseline = method_metrics("baseline")
    heuristic = method_metrics("heuristic")
    baseline_score = baseline["avg_realized_net_return_gated"]
    heuristic_score = heuristic["avg_realized_net_return_gated"]
    if baseline_score > heuristic_score:
        winner = "baseline_entry_filter"
    elif heuristic_score > baseline_score:
        winner = "heuristic_entry_filter"
    else:
        winner = "tie"
    return {
        "rows": int(len(frame)),
        "baseline": baseline,
        "heuristic": heuristic,
        "winner": winner,
        "baseline_lift_vs_heuristic": round(float(baseline_score - heuristic_score), 8),
    }
