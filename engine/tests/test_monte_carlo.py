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
    assert result["extrapolation_count"] == 0
    assert result["extrapolation_rate"] == 0.0


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


def test_sampling_method_is_applied():
    rng = np.random.default_rng(7)
    df = _make_simple_dataset(rng)
    common = dict(
        df=df, model_type="doe_linear",
        coefficients={"_intercept": 10.0, "x1": 2.0, "x2": -1.5},
        input_columns=["x1", "x2"], output_column="y",
        n_simulations=100, seed=42, enable_anomalies=False,
        lsl=None, usl=None,
    )
    bootstrap = run_monte_carlo(**common, sampling_method="bootstrap")
    normal = run_monte_carlo(**common, sampling_method="normal")
    assert bootstrap["sampling_method"] == "bootstrap"
    assert normal["sampling_method"] == "normal"
    assert bootstrap["output_values"] != normal["output_values"]


def test_sample_distribution_unknown_type():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    samples = sample_from_distribution(values, dist_name="unknown_type", n=10, seed=42)
    assert len(samples) == 10


def test_sample_from_weibull():
    values = [10.0, 12.0, 11.0, 13.0, 12.5, 11.5, 12.0, 10.5, 13.5, 12.0]
    samples = sample_from_distribution(values, dist_name="weibull", n=200, seed=42)
    assert len(samples) == 200
    assert all(s >= 0 for s in samples)
    assert all(isinstance(s, float) for s in samples)
    # fallback 只會重放原始 10 個離散值；weibull 抽樣應產生連續新值
    assert len(set(samples)) > 20


def test_sample_from_poisson():
    values = [2.0, 3.0, 1.0, 4.0, 2.0, 3.0, 2.0, 1.0, 3.0, 2.0]
    samples = sample_from_distribution(values, dist_name="poisson", n=200, seed=42)
    assert len(samples) == 200
    assert all(s >= 0 and float(s).is_integer() for s in samples)
    # poisson(λ=2) 抽樣應產生超出原始值域的整數（如 0,5,6...），非只重放 [1..4]
    assert min(samples) < 1 or max(samples) > 4


def test_sample_poisson_negative_mean_falls_back():
    values = [-1.0, -2.0, -3.0, -1.0, -2.0]
    samples = sample_from_distribution(values, dist_name="poisson", n=50, seed=42)
    assert len(samples) == 50  # fallback empirical，不拋例外


def test_monte_carlo_extreme_percentiles_and_dpmo():
    rng = np.random.default_rng(3)
    df = _make_simple_dataset(rng)
    result = run_monte_carlo(
        df=df, model_type="doe_linear",
        coefficients={"_intercept": 10.0, "x1": 2.0, "x2": -1.5},
        input_columns=["x1", "x2"], output_column="y",
        n_simulations=3000, seed=42,
        lsl=100.0, usl=170.0,
    )
    p = result["percentiles"]
    assert "p0_1" in p and "p99_9" in p
    # bootstrap 抽樣自有限離散輸出值，極端外側百分位可能與相鄰百分位相等
    assert p["p0_1"] <= p["p1"] <= p["p99"] <= p["p99_9"]
    assert result["dpmo"] == pytest.approx(result["ng_probability"] * 1e6)


def test_monte_carlo_dpmo_none_without_spec():
    rng = np.random.default_rng(3)
    df = _make_simple_dataset(rng)
    result = run_monte_carlo(
        df=df, model_type="doe_linear",
        coefficients={"_intercept": 10.0, "x1": 2.0, "x2": -1.5},
        input_columns=["x1", "x2"], output_column="y",
        n_simulations=500, seed=42,
    )
    assert result["dpmo"] is None


