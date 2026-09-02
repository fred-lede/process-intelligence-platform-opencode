"""Tests for full validation IPC handler."""
import pytest

from process_intelligence_engine.main import handle_request
from process_intelligence_engine.modeling.fitters import fit_doe_linear, fit_doe_quadratic
from process_intelligence_engine.modeling.registry import ModelRegistry
from process_intelligence_engine.main import REGISTRY, MODEL_REGISTRY
import pandas as pd
import numpy as np


def _setup():
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "A": rng.uniform(0, 10, 50),
        "B": rng.uniform(0, 10, 50),
        "C": rng.uniform(0, 10, 50),
    })
    df["Y"] = 2.0 + 3.0 * df["A"] - 2.0 * df["B"] + rng.normal(0, 0.5, 50)

    dataset_id = REGISTRY.register(df, {"source": "test"})

    fit1 = fit_doe_linear(df, target="Y", inputs=["A", "B", "C"])
    fit2 = fit_doe_quadratic(df, target="Y", inputs=["A", "B", "C"])
    MODEL_REGISTRY.register(fit1)
    MODEL_REGISTRY.register(fit2)

    return fit1, fit2, dataset_id


def test_full_validation():
    fit1, fit2, dataset_id = _setup()
    result = handle_request("modeling/validation/full", {
        "dataset_id": dataset_id,
        "model_ids": [fit1.model_id, fit2.model_id],
    })

    assert "models" in result
    assert "best_model_id" in result
    assert "ranking" in result
    assert "residual_analysis" in result
    assert "experiment_recommendations" in result
    assert len(result["models"]) == 2
    assert result["residual_analysis"]["durbin_watson"]["statistic"] > 0
