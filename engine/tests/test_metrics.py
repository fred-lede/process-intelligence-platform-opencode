"""Tests for modeling metrics."""
import numpy as np

from process_intelligence_engine.modeling.metrics import (
    mean_absolute_error,
    mean_squared_error,
    root_mean_squared_error,
    r2_score,
    adjusted_r2,
)


def test_rmse_perfect_prediction_is_zero():
    y = np.array([1.0, 2.0, 3.0])
    assert root_mean_squared_error(y, y) == 0.0


def test_rmse_known_value():
    y = np.array([0.0, 0.0])
    yhat = np.array([1.0, 1.0])
    assert root_mean_squared_error(y, yhat) == 1.0
    assert np.isclose(mean_squared_error(y, yhat), 1.0)


def test_mae_is_mean_absolute_error():
    y = np.array([0.0, 0.0])
    yhat = np.array([1.0, -2.0])
    assert mean_absolute_error(y, yhat) == 1.5


def test_r2_perfect_is_one():
    y = np.array([1.0, 2.0, 3.0, 4.0])
    assert r2_score(y, y) == 1.0


def test_r2_worse_than_mean_is_negative():
    y = np.array([0.0, 0.0])
    yhat = np.array([5.0, 5.0])
    assert r2_score(y, yhat) < 0.0


def test_adjusted_r2_penalizes_more_features():
    y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    yhat = np.array([1.1, 1.9, 3.1, 4.1, 5.0])
    n = len(y)
    p_1 = 1
    p_3 = 3
    r2 = r2_score(y, yhat)
    assert adjusted_r2(r2, n, p_3) < adjusted_r2(r2, n, p_1)
    assert adjusted_r2(r2, n, p_1) < r2  # penalized below R2