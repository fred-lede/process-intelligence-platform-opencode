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


def compute_experiment_verdict(
    predicted: float,
    actual: float,
    tolerance: float = 0.1,
) -> str:
    """Compute experiment verdict based on prediction error."""
    abs_error = abs(actual - predicted)
    if abs_error <= tolerance * 0.5:
        return "supports"
    elif abs_error <= tolerance:
        return "partially_supports"
    elif abs_error <= tolerance * 2:
        return "does_not_support"
    else:
        return "needs_remodel"


def update_model_after_experiment(
    model_id: str,
    verdict: str,
    chain,
) -> dict:
    """Record experiment impact on model without auto-retiring."""
    from process_intelligence_engine.main import MODEL_REGISTRY
    try:
        model = MODEL_REGISTRY.get(model_id)
    except KeyError:
        return {"error": f"Unknown model_id: {model_id}"}

    if verdict in ("does_not_support", "needs_remodel"):
        claim_id = chain.add_claim(
            entity_id=model_id,
            claim_type="experiment_impact",
            text="Experiment result does not support current model, requires manual review",
            source_entity_ids=[],
            origin_source="user_override",
            evidence_status="experimentally_confirmed",
        )
        return {
            "model_id": model_id,
            "verdict": verdict,
            "action": "claim_created",
            "claim_id": claim_id,
            "message": "Model requires manual review before retirement",
        }
    return {"model_id": model_id, "verdict": verdict, "action": "none"}


def recommend_next_experiment(
    model_id: str,
    df,
    n_suggestions: int = 3,
) -> list[dict]:
    """Recommend next experiment conditions based on input ranges."""
    from process_intelligence_engine.main import MODEL_REGISTRY
    try:
        model = MODEL_REGISTRY.get(model_id)
    except KeyError:
        return []

    suggestions = []
    inputs = getattr(model, 'inputs', [])
    if not inputs or len(df) == 0:
        return suggestions

    # Get input ranges from data
    input_stats = {}
    for col in inputs:
        if col in df.columns:
            series = pd.to_numeric(df[col], errors='coerce').dropna()
            if len(series) > 0:
                input_stats[col] = {
                    "low": float(series.min()),
                    "high": float(series.max()),
                    "mean": float(series.mean()),
                }

    if not input_stats:
        return suggestions

    # Suggest boundary and center points
    for col, stats in input_stats.items():
        suggestions.append({
            "condition": {col: stats["low"]},
            "rationale": "low_boundary",
        })
        suggestions.append({
            "condition": {col: stats["high"]},
            "rationale": "high_boundary",
        })

    # Always suggest center point
    center = {col: (s["low"] + s["high"]) / 2 for col, s in input_stats.items()}
    suggestions.append({"condition": center, "rationale": "center_point"})

    return suggestions[:n_suggestions]
