"""Prediction engine for DOE models."""
from typing import Any

import numpy as np
import pandas as pd

SUPPORTED_MODELS = {"doe_linear", "doe_quadratic"}

_COEFF_RENAMES = {
    "x1x2": "x1_x_x2",
    "x1x1": "x1_x_x1",
    "x2x2": "x2_x_x2",
}


def predict_single(model_type: str, coefficients: dict[str, float], inputs: dict[str, float]) -> float:
    """Predict a single output value using DOE model coefficients.

    Args:
        model_type: "doe_linear" or "doe_quadratic"
        coefficients: dict with keys like "_intercept", "x1", "x2",
                      "x1_x_x2", "x1_x_x1" (also accepts compact "x1x2", "x1x1")
        inputs: dict mapping factor names to their values

    Returns:
        Predicted output value

    Raises:
        ValueError: if model_type is not supported
    """
    if model_type not in SUPPORTED_MODELS:
        raise ValueError(f"Unsupported model type: {model_type!r}. "
                         f"Expected one of {sorted(SUPPORTED_MODELS)}.")

    # Normalize coefficient keys (compact → spaced form)
    normed = {}
    for k, v in coefficients.items():
        normed[_COEFF_RENAMES.get(k, k)] = v

    result = float(normed.get("_intercept", 0.0))

    for name, value in inputs.items():
        # linear term: key is just the factor name (e.g. "x1")
        coef = normed.get(name, 0.0)
        result += coef * value

        if model_type == "doe_quadratic":
            # squared term: "x1_x_x1"
            sq_key = f"{name}_x_{name}"
            coef_sq = normed.get(sq_key, 0.0)
            result += coef_sq * value * value

            # interaction terms: "x1_x_x2"
            for other_name in inputs:
                if other_name == name:
                    continue
                inter_key = f"{name}_x_{other_name}"
                coef_inter = normed.get(inter_key, 0.0)
                result += coef_inter * value * inputs[other_name]

    return float(result)


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