def test_run_monte_carlo_input_distributions_extended():
    """auto 分支須真正以 lognormal 抽樣，非落入 bootstrap。"""
    import pandas as pd
    rng = np.random.default_rng(7)
    n = 120
    thickness = rng.lognormal(1.0, 0.3, n)  # 右偏、恆正
    x2 = rng.normal(50, 3, n)
    y = 10 + 2 * thickness - 1.5 * x2 + rng.normal(0, 0.5, n)
    df = pd.DataFrame({"thickness": thickness, "x2": x2, "y": y})
    coeffs = {"_intercept": float(y.mean()), "thickness": 2.0, "x2": -1.5}
    result = run_monte_carlo(
        df=df, model_type="doe_linear", coefficients=coeffs,
        input_columns=["thickness", "x2"], output_column="y",
        n_simulations=2000, seed=42,
        sampling_method="auto",
        input_distributions={
            "thickness": {"name": "lognormal"},
            "x2": {"name": "normal"},
        },
    )
    applied = result["input_distributions"]
    assert applied["thickness"]["name"] == "lognormal"
    assert applied["x2"]["name"] == "normal"
    # lognormal 抽樣應產生連續新值（fallback 只會重放原始 120 值）
    assert len(set(result["output_values"])) > 500


def test_run_monte_carlo_poisson_input():
    """auto 分支須以 poisson 整數抽樣 defects 欄。"""
    import pandas as pd
    rng = np.random.default_rng(11)
    n = 150
    defects = rng.poisson(3, n).astype(float)
    x2 = rng.normal(50, 3, n)
    y = 10 + 0.5 * defects - 1.0 * x2 + rng.normal(0, 0.3, n)
    df = pd.DataFrame({"defects": defects, "x2": x2, "y": y})
    coeffs = {"_intercept": float(y.mean()), "defects": 0.5, "x2": -1.0}
    result = run_monte_carlo(
        df=df, model_type="doe_linear", coefficients=coeffs,
        input_columns=["defects", "x2"], output_column="y",
        n_simulations=1500, seed=42,
        sampling_method="auto",
        input_distributions={
            "defects": {"name": "poisson"},
            "x2": {"name": "triangular"},
        },
    )
    applied = result["input_distributions"]
    assert applied["defects"]["name"] == "poisson"
    assert applied["x2"]["name"] == "triangular"


def test_predict_output_missing_coefficient():
    coeffs = {"_intercept": 10.0}
    inputs = {"x1": 5.0}
    result = predict_output("doe_linear", coeffs, inputs)
    assert result == 10.0


def test_predict_quadratic_trained_model_uses_fitter_feature_order():
    """A fitted DOE quadratic model must receive its expanded design matrix."""
    class RecordingModel:
        def predict(self, matrix):
            self.matrix = matrix
            return np.array([matrix[0].sum()])

    inputs = {"x1": 2.5, "x2": 1.5}
    model = RecordingModel()
    prediction = predict_output("doe_quadratic", {}, inputs, model=model)
    expected = float(np.array([1.0, 2.5, 2.5**2, 1.5, 1.5**2, 2.5 * 1.5]).sum())
    assert abs(prediction - expected) < 1e-8


def test_predict_tree_model_uses_fitted_feature_order():
    """Tree models must be fed the fitted input order, not sorted dict keys.

    Regression: the Monte Carlo path built its feature array from
    ``sorted(inputs.keys())``, so any model fitted on a non-alphabetical input
    order silently received its columns swapped.
    """
    import pandas as pd

    from process_intelligence_engine.modeling.fitters import fit_random_forest

    rng = np.random.default_rng(1)
    n = 400
    x1 = rng.uniform(0, 1, n)
    x2 = rng.uniform(0, 1, n)
    y = 100.0 + 5.0 * x1 + 0.2 * x2 + rng.normal(0, 0.02, n)
    df = pd.DataFrame({"x1": x1, "x2": x2, "y": y})
    fit = fit_random_forest(df, target="y", inputs=["x2", "x1"], random_state=1)

    point = {"x1": 1.0, "x2": 0.0}
    direct = float(fit.model.predict([[0.0, 1.0]])[0])  # fitted order [x2, x1]

    with_order = predict_output("random_forest", {}, point, model=fit.model,
                                feature_names=["x2", "x1"])
    assert with_order == pytest.approx(direct, abs=1e-9)

    # Without the fitted order the columns are swapped, giving a different value.
    without_order = predict_output("random_forest", {}, point, model=fit.model)
    assert abs(without_order - with_order) > 1.0
