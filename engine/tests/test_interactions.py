"""Tests for interaction analysis."""
import numpy as np
import pandas as pd
import pytest

from process_intelligence_engine.modeling.interactions import compute_interactions
from process_intelligence_engine.modeling.fitters import fit_doe_quadratic


def _make_df(n=100):
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "A": rng.uniform(-1, 1, n),
        "B": rng.uniform(-1, 1, n),
        "C": rng.uniform(-1, 1, n),
    })
    # Y with strong A*B interaction, weak A*C, no B*C
    df["Y"] = 2.0 + 3.0 * df["A"] - 2.0 * df["B"] + 5.0 * df["A"] * df["B"] + 0.1 * df["C"] + rng.normal(0, 0.01, n)
    return df


def test_compute_interactions_returns_matrix():
    df = _make_df()
    fit = fit_doe_quadratic(df, target="Y", inputs=["A", "B", "C"])
    result = compute_interactions(fit, df)
    assert result["factors"] == ["A", "B", "C"]
    assert len(result["matrix"]) == 3
    assert len(result["matrix"][0]) == 3
    assert len(result["significant_pairs"]) > 0


def test_strong_interaction_detected():
    df = _make_df()
    fit = fit_doe_quadratic(df, target="Y", inputs=["A", "B", "C"])
    result = compute_interactions(fit, df)
    # A*B interaction (5.0) should be strongest
    ab_pair = [p for p in result["significant_pairs"] if set([p["i"], p["j"]]) == {"A", "B"}]
    assert len(ab_pair) == 1
    assert ab_pair[0]["strength"] > 0.1  # should be significant


def test_diagonal_is_zero():
    df = _make_df()
    fit = fit_doe_quadratic(df, target="Y", inputs=["A", "B", "C"])
    result = compute_interactions(fit, df)
    for idx in range(len(result["factors"])):
        assert result["matrix"][idx][idx] == 0.0


def test_matrix_is_symmetric():
    df = _make_df()
    fit = fit_doe_quadratic(df, target="Y", inputs=["A", "B", "C"])
    result = compute_interactions(fit, df)
    n = len(result["factors"])
    for i in range(n):
        for j in range(n):
            assert abs(result["matrix"][i][j] - result["matrix"][j][i]) < 1e-10
