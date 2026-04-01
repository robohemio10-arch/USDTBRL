from __future__ import annotations

from typing import Iterable, Mapping

import pandas as pd


def score_shadow_run(predicted: float, realized: float) -> float:
    return round(float(realized) - float(predicted), 10)


def mean_absolute_error(predictions: Iterable[float], realized: Iterable[float]) -> float:
    pred = list(float(value) for value in predictions)
    real = list(float(value) for value in realized)
    if not pred or len(pred) != len(real):
        return 0.0
    return sum(abs(a - b) for a, b in zip(pred, real, strict=False)) / len(pred)


def directional_accuracy(predictions: Iterable[float], realized: Iterable[float]) -> float:
    pred = list(float(value) for value in predictions)
    real = list(float(value) for value in realized)
    if not pred or len(pred) != len(real):
        return 0.0
    hits = 0
    for predicted, actual in zip(pred, real, strict=False):
        if predicted == 0.0 and actual == 0.0:
            hits += 1
        elif predicted == 0.0 or actual == 0.0:
            continue
        elif predicted > 0.0 and actual > 0.0:
            hits += 1
        elif predicted < 0.0 and actual < 0.0:
            hits += 1
    return hits / len(pred)


def evaluate_shadow_predictions(rows: Iterable[Mapping[str, float]]) -> dict[str, float]:
    records = list(rows)
    if not records:
        return {"rows": 0.0, "mean_abs_error": 0.0, "directional_accuracy_pct": 0.0, "avg_score": 0.0}
    predictions = [float(row.get("predicted_return", 0.0)) for row in records]
    realized = [float(row.get("realized_return", 0.0)) for row in records]
    scores = [score_shadow_run(predicted, actual) for predicted, actual in zip(predictions, realized, strict=False)]
    return {
        "rows": float(len(records)),
        "mean_abs_error": round(mean_absolute_error(predictions, realized), 6),
        "directional_accuracy_pct": round(directional_accuracy(predictions, realized) * 100.0, 2),
        "avg_score": round(sum(scores) / len(scores), 6),
    }


def compare_shadow_method_metrics(baseline_rows: Iterable[Mapping[str, float]], heuristic_rows: Iterable[Mapping[str, float]]) -> dict[str, float]:
    baseline = evaluate_shadow_predictions(baseline_rows)
    heuristic = evaluate_shadow_predictions(heuristic_rows)
    baseline_score = float(baseline.get("avg_score", 0.0))
    heuristic_score = float(heuristic.get("avg_score", 0.0))
    return {
        "baseline_rows": float(baseline.get("rows", 0.0)),
        "heuristic_rows": float(heuristic.get("rows", 0.0)),
        "baseline_directional_accuracy_pct": float(baseline.get("directional_accuracy_pct", 0.0)),
        "heuristic_directional_accuracy_pct": float(heuristic.get("directional_accuracy_pct", 0.0)),
        "baseline_avg_score": baseline_score,
        "heuristic_avg_score": heuristic_score,
        "baseline_score_lift": round(baseline_score - heuristic_score, 6),
        "winner": 1.0 if baseline_score > heuristic_score else (-1.0 if heuristic_score > baseline_score else 0.0),
    }


def _segment_table(frame: pd.DataFrame, segment_col: str) -> list[dict[str, float | str]]:
    if frame.empty or segment_col not in frame.columns:
        return []
    output: list[dict[str, float | str]] = []
    for segment, group in frame.groupby(segment_col, dropna=False):
        baseline_gate = group["baseline_gate"].astype(bool)
        heuristic_gate = group["heuristic_gate"].astype(bool)
        baseline_gated = group[baseline_gate]
        heuristic_gated = group[heuristic_gate]
        output.append(
            {
                segment_col: str(segment),
                "rows": int(len(group)),
                "baseline_gate_rate": round(float(baseline_gate.mean()), 6),
                "heuristic_gate_rate": round(float(heuristic_gate.mean()), 6),
                "baseline_gated_positive_rate": round(float(baseline_gated["target_positive_net"].mean()) if len(baseline_gated) else 0.0, 6),
                "heuristic_gated_positive_rate": round(float(heuristic_gated["target_positive_net"].mean()) if len(heuristic_gated) else 0.0, 6),
                "baseline_avg_realized": round(float(baseline_gated["realized_net_return"].mean()) if len(baseline_gated) else 0.0, 8),
                "heuristic_avg_realized": round(float(heuristic_gated["realized_net_return"].mean()) if len(heuristic_gated) else 0.0, 8),
            }
        )
    return output


