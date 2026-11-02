"""Served flood model whose probabilities are isotonic-calibrated on the validation block."""

from __future__ import annotations

import numpy as np


class CalibratedFloodModel:
    """Estimator scores mapped to empirical flood frequencies.

    The calibrator is fit only on the chronological validation block. predict_proba
    returns that calibrated flood chance in column 1.
    """

    def __init__(self, model, calibrator):
        self.model = model
        self.calibrator = calibrator

    def predict_proba(self, features):
        raw = np.asarray(self.model.predict_proba(features)[:, 1], dtype=float)
        calibrated = np.clip(np.asarray(self.calibrator.predict(raw), dtype=float), 0.0, 1.0)
        return np.column_stack([1.0 - calibrated, calibrated])

    def predict(self, features):
        return (self.predict_proba(features)[:, 1] >= 0.5).astype(int)
