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
        if target_vals.nunique() == 2:
            counts = target_vals.value_counts()
            if len(counts) == 2:
                ratio = counts.max() / max(counts.min(), 1)
                if ratio > 4:
                    warnings.append(f"Class imbalance detected (ratio {ratio:.1f}:1), logistic regression may be unreliable")

    for col in inputs:
        if col in df.columns and df[col].nunique() == 1:
            warnings.append(f"Column {col} is constant; review before fitting")

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
    if not ai_pred or not doe_pred or len(ai_pred) != len(doe_pred):
        raise ValueError("Comparison requires non-empty, equally sized predictions")
    if not np.isfinite(scale) or scale <= 0 or not np.all(np.isfinite(ai_pred + doe_pred)):
        raise ValueError("Comparison requires finite predictions and a positive scale")

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

    if not is_binary_target and n_samples >= 100 and not need_interpretability:
        recommendations.append("random_forest")

    return recommendations


def compute_experiment_verdict(
    predicted: float,
    actual: float,
    tolerance: float | None = None,
    spec_range: float | None = None,
    rmse: float | None = None,
    is_classification: bool = False,
    accuracy: float | None = None,
    recall: float | None = None,
    target_recall: float = 0.90,
) -> str:
    """Compute experiment verdict with adaptive tolerance.

    When ``tolerance`` is not provided, it is derived from the smaller of:
    - half the specification range (``spec_range / 2``)
    - 2× the model RMSE (prediction-interval proxy)

    For classification experiments pass ``is_classification=True`` together
    with ``accuracy`` and ``recall``.
    """
    if is_classification:
        if accuracy is None or recall is None:
            return "insufficient_data"
        if not all(np.isfinite(v) and 0 <= v <= 1 for v in (accuracy, recall, target_recall)):
            raise ValueError("Classification metrics must be probabilities")
        acc_pass = accuracy >= 0.80
        rec_pass = recall >= target_recall
        if acc_pass and rec_pass:
            return "supports"
        if acc_pass or rec_pass:
            return "partially_supports"
        if recall < target_recall * 0.5:
            return "needs_remodel"
        return "does_not_support"

    if tolerance is not None and (not np.isfinite(tolerance) or tolerance <= 0):
        raise ValueError("tolerance must be finite and positive")
    if not np.isfinite(predicted) or not np.isfinite(actual):
        raise ValueError("Experiment outputs must be finite")
    if tolerance is None:
        parts: list[float] = []
        if spec_range is not None and spec_range > 0:
            parts.append(spec_range * 0.5)
        if rmse is not None and rmse > 0:
            parts.append(2.0 * rmse)
        if not parts:
            return "insufficient_data"
        else:
            tolerance = min(parts)

    abs_error = abs(actual - predicted)
    ratio = abs_error / max(tolerance, 1e-12)
    if ratio <= 0.5:
        return "supports"
    elif ratio <= 1.0:
        return "partially_supports"
    elif ratio <= 2.0:
        return "does_not_support"
    else:
        return "needs_remodel"


def compute_prediction_interval(
    predicted: float,
    rmse: float,
    n: int,
    confidence: float = 0.95,
) -> dict:
    """Return a prediction interval for a continuous prediction."""
    import math
    if n < 4 or rmse <= 0:
        return {"lower": predicted, "upper": predicted, "width": 0}
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1")
    from scipy.stats import t
    # Approximation assumes independent residuals and n-1 residual degrees of freedom.
    z = float(t.ppf((1 + confidence) / 2, df=n - 1))
    sem = rmse * math.sqrt(1 + 1.0 / n)
    half_width = z * sem
    return {
        "predicted": predicted,
        "lower": round(predicted - half_width, 6),
        "upper": round(predicted + half_width, 6),
        "half_width": round(half_width, 6),
        "confidence": confidence,
    }


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
    if not inputs or df is None or len(df) == 0:
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

    center = {col: s["mean"] for col, s in input_stats.items()}
    # Complete executable settings; vary one factor while holding others fixed.
    for col, stats in input_stats.items():
        suggestions.append({
            "condition": {**center, col: stats["low"]},
            "rationale": "low_boundary",
        })
        suggestions.append({
            "condition": {**center, col: stats["high"]},
            "rationale": "high_boundary",
        })

    # Always suggest center point
    center = {col: (s["low"] + s["high"]) / 2 for col, s in input_stats.items()}
    suggestions.append({"condition": center, "rationale": "center_point"})
    estimators = getattr(model.model, "estimators_", None)
    if estimators is not None and len(estimators):
        candidates = np.array([[s["condition"][col] for col in inputs] for s in suggestions])
        predictions = np.array([tree.predict(candidates) for tree in estimators])
        spread = predictions.std(axis=0)
        for suggestion, score in zip(suggestions, spread):
            suggestion["rationale"] = "ensemble_disagreement (heuristic, not a calibrated interval)"
            suggestion["score"] = float(score)
        suggestions.sort(key=lambda s: s["score"], reverse=True)
    return suggestions[:max(1, min(int(n_suggestions), 20))]
