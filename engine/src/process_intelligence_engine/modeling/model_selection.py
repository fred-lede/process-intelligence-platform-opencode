"""Model comparison and selection using cross-validation."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .fitters import ModelFit
from .validation import cross_validate, analyze_residuals


def compare_models(
    fits: list[ModelFit],
    df: pd.DataFrame,
    k: int = 5,
) -> dict[str, Any]:
    """Compare multiple fitted models using cross-validation.

    Returns ranking based on CV metrics and residual normality.
    """
    models = []
    skipped = []

    for fit in fits:
        try:
            cv_result = cross_validate(fit, df, k)
            residual_result = analyze_residuals(fit, df)

            mean_r2 = cv_result["mean_metrics"]["mean_r2"]
            mean_rmse = cv_result["mean_metrics"]["mean_rmse"]
            residual_normal = residual_result["normality_test"]["is_normal"]
            cv_r2_vals = [r["r2"] for r in cv_result["cv_results"]]
            cv_std = float(np.std(cv_r2_vals)) if len(cv_r2_vals) > 1 else 0.0
            score = float(mean_r2) - (0.1 if not residual_normal else 0.0) - 0.05 * cv_std
            models.append({
                "model_id": fit.model_id,
                "model_type": fit.model_type,
                "cv_metrics": {"mean_r2": float(mean_r2), "mean_rmse": float(mean_rmse)},
                "residual_normal": residual_normal,
                "score": score,
            })
        except (ValueError, TypeError, KeyError) as exc:
            skipped.append({"model_id": fit.model_id, "reason": str(exc)})

    # Sort by score descending
    models.sort(key=lambda x: x["score"], reverse=True)
    ranking = [m["model_id"] for m in models]

    return {
        "models": models,
        "best_model_id": ranking[0] if ranking else None,
        "ranking": ranking,
        "skipped": skipped,
    }
