"""Two-factor interaction strength computation."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from process_intelligence_engine.modeling.fitters import ModelFit


def _predict_from_fit(fit: ModelFit, row_dict: dict) -> float:
    """Predict Y for a single row dict using fitted coefficients."""
    y = float(fit.coefficients.get("_intercept", 0.0))
    for col in fit.inputs:
        coef_key = col
        if coef_key in fit.coefficients:
            y += fit.coefficients[coef_key] * float(row_dict.get(col, 0.0))
        sq_key = f"{col}^2"
        if sq_key in fit.coefficients:
            y += fit.coefficients[sq_key] * float(row_dict.get(col, 0.0)) ** 2
    n = len(fit.inputs)
    for i in range(n):
        for j in range(i + 1, n):
            pair_key = f"{fit.inputs[i]}*{fit.inputs[j]}"
            if pair_key in fit.coefficients:
                y += (
                    fit.coefficients[pair_key]
                    * float(row_dict.get(fit.inputs[i], 0.0))
                    * float(row_dict.get(fit.inputs[j], 0.0))
                )
    return y


def compute_interactions(
    fit: ModelFit,
    df: pd.DataFrame,
    threshold: float = 0.01,
) -> dict[str, Any]:
    """Compute two-factor interaction strengths for a fitted model."""
    inputs = fit.inputs
    n = len(inputs)
    if n < 2:
        return {"factors": inputs, "matrix": [[0.0]], "significant_pairs": []}

    means = {col: df[col].mean() for col in inputs}

    base_row = {col: means[col] for col in inputs}
    y_base = _predict_from_fit(fit, base_row)

    matrix = [[0.0] * n for _ in range(n)]
    significant_pairs = []

    for i in range(n):
        for j in range(i + 1, n):
            col_i, col_j = inputs[i], inputs[j]

            strengths = []
            for _, sample in df.iterrows():
                row_both = base_row.copy()
                row_both[col_i] = sample[col_i]
                row_both[col_j] = sample[col_j]
                y_both = _predict_from_fit(fit, row_both)

                row_i = base_row.copy()
                row_i[col_i] = sample[col_i]
                y_i = _predict_from_fit(fit, row_i)

                row_j = base_row.copy()
                row_j[col_j] = sample[col_j]
                y_j = _predict_from_fit(fit, row_j)

                interaction = y_both - y_i - y_j + y_base
                strengths.append(abs(interaction))

            avg_strength = float(np.mean(strengths))
            matrix[i][j] = avg_strength
            matrix[j][i] = avg_strength

            significant_pairs.append({
                "i": col_i,
                "j": col_j,
                "strength": avg_strength,
                "significant": avg_strength >= threshold,
            })

    significant_pairs.sort(key=lambda x: x["strength"], reverse=True)

    return {
        "factors": inputs,
        "matrix": matrix,
        "significant_pairs": significant_pairs,
    }
