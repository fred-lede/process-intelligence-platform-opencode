"""Experiment recommendation based on model analysis."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from process_intelligence_engine.modeling.fitters import ModelFit


def recommend_experiments(
    fit: ModelFit,
    df: pd.DataFrame,
    interactions: dict,
    validation: dict,
    n_recommendations: int = 5,
) -> dict[str, Any]:
    """Recommend next experiments based on model analysis."""
    recommendations = []

    # 1. Check for strong interactions
    significant_pairs = interactions.get("significant_pairs", [])
    for pair in significant_pairs:
        if pair.get("strength", 0) > 0.3:
            factor_a, factor_b = pair["i"], pair["j"]
            range_a = (df[factor_a].max() - df[factor_a].min()) / 2
            range_b = (df[factor_b].max() - df[factor_b].min()) / 2
            center_a = df[factor_a].mean()
            center_b = df[factor_b].mean()

            recommendations.append({
                "type": "interaction",
                "priority": "high" if pair["strength"] > 0.5 else "medium",
                "factors": [factor_a, factor_b],
                "strength": pair["strength"],
                "settings": [
                    {factor_a: center_a - range_a, factor_b: center_b - range_b},
                    {factor_a: center_a + range_a, factor_b: center_b + range_b},
                ],
                "key": "recInteraction",
            })

    # 2. Check residual normality
    stats = validation.get("stats", {})
    skewness = stats.get("skewness", 0)
    if abs(skewness) > 1:
        recommendations.append({
            "type": "transformation",
            "priority": "medium",
            "factors": [fit.target],
            "method": "log" if skewness > 0 else "sqrt",
            "skewness": skewness,
            "key": "recTransformationRightSkewed" if skewness > 0 else "recTransformationLeftSkewed",
        })

    # 3. Check for heteroscedasticity (simplified)
    residuals = validation.get("residuals", [])
    if len(residuals) > 10 and fit.inputs:
        sorted_indices = np.argsort(df[fit.inputs[0]])
        chunk_size = len(residuals) // 4
        if chunk_size > 0:
            var_quarters = [
                np.var(residuals[i * chunk_size:(i + 1) * chunk_size])
                for i in range(4)
            ]
            if max(var_quarters) > 3 * min(var_quarters):
                factor = fit.inputs[0]
                recommendations.append({
                    "type": "range_expansion",
                    "priority": "medium",
                    "factors": [factor],
                    "corr": float(np.corrcoef(df[factor], residuals)[0, 1]) if len(residuals) > 1 else 0.0,
                    "key": "recRangeExpansion",
                })

    # 4. If few recommendations, suggest replicates
    if len(recommendations) < 2:
        recommendations.append({
            "type": "replicate",
            "priority": "low",
            "factors": [],
            "key": "recReplicate",
        })

    # 5. Suggest new factor exploration if needed
    if len(recommendations) < n_recommendations:
        recommendations.append({
            "type": "new_factor",
            "priority": "low",
            "factors": [],
            "key": "recNewFactor",
        })

    # Generate summary (use first rec's key for display)
    if recommendations:
        first = recommendations[0]
        summary = f"{first['key']}: {first.get('factors', [])}"
    else:
        summary = "Model analysis complete. No critical issues detected."

    return {
        "recommendations": recommendations[:n_recommendations],
        "summary": summary,
    }
