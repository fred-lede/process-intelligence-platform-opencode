"""Tests for interaction analysis IPC handler."""
import pytest

from process_intelligence_engine.main import handle_request, REGISTRY, MODEL_REGISTRY
from process_intelligence_engine.modeling.fitters import fit_doe_quadratic
import pandas as pd
import numpy as np


def _setup_fit():
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "A": rng.uniform(-1, 1, 50),
        "B": rng.uniform(-1, 1, 50),
        "C": rng.uniform(-1, 1, 50),
    })
    df["Y"] = 2.0 + 3.0 * df["A"] - 2.0 * df["B"] + 5.0 * df["A"] * df["B"] + 0.1 * df["C"]
    return fit_doe_quadratic(df, target="Y", inputs=["A", "B", "C"])


def _setup_dataset():
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "A": rng.uniform(-1, 1, 50),
        "B": rng.uniform(-1, 1, 50),
        "C": rng.uniform(-1, 1, 50),
    })
    df["Y"] = 2.0 + 3.0 * df["A"] - 2.0 * df["B"] + 5.0 * df["A"] * df["B"] + 0.1 * df["C"]
    return df


def test_interactions_compute():
    df = _setup_dataset()
    fit = fit_doe_quadratic(df, target="Y", inputs=["A", "B", "C"])
    MODEL_REGISTRY.register(fit)
    dataset_id = REGISTRY.register(df, {"file_path": "test", "format": "csv"})

    result = handle_request("modeling/interactions/compute", {
        "model_id": fit.model_id,
        "dataset_id": dataset_id,
        "threshold": 0.01,
    })
    assert result["factors"] == ["A", "B", "C"]
    assert len(result["matrix"]) == 3
    ab = [p for p in result["significant_pairs"] if set([p["i"], p["j"]]) == {"A", "B"}]
    assert len(ab) == 1
    assert ab[0]["strength"] > 0.1


def test_interactions_unknown_model():
    with pytest.raises((KeyError, ValueError)):
        handle_request("modeling/interactions/compute", {"model_id": "nonexistent", "dataset_id": "x"})
