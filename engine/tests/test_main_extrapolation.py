"""Tests for extrapolation risk IPC handler."""
import pytest

from process_intelligence_engine.main import handle_request, REGISTRY
import pandas as pd
import numpy as np


def test_extrapolation_check():
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "A": rng.uniform(0.0, 10.0, 50),
        "B": rng.uniform(5.0, 15.0, 50),
    })
    dataset_id = REGISTRY.register(df, {"file_path": "test", "format": "csv"})

    result = handle_request("modeling/extrapolation/check", {
        "dataset_id": dataset_id,
        "prediction_points": [{"A": 5.0, "B": 10.0}],
    })
    assert result["is_extrapolation"] is False
    assert result["max_risk"] == 0.0
    assert len(result["risk_scores"]) == 1


def test_extrapolation_check_outside():
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "A": rng.uniform(0.0, 10.0, 50),
        "B": rng.uniform(5.0, 15.0, 50),
    })
    dataset_id = REGISTRY.register(df, {"file_path": "test", "format": "csv"})

    result = handle_request("modeling/extrapolation/check", {
        "dataset_id": dataset_id,
        "prediction_points": [{"A": 15.0, "B": 10.0}],
    })
    assert result["is_extrapolation"] is True
    assert result["max_risk"] > 0


def test_extrapolation_check_multiple_points():
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "A": rng.uniform(0.0, 10.0, 50),
    })
    dataset_id = REGISTRY.register(df, {"file_path": "test", "format": "csv"})

    result = handle_request("modeling/extrapolation/check", {
        "dataset_id": dataset_id,
        "prediction_points": [
            {"A": 5.0},
            {"A": 15.0},
            {"A": -5.0},
        ],
    })
    assert len(result["risk_scores"]) == 3
    assert result["risk_scores"][0] == 0.0
    assert result["risk_scores"][1] > 0
    assert result["risk_scores"][2] > 0
