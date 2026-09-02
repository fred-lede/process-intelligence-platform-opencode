"""Tests for prediction engine."""
import pytest
import pandas as pd
import numpy as np
from process_intelligence_engine.prediction import predict_single, get_input_ranges


def test_predict_single_linear():
    coeffs = {"_intercept": 10.0, "x1": 2.0, "x2": -1.5}
    inputs = {"x1": 100.0, "x2": 50.0}
    result = predict_single("doe_linear", coeffs, inputs)
    expected = 10.0 + 2.0 * 100.0 - 1.5 * 50.0
    assert abs(result - expected) < 0.001


def test_predict_single_quadratic():
    coeffs = {
        "_intercept": 10.0,
        "x1": 2.0,
        "x2": -1.5,
        "x1_x_x1": 0.01,
        "x1_x_x2": 0.02,
    }
    inputs = {"x1": 100.0, "x2": 50.0}
    result = predict_single("doe_quadratic", coeffs, inputs)
    expected = 10.0 + 2.0 * 100.0 - 1.5 * 50.0 + 0.01 * 100.0**2 + 0.02 * 100.0 * 50.0
    assert abs(result - expected) < 0.001


def test_predict_single_missing_coefficient():
    coeffs = {"_intercept": 10.0}
    inputs = {"x1": 5.0}
    result = predict_single("doe_linear", coeffs, inputs)
    assert result == 10.0


def test_predict_single_compact_coefficient_names():
    coeffs = {"_intercept": 5.0, "x1x2": 0.5, "x1x1": 0.1}
    inputs = {"x1": 10.0, "x2": 20.0}
    result = predict_single("doe_quadratic", coeffs, inputs)
    expected = 5.0 + 0.5 * 10.0 * 20.0 + 0.1 * 10.0**2
    assert abs(result - expected) < 0.001


def test_predict_single_unknown_model_type():
    coeffs = {"_intercept": 1.0}
    inputs = {"x1": 1.0}
    with pytest.raises(ValueError, match="Unsupported model type"):
        predict_single("unknown_model", coeffs, inputs)


def test_get_input_ranges():
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "x1": rng.normal(100, 5, 100),
        "x2": rng.normal(50, 3, 100),
    })
    ranges = get_input_ranges(df, ["x1", "x2"])
    assert "x1" in ranges
    assert "x2" in ranges
    assert ranges["x1"]["min"] < ranges["x1"]["max"]
    assert ranges["x2"]["min"] < ranges["x2"]["max"]
    assert ranges["x1"]["mean"] == pytest.approx(100.0, abs=5)
    assert ranges["x2"]["mean"] == pytest.approx(50.0, abs=3)


def test_get_input_ranges_empty_df():
    df = pd.DataFrame({"x1": pd.Series(dtype=float), "x2": pd.Series(dtype=float)})
    ranges = get_input_ranges(df, ["x1", "x2"])
    assert ranges["x1"]["min"] == 0.0
    assert ranges["x1"]["max"] == 0.0
    assert ranges["x1"]["mean"] == 0.0
    assert ranges["x1"]["std"] == 0.0
