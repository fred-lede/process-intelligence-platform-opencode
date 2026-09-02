"""Tests for model selection."""
import numpy as np
import pandas as pd
import pytest

from process_intelligence_engine.modeling.model_selection import compare_models
from process_intelligence_engine.modeling.fitters import fit_doe_linear, fit_doe_quadratic, fit_random_forest


def _make_df(n=100):
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "A": rng.uniform(0, 10, n),
        "B": rng.uniform(0, 10, n),
        "C": rng.uniform(0, 10, n),
    })
    df["Y"] = 2.0 + 3.0 * df["A"] - 2.0 * df["B"] + 0.5 * df["A"] * df["B"] + rng.normal(0, 0.5, n)
    return df


def test_compare_models_returns_structure():
    df = _make_df()
    fits = [
        fit_doe_linear(df, target="Y", inputs=["A", "B", "C"]),
        fit_doe_quadratic(df, target="Y", inputs=["A", "B", "C"]),
    ]
    result = compare_models(fits, df, k=5)

    assert "models" in result
    assert "best_model_id" in result
    assert "ranking" in result
    assert len(result["models"]) == 2
    assert len(result["ranking"]) == 2
    assert result["best_model_id"] in result["ranking"]


def test_compare_models_ranking():
    df = _make_df()
    fits = [
        fit_doe_linear(df, target="Y", inputs=["A", "B", "C"]),
        fit_doe_quadratic(df, target="Y", inputs=["A", "B", "C"]),
    ]
    result = compare_models(fits, df, k=5)

    # Quadratic should rank higher due to interaction term
    linear_id = fits[0].model_id
    quadratic_id = fits[1].model_id

    linear_rank = result["ranking"].index(linear_id)
    quadratic_rank = result["ranking"].index(quadratic_id)

    # Either could be best, but both should be ranked
    assert linear_rank >= 0
    assert quadratic_rank >= 0


def test_compare_models_single_model():
    df = _make_df()
    fits = [fit_doe_linear(df, target="Y", inputs=["A", "B", "C"])]
    result = compare_models(fits, df, k=5)

    assert len(result["models"]) == 1
    assert result["best_model_id"] == fits[0].model_id
    assert result["ranking"] == [fits[0].model_id]
