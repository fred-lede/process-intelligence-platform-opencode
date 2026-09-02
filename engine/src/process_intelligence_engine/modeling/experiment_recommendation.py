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
                "settings": [
                    {factor_a: center_a - range_a, factor_b: center_b - range_b},
                    {factor_a: center_a + range_a, factor_b: center_b + range_b},
                ],
                "reason": f"Strong {factor_a}×{factor_b} interaction (strength: {pair['strength']:.2f})",
            })

    # 2. Check residual normality
    stats = validation.get("stats", {})
    skewness = stats.get("skewness", 0)
    if abs(skewness) > 1:
        direction = "right" if skewness > 0 else "left"
        recommendations.append({
            "type": "transformation",
            "priority": "medium",
            "factors": [fit.target],
            "settings": [],
            "reason": f"Residuals are {direction}-skewed (skewness: {skewness:.2f}). Consider log/sqrt transformation.",
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
                    "settings": [],
                    "reason": f"Heteroscedasticity detected. Consider expanding {factor} range.",
                })

    # 4. If few recommendations, suggest replicates
    if len(recommendations) < 2:
        recommendations.append({
            "type": "replicate",
            "priority": "low",
            "factors": [],
            "settings": [],
            "reason": "Consider replicating center points to estimate pure error.",
        })

    # 5. Suggest new factor exploration if needed
    if len(recommendations) < n_recommendations:
        recommendations.append({
            "type": "new_factor",
            "priority": "low",
            "factors": [],
            "settings": [],
            "reason": "Unexplained variance may be due to missing factors. Consider adding new input variables.",
        })

    # Generate summary
    summary_parts = []
    for rec in recommendations[:3]:
        summary_parts.append(f"{rec['type']}: {rec['reason']}")
    summary = " | ".join(summary_parts) if summary_parts else "Model analysis complete. No critical issues detected."

    return {
        "recommendations": recommendations[:n_recommendations],
        "summary": summary,
    }
