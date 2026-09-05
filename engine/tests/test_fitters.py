"""Tests for DOE / AI / hybrid model fitting."""
import numpy as np
import pandas as pd
import pytest

from process_intelligence_engine.modeling.fitters import (
    fit_doe_linear,
    fit_doe_quadratic,
    fit_random_forest,
    fit_residual_hybrid,
    fit_xgboost,
    fit_lightgbm,
)


def _simple_df(n=100, seed=3):
    rng = np.random.default_rng(seed)
    x1 = rng.uniform(0, 1, n)
    x2 = rng.uniform(0, 1, n)
    y = 2.0 + 3.0 * x1 - 4.0 * x2 + rng.normal(0, 0.01, n)
    return pd.DataFrame({"x1": x1, "x2": x2, "y": y})


def test_fit_doe_linear_recovers_coefficients():
    df = _simple_df()
    fit = fit_doe_linear(df, target="y", inputs=["x1", "x2"])
    assert fit.model_type == "doe_linear"
    assert fit.metrics["r2"] > 0.95
    # y = 2 + 3 x1 - 4 x2 approximate
    c = fit.coefficients
    assert abs(c.get("x1", 0) - 3.0) < 0.5
    assert abs(c.get("x2", 0) + 4.0) < 0.5
    assert "1" not in c
    assert abs(c.get("_intercept", 0) - 2.0) < 0.5
    assert fit.equation
    assert fit.direction is None  # regression has no directional encoding


def test_fit_doe_quadratic_captures_squared_term():
    rng = np.random.default_rng(5)
    n = 200
    x = rng.uniform(0, 2, n)
    y = 1.0 + 2.0 * x + 0.8 * x ** 2 + rng.normal(0, 0.05, n)
    df = pd.DataFrame({"x": x, "y": y})
    fit = fit_doe_quadratic(df, target="y", inputs=["x"])
    assert fit.model_type == "doe_quadratic"
    assert fit.metrics["r2"] > 0.9
    # Coefficients keyed by python expression
    assert any("x^2" in k or "**2" in k for k in fit.coefficients)


def test_quadratic_requires_at_least_one_input():
    df = _simple_df(n=20)
    with pytest.raises(ValueError):
        fit_doe_quadratic(df, target="y", inputs=[])


def test_fit_random_forest_trains_and_scores():
    df = _simple_df(n=200)
    fit = fit_random_forest(df, target="y", inputs=["x1", "x2"], test_size=0.3, random_state=7)
    assert fit.model_type == "random_forest"
    assert fit.metrics["r2"] > 0.8
    assert fit.n_train + fit.n_test > 0
    assert fit.coefficients is None  # RF has no linear coefficients


def test_residual_hybrid_fit_is_better_than_linear_alone():
    # Non-linear term the linear model misses; RF residual should recover it.
    rng = np.random.default_rng(9)
    n = 300
    x = rng.uniform(0, 1, n)
    y = 1.0 + 2.0 * x + np.sin(10 * x) + rng.normal(0, 0.02, n)
    df = pd.DataFrame({"x": x, "y": y})
    hybrid = fit_residual_hybrid(df, target="y", inputs=["x"], random_state=11)
    assert hybrid.model_type == "residual_hybrid"
    assert hybrid.metrics["r2"] > 0.9


def test_fit_dto_is_json_serializable():
    import json

    df = _simple_df(n=80)
    fit = fit_doe_linear(df, target="y", inputs=["x1", "x2"])
    payload = json.dumps(fit.to_dto())
    assert payload


def test_fit_random_forest_auto_select_features():
    """Test auto feature selection returns fewer features when some are noise."""
    rng = np.random.default_rng(42)
    n = 200
    x1 = rng.uniform(0, 1, n)
    x2 = rng.uniform(0, 1, n)
    noise = rng.uniform(0, 1, n)
    y = 2.0 + 3.0 * x1 - 4.0 * x2 + rng.normal(0, 0.01, n)
    df = pd.DataFrame({"x1": x1, "x2": x2, "noise": noise, "y": y})

    fit = fit_random_forest(df, target="y", inputs=["x1", "x2", "noise"], auto_select_features=True)
    assert fit.selected_inputs is not None
    assert len(fit.selected_inputs) <= 2
    assert "noise" not in fit.selected_inputs


def test_fit_random_forest_hyperparameters():
    """Test hyperparameter exposure."""
    df = _simple_df(n=200)
    fit = fit_random_forest(df, target="y", inputs=["x1", "x2"], n_estimators=50, max_depth=5)
    assert fit.model is not None
    assert fit.metrics["r2"] > 0.5


def test_fit_random_forest_all_features_below_threshold():
    """Test that ValueError is raised when all features are filtered out."""
    rng = np.random.default_rng(42)
    n = 200
    noise1 = rng.uniform(0, 1, n)
    noise2 = rng.uniform(0, 1, n)
    y = rng.normal(0, 1, n)  # no signal from inputs
    df = pd.DataFrame({"noise1": noise1, "noise2": noise2, "y": y})
    
    # With very high threshold, all features should be filtered
    with pytest.raises(ValueError, match="at least one input"):
        fit_random_forest(df, target="y", inputs=["noise1", "noise2"], auto_select_features=True, importance_threshold=0.9)


def test_fit_xgboost_trains_and_scores():
    df = _simple_df(n=200)
    fit = fit_xgboost(df, target="y", inputs=["x1", "x2"])
    assert fit.model_type == "xgboost"
    assert fit.metrics["r2"] > 0.8


def test_fit_lightgbm_trains_and_scores():
    df = _simple_df(n=200)
    fit = fit_lightgbm(df, target="y", inputs=["x1", "x2"])
    assert fit.model_type == "lightgbm"
    assert fit.metrics["r2"] > 0.8


def test_fit_xgboost_auto_select():
    rng = np.random.default_rng(42)
    n = 200
    x1 = rng.uniform(0, 1, n)
    x2 = rng.uniform(0, 1, n)
    noise = rng.uniform(0, 1, n)
    y = 2.0 + 3.0 * x1 - 4.0 * x2 + rng.normal(0, 0.01, n)
    df = pd.DataFrame({"x1": x1, "x2": x2, "noise": noise, "y": y})

    fit = fit_xgboost(df, target="y", inputs=["x1", "x2", "noise"], auto_select_features=True)
    assert "noise" not in fit.selected_inputs
