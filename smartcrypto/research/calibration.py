from __future__ import annotations

from typing import Any

import numpy as np


class BinnedProbabilityCalibrator:
    def __init__(self, bins: int = 10, n_bins: int | None = None):
        resolved_bins = int(n_bins if n_bins is not None else bins)
        self.bins = resolved_bins
        self.n_bins = resolved_bins
        self.bin_edges: np.ndarray | None = None
        self.bin_probs: np.ndarray | None = None

    def fit(self, y_pred: np.ndarray, y_true: np.ndarray) -> "BinnedProbabilityCalibrator":
        y_pred = np.clip(np.asarray(y_pred, dtype=float), 0.0, 1.0)
        y_true = np.asarray(y_true, dtype=float)

        bins = np.linspace(0.0, 1.0, self.n_bins + 1)
        self.bin_edges = bins
        self.bin_probs = np.zeros(self.n_bins, dtype=float)

        if y_pred.size == 0:
            return self

        for i in range(self.n_bins):
            if i == self.n_bins - 1:
                mask = (y_pred >= bins[i]) & (y_pred <= bins[i + 1])
            else:
                mask = (y_pred >= bins[i]) & (y_pred < bins[i + 1])

            if np.any(mask):
                self.bin_probs[i] = float(np.mean(y_true[mask]))
            else:
                self.bin_probs[i] = float((bins[i] + bins[i + 1]) / 2.0)

        return self

    def predict(self, y_pred: np.ndarray) -> np.ndarray:
        y_pred = np.clip(np.asarray(y_pred, dtype=float), 0.0, 1.0)

        if self.bin_edges is None or self.bin_probs is None:
            return y_pred

        calibrated = np.zeros_like(y_pred, dtype=float)

        for i in range(self.n_bins):
            if i == self.n_bins - 1:
                mask = (y_pred >= self.bin_edges[i]) & (y_pred <= self.bin_edges[i + 1])
            else:
                mask = (y_pred >= self.bin_edges[i]) & (y_pred < self.bin_edges[i + 1])

            calibrated[mask] = self.bin_probs[i]

        return calibrated

    def as_dict(self) -> dict[str, Any]:
        return {
            "calibrator_type": "binned_probability",
            "bins": int(self.bins),
            "bin_edges": [] if self.bin_edges is None else [float(x) for x in self.bin_edges],
            "bin_probs": [] if self.bin_probs is None else [float(x) for x in self.bin_probs],
        }
