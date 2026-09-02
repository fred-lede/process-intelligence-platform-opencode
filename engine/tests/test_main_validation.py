"""Tests for validation analysis IPC handler."""
import numpy as np
import pandas as pd
import pytest

from process_intelligence_engine.main import handle_request, REGISTRY, MODEL_REGISTRY
from process_intelligence_engine.modeling.fitters import fit_doe_linear


def _setup():
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "A": rng.uniform(0, 10, 50),
        "B": rng.uniform(0, 10, 50),
        "C": rng.uniform(0, 10, 50),
    })
    df["Y"] = 2.0 + 3.0 * df["A"] - 2.0 * df["B"] + rng.normal(0, 0.5, 50)
    dataset_id = REGISTRY.register(df, {"source": "test"})
    fit = fit_doe_linear(df, target="Y", inputs=["A", "B", "C"])
    MODEL_REGISTRY.register(fit)
    return fit, dataset_id


def test_validation_analyze():
    fit, dataset_id = _setup()
    result = handle_request("modeling/validation/analyze", {
        "model_id": fit.model_id,
        "dataset_id": dataset_id,
        "k": 5,
    })

    assert "cv_results" in result
    assert "mean_metrics" in result
    assert len(result["cv_results"]) == 5
    assert "residuals" in result
    assert "stats" in result
    assert "recommendations" in result
    assert isinstance(result["recommendations"], list)


def test_validation_analyze_unknown_model():
    with pytest.raises((ValueError, KeyError)):
        handle_request("modeling/validation/analyze", {
            "model_id": "nonexistent",
            "dataset_id": "test",
            "k": 5,
        })
