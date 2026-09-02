"""Tests for Monte Carlo simulation engine."""
import numpy as np
import pytest

from process_intelligence_engine.monte_carlo import (
    run_monte_carlo,
    sample_from_distribution,
    apply_anomalies,
    predict_output,
)


def _make_simple_dataset(rng):
    """Create a simple dataset for testing."""
    import pandas as pd
    n = 100
    x1 = rng.normal(100, 5, n)
    x2 = rng.normal(50, 3, n)
    y = 10 + 2 * x1 - 1.5 * x2 + rng.normal(0, 1, n)
    return pd.DataFrame({"x1": x1, "x2": x2, "y": y})


def test_sample_from_normal():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    samples = sample_from_distribution(values, dist_name="normal", n=100, seed=42)
    assert len(samples) == 100
    assert all(isinstance(s, float) for s in samples)


def test_sample_from_histogram():
    values = list(range(100))
    samples = sample_from_distribution(values, dist_name="histogram", n=50, seed=42)
    assert len(samples) == 50


def test_predict_linear():
    coeffs = {"_intercept": 10.0, "x1": 2.0, "x2": -1.5}
    inputs = {"x1": 100.0, "x2": 50.0}
    result = predict_output("doe_linear", coeffs, inputs)
    expected = 10.0 + 2.0 * 100.0 - 1.5 * 50.0
    assert abs(result - expected) < 0.001


def test_predict_quadratic():
    coeffs = {
        "_intercept": 10.0,
        "x1": 2.0,
        "x2": -1.5,
        "x1_x_x1": 0.1,
        "x2_x_x2": -0.05,
        "x1_x_x2": 0.3,
    }
    inputs = {"x1": 100.0, "x2": 50.0}
    result = predict_output("doe_quadratic", coeffs, inputs)
    expected = 10.0 + 2.0 * 100.0 - 1.5 * 50.0 + 0.1 * 100.0**2 + (-0.05) * 50.0**2 + 0.3 * 100.0 * 50.0
    assert abs(result - expected) < 0.001


def test_apply_anomalies_no_anomaly():
    values = [100.0, 101.0, 99.0]
    anomalies = []
    rng = np.random.default_rng(42)
    result = apply_anomalies(values, anomalies, rng)
    assert result == values


def test_apply_anomalies_with_anomaly():
    anomalies = [{"target_input": "x1", "direction": "above", "magnitude": 10.0, "occurrence_probability": 1.0}]
    values = [100.0, 100.0, 100.0]
    rng = np.random.default_rng(42)
    result = apply_anomalies(values, anomalies, rng)
    assert all(v == 110.0 for v in result)


def test_apply_anomalies_probabilistic():
    anomalies = [{"target_input": "x1", "direction": "above", "magnitude": 10.0, "occurrence_probability": 0.0}]
    values = [100.0, 100.0, 100.0]
    rng = np.random.default_rng(42)
    result = apply_anomalies(values, anomalies, rng)
    assert all(v == 100.0 for v in result)


def test_run_monte_carlo_basic():
    import pandas as pd
    rng = np.random.default_rng(42)
    df = _make_simple_dataset(rng)

    model_coeffs = {"_intercept": 10.0, "x1": 2.0, "x2": -1.5}
    inputs = ["x1", "x2"]

    result = run_monte_carlo(
        df=df,
        model_type="doe_linear",
        coefficients=model_coeffs,
        input_columns=inputs,
        output_column="y",
        n_simulations=1000,
        seed=42,
        enable_anomalies=False,
        lsl=50.0,
        usl=200.0,
    )

    assert result["n_simulations"] == 1000
    assert result["ng_count"] >= 0
    assert 0.0 <= result["ng_probability"] <= 1.0
    assert result["output_mean"] is not None
    assert result["percentiles"] is not None
    assert "histogram" in result
    assert "cdf_data" in result


def test_run_monte_carlo_with_anomalies():
    import pandas as pd
    rng = np.random.default_rng(42)
    df = _make_simple_dataset(rng)

    model_coeffs = {"_intercept": 10.0, "x1": 2.0, "x2": -1.5}
    anomalies = [
        {
            "anomaly_id": "an-1",
            "target_input": "x1",
            "direction": "above",
            "occurrence_probability": 0.1,
            "magnitude_distribution": {"type": "constant", "value": 20.0},
        }
    ]

    result = run_monte_carlo(
        df=df,
        model_type="doe_linear",
        coefficients=model_coeffs,
        input_columns=["x1", "x2"],
        output_column="y",
        n_simulations=500,
        seed=42,
        enable_anomalies=True,
        anomalies=anomalies,
        lsl=50.0,
        usl=200.0,
    )

    assert result["n_simulations"] == 500
    assert result["ng_count"] >= 0
    assert result["ng_probability"] >= 0


def test_run_monte_carlo_small_n():
    import pandas as pd
    rng = np.random.default_rng(42)
    df = _make_simple_dataset(rng)

    result = run_monte_carlo(
        df=df,
        model_type="doe_linear",
        coefficients={"_intercept": 10.0, "x1": 2.0, "x2": -1.5},
        input_columns=["x1", "x2"],
        output_column="y",
        n_simulations=10,
        seed=42,
        enable_anomalies=False,
        lsl=None,
        usl=None,
    )
    assert result["n_simulations"] == 10


def test_run_monte_carlo_quadratic():
    import pandas as pd
    rng = np.random.default_rng(42)
    df = _make_simple_dataset(rng)

    coeffs = {
        "_intercept": 10.0,
        "x1": 2.0,
        "x2": -1.5,
        "x1_x_x1": 0.01,
        "x2_x_x2": -0.005,
        "x1_x_x2": 0.02,
    }

    result = run_monte_carlo(
        df=df,
        model_type="doe_quadratic",
        coefficients=coeffs,
        input_columns=["x1", "x2"],
        output_column="y",
        n_simulations=100,
        seed=42,
        enable_anomalies=False,
        lsl=50.0,
        usl=200.0,
    )
    assert result["output_mean"] is not None
    assert len(result["output_values"]) == 100


def test_run_monte_carlo_no_bounds():
    import pandas as pd
    rng = np.random.default_rng(42)
    df = _make_simple_dataset(rng)

    result = run_monte_carlo(
        df=df,
        model_type="doe_linear",
        coefficients={"_intercept": 10.0, "x1": 2.0, "x2": -1.5},
        input_columns=["x1", "x2"],
        output_column="y",
        n_simulations=100,
        seed=42,
        enable_anomalies=False,
        lsl=None,
        usl=None,
    )
    assert result["ng_count"] == 0
    assert result["ng_probability"] == 0.0


def test_sample_distribution_unknown_type():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    samples = sample_from_distribution(values, dist_name="unknown_type", n=10, seed=42)
    assert len(samples) == 10


def test_predict_output_missing_coefficient():
    coeffs = {"_intercept": 10.0}
    inputs = {"x1": 5.0}
    result = predict_output("doe_linear", coeffs, inputs)
    assert result == 10.0
