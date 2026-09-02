"""Tests for SHAP explainer."""
import numpy as np
import pandas as pd
import pytest

from process_intelligence_engine.modeling.shap_explainer import compute_shap
from process_intelligence_engine.modeling.fitters import fit_doe_quadratic, fit_random_forest


def _make_df(n=100):
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "A": rng.uniform(-1, 1, n),
        "B": rng.uniform(-1, 1, n),
        "C": rng.uniform(-1, 1, n),
    })
    df["Y"] = 2.0 + 3.0 * df["A"] - 2.0 * df["B"] + 5.0 * df["A"] * df["B"] + 0.1 * df["C"] + rng.normal(0, 0.01, n)
    return df


def test_shap_linear_importance():
    df = _make_df()
    fit = fit_doe_quadratic(df, target="Y", inputs=["A", "B", "C"])
    result = compute_shap(fit, df)
    assert result["expected_value"] is not None
    assert len(result["feature_importance"]) == 3
    # Check sorted by importance descending
    assert result["feature_importance"][0]["importance"] >= result["feature_importance"][1]["importance"]
    # SHAP values shape matches (n_samples, n_features)
    assert len(result["shap_values"]) == len(df)
    assert len(result["shap_values"][0]) == 3


def test_shap_random_forest():
    df = _make_df()
    fit = fit_random_forest(df, target="Y", inputs=["A", "B", "C"])
    result = compute_shap(fit, df)
    assert result["expected_value"] is not None
    assert len(result["feature_importance"]) == 3
    assert abs(sum(result["shap_values"][0])) - abs(result["expected_value"] - df["Y"].iloc[0]) < 0.5


def test_shap_unknown_model_raises():
    df = _make_df()
    # Create a mock fit with unsupported model type
    class MockFit:
        model_type = "unsupported"
        inputs = ["A"]
        model = None
    with pytest.raises(ValueError, match="Unsupported model"):
        compute_shap(MockFit(), df)
