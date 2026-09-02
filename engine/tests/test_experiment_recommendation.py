"""Tests for experiment recommendation."""
import numpy as np
import pandas as pd
import pytest

from process_intelligence_engine.modeling.experiment_recommendation import recommend_experiments
from process_intelligence_engine.modeling.fitters import fit_doe_quadratic


def _make_df(n=100):
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "A": rng.uniform(0, 10, n),
        "B": rng.uniform(0, 10, n),
        "C": rng.uniform(0, 10, n),
    })
    df["Y"] = 2.0 + 3.0 * df["A"] - 2.0 * df["B"] + 0.5 * df["A"] * df["B"] + rng.normal(0, 0.5, n)
    return df


def test_recommend_experiments_returns_structure():
    df = _make_df()
    fit = fit_doe_quadratic(df, target="Y", inputs=["A", "B", "C"])
    interactions = {"significant_pairs": [{"i": "A", "j": "B", "strength": 0.5}]}
    validation = {"residuals": [0.1, -0.2], "stats": {"skewness": 0.1}}
    
    result = recommend_experiments(fit, df, interactions, validation)
    
    assert "recommendations" in result
    assert "summary" in result
    assert isinstance(result["recommendations"], list)
    assert len(result["recommendations"]) > 0


def test_recommend_experiments_detects_interaction():
    df = _make_df()
    fit = fit_doe_quadratic(df, target="Y", inputs=["A", "B", "C"])
    interactions = {"significant_pairs": [{"i": "A", "j": "B", "strength": 0.8}]}
    validation = {"residuals": [0.1], "stats": {}}
    
    result = recommend_experiments(fit, df, interactions, validation)
    
    interaction_recs = [r for r in result["recommendations"] if r["type"] == "interaction"]
    assert len(interaction_recs) > 0
    assert "A" in interaction_recs[0]["factors"]
    assert "B" in interaction_recs[0]["factors"]


def test_recommend_experiments_has_settings():
    df = _make_df()
    fit = fit_doe_quadratic(df, target="Y", inputs=["A", "B", "C"])
    interactions = {"significant_pairs": []}
    validation = {"residuals": [0.1], "stats": {}}
    
    result = recommend_experiments(fit, df, interactions, validation)
    
    for rec in result["recommendations"]:
        assert "settings" in rec
        assert isinstance(rec["settings"], list)
        assert "reason" in rec
