"""Tests for prediction engine."""
import pytest
import pandas as pd
import numpy as np
from process_intelligence_engine.prediction import predict_single, get_input_ranges
from process_intelligence_engine.modeling.fitters import (
    fit_random_forest,
    fit_residual_hybrid,
)


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


def _asymmetric_df(n=400, seed=1):
    rng = np.random.default_rng(seed)
    x1 = rng.uniform(0, 1, n)
    x2 = rng.uniform(0, 1, n)
    y = 100.0 + 5.0 * x1 + 0.2 * x2 + rng.normal(0, 0.02, n)
    return pd.DataFrame({"x1": x1, "x2": x2, "y": y})


def test_model_prediction_honours_fitted_feature_order():
    # Regression: predict_single derived the column order from sorted(dict keys)
    # while the model was trained on fit.inputs, so any non-alphabetical input
    # order silently swapped the features.
    df = _asymmetric_df()
    fit = fit_random_forest(df, target="y", inputs=["x2", "x1"], random_state=1)

    point = {"x1": 1.0, "x2": 0.0}
    direct = float(fit.model.predict([[0.0, 1.0]])[0])  # training order [x2, x1]

    with_order = predict_single("random_forest", {}, point, model=fit.model,
                                feature_names=["x2", "x1"])
    assert with_order == pytest.approx(direct, abs=1e-9)

    # The old behaviour fed (x1, x2) and produced a different number.
    sorted_order = predict_single("random_forest", {}, point, model=fit.model)
    assert abs(sorted_order - with_order) > 1.0


def test_model_prediction_rejects_missing_features():
    df = _asymmetric_df()
    fit = fit_random_forest(df, target="y", inputs=["x2", "x1"], random_state=1)
    with pytest.raises(ValueError, match="missing input values"):
        predict_single("random_forest", {}, {"x1": 0.5}, model=fit.model,
                       feature_names=["x2", "x1"])


def test_residual_hybrid_predicts_doe_trend_plus_residual():
    # Regression: fit.model held only the residual learner, so prediction
    # returned a number centred on zero instead of Y.
    df = _asymmetric_df()
    fit = fit_residual_hybrid(df, target="y", inputs=["x1", "x2"], random_state=1)

    truth = 100.0 + 5.0 * 0.5 + 0.2 * 0.5
    pred = predict_single("residual_hybrid", fit.coefficients or {}, {"x1": 0.5, "x2": 0.5},
                          model=fit.model, feature_names=fit.inputs)
    assert pred == pytest.approx(truth, abs=1.0)

    # The composite must also be usable directly, in fitted column order.
    direct = float(fit.model.predict(np.array([[0.5, 0.5]]))[0])
    assert direct == pytest.approx(pred, abs=1e-9)
    assert abs(direct) > 50.0  # not merely the residual

