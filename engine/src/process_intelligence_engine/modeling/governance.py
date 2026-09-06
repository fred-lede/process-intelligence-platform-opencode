"""Model governance: applicability checks, DOE vs AI comparison, model recommendation."""
from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Any


def check_model_applicability(
    df: pd.DataFrame,
    target: str,
    inputs: list[str],
    is_binary: bool = False,
) -> list[str]:
    """Run pre-fit applicability checks. Returns list of warning strings."""
    warnings = []
    n = len(df)

    if n < 30:
        warnings.append(f"Sample size insufficient ({n} < 30), tree models not recommended")

    if is_binary:
        target_vals = df[target]
        if target_vals.dtype == 'object' or pd.api.types.is_string_dtype(target_vals):
            counts = target_vals.value_counts()
            if len(counts) == 2:
                ratio = counts.max() / max(counts.min(), 1)
                if ratio > 4:
                    warnings.append(f"Class imbalance detected (ratio {ratio:.1f}:1), logistic regression may be unreliable")

    for col in inputs:
        if col in df.columns and df[col].nunique() == 1:
            warnings.append(f"Column {col} is constant, will be excluded")

    if len(inputs) >= 2:
        try:
            X = df[inputs].apply(pd.to_numeric, errors='coerce')
            X = X.dropna()
            if len(X) >= 10:
                from sklearn.linear_model import LinearRegression
                for i, col_i in enumerate(inputs):
                    if col_i not in X.columns:
                        continue
                    others = [c for c in inputs if c != col_i and c in X.columns]
                    if others:
                        lr = LinearRegression()
                        lr.fit(X[others], X[col_i])
                        r2 = lr.score(X[others], X[col_i])
                        vif = 1 / (1 - r2) if r2 < 0.999 else float('inf')
                        if vif > 10:
                            warnings.append(f"Multicollinearity warning: {col_i} highly correlated with others (VIF={vif:.1f})")
        except Exception:
            pass

    return warnings


def check_doeb_ai_discrepancy(
    doe_r2: float,
    ai_r2: float,
    ai_pred: list[float],
    doe_pred: list[float],
    scale: float,
    mean_threshold: float = 0.15,
    max_threshold: float = 0.30,
) -> dict:
    """Check if DOE and AI predictions differ significantly."""
    if not ai_pred or not doe_pred:
        return {"needs_review": False, "recommendation": "Cannot compare: missing prediction data"}

    normalized_diff = [
        abs(a - b) / max(scale, 1e-12)
        for a, b in zip(ai_pred, doe_pred)
    ]
    max_diff = max(normalized_diff)
    mean_diff = sum(normalized_diff) / len(normalized_diff)

    needs_review = max_diff > max_threshold or mean_diff > mean_threshold

    return {
        "needs_review": needs_review,
        "max_difference": round(max_diff, 4),
        "mean_difference": round(mean_diff, 4),
        "doe_r2": doe_r2,
        "ai_r2": ai_r2,
        "recommendation": (
            "Manual review required, default to DOE as conservative baseline"
            if needs_review else "AI model can proceed to validation"
        ),
    }


def recommend_models(
    n_samples: int,
    n_features: int,
    is_binary_target: bool,
    has_nonlinearity: bool,
    need_interpretability: bool,
) -> list[str]:
    """Recommend suitable model types based on data characteristics."""
    recommendations = []

    if is_binary_target:
        recommendations.append("logistic_regression")
        if n_samples >= 100:
            recommendations.append("xgboost")
    else:
        if n_samples < 50:
            recommendations.append("doe_linear")
            if n_features >= 2:
                recommendations.append("doe_quadratic")
        elif n_samples < 200:
            recommendations.append("doe_quadratic")
            if has_nonlinearity:
                recommendations.append("residual_hybrid")
        else:
            if need_interpretability:
                recommendations.append("doe_linear")
                recommendations.append("residual_hybrid")
            else:
                recommendations.append("xgboost")
                recommendations.append("lightgbm")

    if n_samples >= 100 and not need_interpretability:
        recommendations.append("random_forest")

    return recommendations
