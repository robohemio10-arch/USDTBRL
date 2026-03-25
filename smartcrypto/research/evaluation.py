from __future__ import annotations

from typing import Iterable, Mapping


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
        return {
            "rows": 0.0,
            "mean_abs_error": 0.0,
            "directional_accuracy_pct": 0.0,
            "avg_score": 0.0,
        }
    predictions = [float(row.get("predicted_return", 0.0)) for row in records]
    realized = [float(row.get("realized_return", 0.0)) for row in records]
    scores = [score_shadow_run(predicted, actual) for predicted, actual in zip(predictions, realized, strict=False)]
    return {
        "rows": float(len(records)),
        "mean_abs_error": round(mean_absolute_error(predictions, realized), 6),
        "directional_accuracy_pct": round(directional_accuracy(predictions, realized) * 100.0, 2),
        "avg_score": round(sum(scores) / len(scores), 6),
    }
