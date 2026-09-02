"""Tests for SHAP analysis IPC handler."""
import pytest

from process_intelligence_engine.main import handle_request, REGISTRY, MODEL_REGISTRY
from process_intelligence_engine.modeling.fitters import fit_doe_quadratic, fit_random_forest
import pandas as pd
import numpy as np


def _setup_fit(model_type="doe_quadratic"):
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "A": rng.uniform(-1, 1, 50),
        "B": rng.uniform(-1, 1, 50),
        "C": rng.uniform(-1, 1, 50),
    })
    df["Y"] = 2.0 + 3.0 * df["A"] - 2.0 * df["B"] + 5.0 * df["A"] * df["B"] + 0.1 * df["C"]
    dataset_id = REGISTRY.register(df, {"file_path": "test", "format": "csv"})
    if model_type == "doe_quadratic":
        fit = fit_doe_quadratic(df, target="Y", inputs=["A", "B", "C"])
    else:
        fit = fit_random_forest(df, target="Y", inputs=["A", "B", "C"])
    MODEL_REGISTRY.register(fit)
    return fit, dataset_id


def test_shap_doe():
    fit, dataset_id = _setup_fit("doe_quadratic")
    result = handle_request("modeling/shap/explain", {
        "model_id": fit.model_id,
        "dataset_id": dataset_id,
    })
    assert result["expected_value"] is not None
    assert len(result["feature_importance"]) == 3
    assert result["feature_importance"][0]["importance"] > 0
    assert len(result["shap_values"]) == 50


def test_shap_random_forest():
    fit, dataset_id = _setup_fit("random_forest")
    result = handle_request("modeling/shap/explain", {
        "model_id": fit.model_id,
        "dataset_id": dataset_id,
    })
    assert result["expected_value"] is not None
    assert len(result["feature_importance"]) == 3


def test_shap_unknown_model():
    with pytest.raises((KeyError, ValueError)):
        handle_request("modeling/shap/explain", {
            "model_id": "nonexistent",
            "dataset_id": "test",
        })
