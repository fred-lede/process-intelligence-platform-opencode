"""Tests for extrapolation risk scoring."""
import numpy as np
import pandas as pd
import pytest

from process_intelligence_engine.modeling.extrapolation import compute_extrapolation_risk


def _make_df(n=100):
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "A": rng.uniform(0.0, 10.0, n),
        "B": rng.uniform(5.0, 15.0, n),
        "C": rng.uniform(-5.0, 5.0, n),
    })
    return df


def test_compute_risk_no_extrapolation():
    df = _make_df()
    a_min, a_max = df["A"].min(), df["A"].max()
    b_min, b_max = df["B"].min(), df["B"].max()
    c_min, c_max = df["C"].min(), df["C"].max()
    point = {"A": (a_min + a_max) / 2, "B": (b_min + b_max) / 2, "C": (c_min + c_max) / 2}
    result = compute_extrapolation_risk(df, point)
    assert result["max_risk"] == 0.0
    assert result["is_extrapolation"] is False


def test_compute_risk_with_extrapolation():
    df = _make_df()
    a_min, a_max = df["A"].min(), df["A"].max()
    b_min, b_max = df["B"].min(), df["B"].max()
    c_min, c_max = df["C"].min(), df["C"].max()
    expected_risk = (a_max + 5.0 - a_max) / (a_max - a_min)  # (value - max) / range = 5.0 / range
    point = {"A": a_max + 5.0, "B": (b_min + b_max) / 2, "C": (c_min + c_max) / 2}
    result = compute_extrapolation_risk(df, point)
    assert result["is_extrapolation"] is True
    assert result["max_risk"] > 0
    assert result["factor_risks"]["A"]["risk"] == pytest.approx(5.0 / (a_max - a_min), abs=0.01)


def test_compute_risk_below_range():
    df = _make_df()
    a_min, a_max = df["A"].min(), df["A"].max()
    b_min, b_max = df["B"].min(), df["B"].max()
    c_min, c_max = df["C"].min(), df["C"].max()
    point = {"A": a_min - 5.0, "B": (b_min + b_max) / 2, "C": (c_min + c_max) / 2}
    result = compute_extrapolation_risk(df, point)
    assert result["is_extrapolation"] is True
    assert result["factor_risks"]["A"]["risk"] == pytest.approx(5.0 / (a_max - a_min), abs=0.01)


def test_compute_risk_multiple_points():
    df = _make_df()
    a_min, a_max = df["A"].min(), df["A"].max()
    b_min, b_max = df["B"].min(), df["B"].max()
    c_min, c_max = df["C"].min(), df["C"].max()
    mid = {"A": (a_min + a_max) / 2, "B": (b_min + b_max) / 2, "C": (c_min + c_max) / 2}
    out = {"A": a_max + 5.0, "B": (b_min + b_max) / 2, "C": (c_min + c_max) / 2}
    result = compute_extrapolation_risk(df, [mid, out])
    assert len(result["risk_scores"]) == 2
    assert result["risk_scores"][0] == 0.0
    assert result["risk_scores"][1] > 0


def test_compute_risk_edge_case():
    df = _make_df()
    a_min, a_max = df["A"].min(), df["A"].max()
    b_min, b_max = df["B"].min(), df["B"].max()
    c_min, c_max = df["C"].min(), df["C"].max()
    point = {"A": a_min, "B": b_min, "C": c_min}
    result = compute_extrapolation_risk(df, point)
    assert result["max_risk"] == 0.0
    assert result["is_extrapolation"] is False
