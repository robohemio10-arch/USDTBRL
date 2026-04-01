from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from smartcrypto.research.calibration import BinnedProbabilityCalibrator


@dataclass
class LinearBaselineModel:
    feature_names: list[str]
    ridge_alpha: float = 1e-3
    probability_bins: int = 10
    bias_: float = 0.0
    weights_: np.ndarray | None = None
    calibrator_: BinnedProbabilityCalibrator | None = None
    prob_loc_: float = 0.0
    prob_scale_: float = 1.0
    calibration_metrics_: dict[str, float] | None = None

    def fit(self, frame: pd.DataFrame, target_column: str = "target_net_return_h") -> "LinearBaselineModel":
        if frame.empty:
            self.bias_ = 0.0
            self.weights_ = np.zeros(len(self.feature_names), dtype=float)
            self.calibrator_ = None
            self.prob_loc_ = 0.0
            self.prob_scale_ = 1.0
            self.calibration_metrics_ = {"brier_score": 0.25, "positive_rate": 0.5}
            return self
        x = frame[self.feature_names].astype(float).to_numpy()
        y = frame[target_column].astype(float).to_numpy()
        ones = np.ones((len(frame), 1), dtype=float)
        design = np.hstack([ones, x])
        ridge = np.eye(design.shape[1], dtype=float) * float(self.ridge_alpha)
        ridge[0, 0] = 0.0
        coeffs = np.linalg.pinv(design.T @ design + ridge) @ design.T @ y
        self.bias_ = float(coeffs[0])
        self.weights_ = coeffs[1:]
        positive_col = "target_positive_net_h" if "target_positive_net_h" in frame.columns else None
        raw = np.clip(self.predict(frame), -0.05, 0.05)
        self.prob_loc_ = float(np.median(raw)) if raw.size else 0.0
        self.prob_scale_ = max(1e-6, float(np.std(raw)) or 1e-6)
        if positive_col is not None and len(frame) >= max(20, len(self.feature_names) * 2):
            zscore = np.clip((raw - self.prob_loc_) / self.prob_scale_, -20.0, 20.0)
            raw_prob = 1.0 / (1.0 + np.exp(-zscore))
            labels = frame[positive_col].astype(float).to_numpy()
            self.calibrator_ = BinnedProbabilityCalibrator(n_bins=int(self.probability_bins)).fit(raw_prob, labels)
            calibrated = self.calibrator_.predict(raw_prob) if self.calibrator_ else raw_prob
            self.calibration_metrics_ = {
                "brier_score": float(np.mean((calibrated - labels) ** 2)),
                "positive_rate": float(np.mean(labels)),
                "prob_mean": float(np.mean(calibrated)),
            }
        else:
            self.calibrator_ = None
            self.calibration_metrics_ = {"brier_score": 0.25, "positive_rate": 0.5, "prob_mean": 0.5}
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        if self.weights_ is None:
            raise RuntimeError("Model must be fit before predict().")
        x = frame[self.feature_names].astype(float).to_numpy()
        return self.bias_ + x @ self.weights_

    def predict_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame(columns=["predicted_net_return", "predicted_positive_net_prob", "score"])
        predicted = np.clip(self.predict(frame), -0.05, 0.05)
        zscore = np.clip((predicted - float(self.prob_loc_)) / max(1e-6, float(self.prob_scale_)), -20.0, 20.0)
        prob = 1.0 / (1.0 + np.exp(-zscore))
        if self.calibrator_ is not None:
            prob = self.calibrator_.predict(prob)
        return pd.DataFrame(
            {
                "predicted_net_return": predicted.astype(float),
                "predicted_positive_net_prob": prob.astype(float),
                "score": (prob * predicted).astype(float),
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_type": "linear_baseline",
            "feature_names": list(self.feature_names),
            "ridge_alpha": float(self.ridge_alpha),
            "bias": float(self.bias_),
            "weights": list((self.weights_ if self.weights_ is not None else np.zeros(len(self.feature_names))).astype(float)),
            "calibrator": None if self.calibrator_ is None else self.calibrator_.as_dict(),
            "prob_loc": float(self.prob_loc_),
            "prob_scale": float(self.prob_scale_),
            "calibration_metrics": dict(self.calibration_metrics_ or {}),
        }


def min_training_rows(feature_count: int) -> int:
    return max(40, feature_count * 6)
