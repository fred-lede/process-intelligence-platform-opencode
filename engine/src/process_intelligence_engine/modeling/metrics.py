"""Regression comparison metrics (all JSON-native floats).

Shared by DOE / AI / hybrid models so comparisons use identical statistics.
"""

from __future__ import annotations

import numpy as np


def _pair(y_true, y_pred) -> tuple[np.ndarray, np.ndarray]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    if y_true.shape != y_pred.shape:
        raise ValueError("y_true and y_pred must have the same shape")
    return y_true, y_pred


def mean_squared_error(y_true, y_pred) -> float:
    y_true, y_pred = _pair(y_true, y_pred)
    return float(np.mean((y_true - y_pred) ** 2))


def root_mean_squared_error(y_true, y_pred) -> float:
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


def mean_absolute_error(y_true, y_pred) -> float:
    y_true, y_pred = _pair(y_true, y_pred)
    return float(np.mean(np.abs(y_true - y_pred)))


def r2_score(y_true, y_pred) -> float:
    y_true, y_pred = _pair(y_true, y_pred)
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    if ss_tot == 0:
        # Constant response: the mean-baseline is perfect (ss_tot = 0), so any
        # residual error is strictly worse than baseline and R² is undefined.
        # Return 1.0 for perfect fit, else a strong negative signal.
        return 1.0 if ss_res == 0 else -1.0
    return float(1.0 - ss_res / ss_tot)


def adjusted_r2(r2: float, n: int, p: int) -> float:
    """Wherry-McLaughlin adjusted R²; n = samples, p = feature count."""
    if n - p - 1 <= 0:
        return r2
    return float(1.0 - (1.0 - r2) * (n - 1) / (n - p - 1))