"""Tests for validation and residual analysis."""
import numpy as np
import pandas as pd
import pytest

from process_intelligence_engine.modeling.validation import (
    cross_validate,
    analyze_residuals,
    recommend_experiments,
)
from process_intelligence_engine.modeling.fitters import fit_doe_linear, fit_doe_quadratic


def _make_df(n=100):
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "A": rng.uniform(0, 10, n),
        "B": rng.uniform(0, 10, n),
        "C": rng.uniform(0, 10, n),
    })
    df["Y"] = 2.0 + 3.0 * df["A"] - 2.0 * df["B"] + 0.5 * df["A"] * df["B"] + rng.normal(0, 0.5, n)
    return df


def test_cross_validate_returns_correct_structure():
    df = _make_df()
    fit = fit_doe_linear(df, target="Y", inputs=["A", "B", "C"])
    result = cross_validate(fit, df, k=5)
    
    assert "cv_results" in result
    assert "mean_metrics" in result
    assert len(result["cv_results"]) == 5
    for fold in result["cv_results"]:
        assert "fold" in fold
        assert "r2" in fold
        assert "rmse" in fold
    assert "mean_r2" in result["mean_metrics"]
    assert "mean_rmse" in result["mean_metrics"]


def test_cross_validate_r2_positive():
    df = _make_df()
    fit = fit_doe_linear(df, target="Y", inputs=["A", "B", "C"])
    result = cross_validate(fit, df, k=5)
    
    # R² should be positive for a decent linear fit
    assert result["mean_metrics"]["mean_r2"] > 0.5
    assert result["mean_metrics"]["mean_rmse"] < 8.0


def test_analyze_residuals_returns_structure():
    df = _make_df()
    fit = fit_doe_linear(df, target="Y", inputs=["A", "B", "C"])
    result = analyze_residuals(fit, df)
    
    assert "residuals" in result
    assert "stats" in result
    assert "normality_test" in result
    assert len(result["residuals"]) == len(df)
    assert result["stats"]["mean"] == pytest.approx(0.0, abs=0.1)
    assert result["stats"]["std"] > 0
    assert 0 <= result["normality_test"]["p_value"] <= 1


def test_recommend_experiments_returns_list():
    df = _make_df()
    fit = fit_doe_linear(df, target="Y", inputs=["A", "B", "C"])
    interactions = {"significant_pairs": [{"i": "A", "j": "B", "strength": 0.5}]}
    
    result = recommend_experiments(fit, df, interactions)
    
    assert isinstance(result, list)
    assert len(result) > 0
    for rec in result:
        assert "type" in rec
        assert "key" in rec


def test_recommend_experiments_detects_interaction():
    df = _make_df()
    fit = fit_doe_quadratic(df, target="Y", inputs=["A", "B", "C"])
    interactions = {"significant_pairs": [{"i": "A", "j": "B", "strength": 0.5}]}
    
    result = recommend_experiments(fit, df, interactions)
    
    # Should recommend exploring the A-B interaction
    interaction_recs = [r for r in result if r["type"] == "interaction"]
    assert len(interaction_recs) > 0


def test_analyze_residuals_qq_data():
    df = _make_df()
    fit = fit_doe_linear(df, target="Y", inputs=["A", "B", "C"])
    result = analyze_residuals(fit, df)

    assert "qq_data" in result
    assert "theoretical_quantiles" in result["qq_data"]
    assert "sample_quantiles" in result["qq_data"]
    assert len(result["qq_data"]["theoretical_quantiles"]) == len(df)
    assert len(result["qq_data"]["sample_quantiles"]) == len(df)


def test_analyze_residuals_vs_predicted():
    df = _make_df()
    fit = fit_doe_linear(df, target="Y", inputs=["A", "B", "C"])
    result = analyze_residuals(fit, df)

    assert "residuals_vs_predicted" in result
    assert "predicted" in result["residuals_vs_predicted"]
    assert "residuals" in result["residuals_vs_predicted"]
    assert len(result["residuals_vs_predicted"]["predicted"]) == len(df)


def test_analyze_residuals_durbin_watson():
    df = _make_df()
    fit = fit_doe_linear(df, target="Y", inputs=["A", "B", "C"])
    result = analyze_residuals(fit, df)

    assert "durbin_watson" in result
    assert "statistic" in result["durbin_watson"]
    assert "interpretation" in result["durbin_watson"]
    # Durbin-Watson statistic should be between 0 and 4
    assert 0 <= result["durbin_watson"]["statistic"] <= 4
