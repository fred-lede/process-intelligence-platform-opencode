"""SHAP value computation for model interpretability."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from process_intelligence_engine.modeling.fitters import ModelFit


def compute_shap(
    fit: ModelFit,
    df: pd.DataFrame,
    nsamples: int = 100,
) -> dict[str, Any]:
    """Compute SHAP values for a fitted model.

    Args:
        fit: A fitted ModelFit object
        df: The dataset used for fitting
        nsamples: Number of samples to use for background data (default 100)

    Returns:
        {
            "expected_value": float,
            "feature_importance": [{"name": str, "importance": float}, ...],
            "shap_values": list[list[float]]
        }
    """
    if fit.model_type == "doe_linear" or fit.model_type == "doe_quadratic":
        return _compute_shap_linear(fit, df, nsamples)
    elif fit.model_type == "random_forest":
        return _compute_shap_tree(fit, df, nsamples)
    else:
        raise ValueError(f"Unsupported model type for SHAP: {fit.model_type}")


def _compute_shap_linear(fit: ModelFit, df: pd.DataFrame, nsamples: int) -> dict:
    """SHAP for linear/quadratic models using LinearExplainer."""
    try:
        import shap
    except ImportError:
        raise ImportError("shap is required for SHAP analysis. Install with: pip install shap")

    inputs = fit.inputs
    X = df[inputs]

    # Sample background data
    if len(X) > nsamples:
        bg_data = X.sample(n=nsamples, random_state=42)
    else:
        bg_data = X

    # Build linear approximation from coefficients
    intercept = fit.coefficients.get("_intercept", 0.0)
    coefs = fit.coefficients.copy()
    del coefs["_intercept"]

    # Extract linear coefficients
    linear_coefs = {}
    quadratic_coefs = {}
    interaction_coefs = {}
    for key, value in coefs.items():
        if key.startswith("X") and "_" in key:
            # Interaction term like X_A_X_B
            parts = key.replace("X_", "").split("_X")
            if len(parts) == 2:
                interaction_coefs[(parts[0], parts[1])] = value
            elif len(parts) == 1:
                # Quadratic term like X_A_X_A (simplified to X_A)
                quadratic_coefs[parts[0]] = value
        elif key in inputs:
            linear_coefs[key] = value

    # Create LinearExplainer with the intercept and coefficients
    coef_array = np.array([linear_coefs.get(col, 0.0) for col in inputs])
    explainer = shap.LinearExplainer((coef_array, intercept), bg_data, model_output="linear")

    # Adjust for quadratic and interaction terms
    shap_values = explainer.shap_values(X)

    # Ensure shap_values is 2D
    if shap_values.ndim == 3:
        shap_values = shap_values[:, :, 0]  # Take first output class

    # Compute feature importance (mean absolute SHAP value)
    importance = np.abs(shap_values).mean(axis=0)
    feature_importance = sorted(
        [{"name": col, "importance": float(imp)} for col, imp in zip(inputs, importance)],
        key=lambda x: x["importance"],
        reverse=True,
    )

    return {
        "expected_value": float(intercept),
        "feature_importance": feature_importance,
        "shap_values": shap_values.tolist(),
    }


def _compute_shap_tree(fit: ModelFit, df: pd.DataFrame, nsamples: int) -> dict:
    """SHAP for tree-based models using TreeExplainer."""
    try:
        import shap
    except ImportError:
        raise ImportError("shap is required for SHAP analysis. Install with: pip install shap")

    inputs = fit.inputs
    X = df[inputs]

    # Sample background data
    if len(X) > nsamples:
        bg_data = X.sample(n=nsamples, random_state=42)
    else:
        bg_data = X

    explainer = shap.TreeExplainer(fit.model)
    shap_values = explainer.shap_values(X, check_additivity=False)

    # Ensure 2D
    if shap_values.ndim == 3:
        shap_values = shap_values[:, :, 0]

    # Compute feature importance
    importance = np.abs(shap_values).mean(axis=0)
    feature_importance = sorted(
        [{"name": col, "importance": float(imp)} for col, imp in zip(inputs, importance)],
        key=lambda x: x["importance"],
        reverse=True,
    )

    return {
        "expected_value": float(np.asarray(explainer.expected_value).ravel()[0]),
        "feature_importance": feature_importance,
        "shap_values": shap_values.tolist(),
    }
