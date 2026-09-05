"""Prediction engine for DOE, logistic, and Weibull models."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

SUPPORTED_MODELS = {"doe_linear", "doe_quadratic", "logistic_regression", "weibull_regression"}

_COEFF_RENAMES = {
    "x1x2": "x1_x_x2",
    "x1x1": "x1_x_x1",
    "x2x2": "x2_x_x2",
}


def predict_single(model_type: str, coefficients: dict[str, float], inputs: dict[str, float]) -> float:
    """Predict output using model coefficients.

    Args:
        model_type: one of "doe_linear", "doe_quadratic", "logistic_regression", "weibull_regression"
        coefficients: dict with keys like "_intercept", "x1", "x2",
                      "x1_x_x2", "x1_x_x1" (also accepts compact "x1x2", "x1x1")
                      For logistic: plain coefficients; For weibull: "_weibull_shape" key
        inputs: dict mapping factor names to their values

    Returns:
        Predicted output value (probability for logistic, mean TTF for weibull)

    Raises:
        ValueError: if model_type is not supported
    """
    if model_type not in SUPPORTED_MODELS:
        raise ValueError(
            f"Unsupported model type: {model_type!r}. "
            f"Expected one of {sorted(SUPPORTED_MODELS)}."
        )

    # Normalize coefficient keys (compact → spaced form)
    normed = {**_COEFF_RENAMES, **coefficients}

    if model_type in ("doe_linear", "doe_quadratic"):
        result = float(normed.get("_intercept", 0.0))
        for name, value in inputs.items():
            coef = normed.get(name, 0.0)
            result += coef * value
            if model_type == "doe_quadratic":
                sq_key = f"{name}_x_{name}"
                coef_sq = normed.get(sq_key, 0.0)
                result += coef_sq * value * value
                for other_name in inputs:
                    if other_name == name:
                        continue
                    inter_key = f"{name}_x_{other_name}"
                    coef_inter = normed.get(inter_key, 0.0)
                    result += coef_inter * value * inputs[other_name]
        return float(result)

    if model_type == "logistic_regression":
        logit = float(normed.get("_intercept", 0.0))
        for name, value in inputs.items():
            logit += float(normed.get(name, 0.0)) * value
        return 1.0 / (1.0 + math.exp(-logit))

    if model_type == "weibull_regression":
        intercept = float(normed.get("_intercept", 0.0))
        k = float(normed.get("_weibull_shape", 1.0))
        log_lambda = intercept
        for name, value in inputs.items():
            log_lambda += float(normed.get(name, 0.0)) * value
        log_lambda = max(min(log_lambda, 700.0), -700.0)
        lambda_val = float(np.exp(log_lambda))
        from scipy.special import gamma
        return float(lambda_val * gamma(1.0 + 1.0 / k))

    raise ValueError(f"Unhandled model type: {model_type}")


def get_input_ranges(df: pd.DataFrame, input_columns: list[str]) -> dict[str, dict[str, float]]:
    """Return min, max, mean, std for each input column.

    Args:
        df: pandas DataFrame containing the data
        input_columns: list of column names to analyze

    Returns:
        dict mapping column name → {"min", "max", "mean", "std"}
    """
    ranges: dict[str, dict[str, float]] = {}
    for col in input_columns:
        series = df[col]
        if len(series) == 0:
            ranges[col] = {"min": 0.0, "max": 0.0, "mean": 0.0, "std": 0.0}
        else:
            ranges[col] = {
                "min": float(series.min()),
                "max": float(series.max()),
                "mean": float(series.mean()),
                "std": float(series.std()),
            }
    return ranges