def compare_entry_filters_by_segment(rows: Iterable[Mapping[str, float | str]]) -> dict[str, list[dict[str, float | str]]]:
    frame = pd.DataFrame(list(rows))
    return {
        "by_regime": _segment_table(frame, "regime_bucket"),
        "by_hour": _segment_table(frame, "hour_bucket"),
    }



def compare_execution_quality_by_segment(rows: Iterable[Mapping[str, float | str]]) -> dict[str, list[dict[str, float | str]]]:
    frame = pd.DataFrame(list(rows))
    return {
        "by_regime": _segment_execution_table(frame, "regime_bucket"),
        "by_hour": _segment_execution_table(frame, "hour_bucket"),
    }


def _segment_execution_table(frame: pd.DataFrame, segment_col: str) -> list[dict[str, float | str]]:
    if frame.empty or segment_col not in frame.columns:
        return []
    output: list[dict[str, float | str]] = []
    for segment, group in frame.groupby(segment_col, dropna=False):
        baseline_gate = group["baseline_gate"].astype(bool)
        heuristic_gate = group["heuristic_gate"].astype(bool)
        baseline_gated = group[baseline_gate]
        heuristic_gated = group[heuristic_gate]
        output.append({
            segment_col: str(segment),
            "rows": int(len(group)),
            "baseline_gate_rate": round(float(baseline_gate.mean()), 6),
            "heuristic_gate_rate": round(float(heuristic_gate.mean()), 6),
            "baseline_fill_hit_rate": round(float(baseline_gated["realized_fill_success"].mean()) if len(baseline_gated) else 0.0, 6),
            "heuristic_fill_hit_rate": round(float(heuristic_gated["realized_fill_success"].mean()) if len(heuristic_gated) else 0.0, 6),
            "baseline_avg_cost_bps": round(float(baseline_gated["realized_execution_cost_bps"].mean()) if len(baseline_gated) else 0.0, 8),
            "heuristic_avg_cost_bps": round(float(heuristic_gated["realized_execution_cost_bps"].mean()) if len(heuristic_gated) else 0.0, 8),
        })
    return output


def compare_position_manager_by_segment(rows: Iterable[Mapping[str, float | str]]) -> dict[str, list[dict[str, float | str]]]:
    frame = pd.DataFrame(list(rows))
    return {
        "by_regime": _segment_position_table(frame, "regime_bucket"),
        "by_hour": _segment_position_table(frame, "hour_bucket"),
    }


def _segment_position_table(frame: pd.DataFrame, segment_col: str) -> list[dict[str, float | str]]:
    if frame.empty or segment_col not in frame.columns:
        return []
    output: list[dict[str, float | str]] = []
    for segment, group in frame.groupby(segment_col, dropna=False):
        output.append({
            segment_col: str(segment),
            "rows": int(len(group)),
            "baseline_hold_rate": round(float((group["baseline_action"] == "hold").mean()), 6),
            "heuristic_hold_rate": round(float((group["heuristic_action"] == "hold").mean()), 6),
            "baseline_defensive_rate": round(float(group["baseline_action"].isin(["reduce", "risk_off"]).mean()), 6),
            "heuristic_defensive_rate": round(float(group["heuristic_action"].isin(["reduce", "risk_off"]).mean()), 6),
            "avg_realized_net_return": round(float(group["realized_net_return"].mean()), 8),
        })
    return output
