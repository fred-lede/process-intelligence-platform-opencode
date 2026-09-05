"""Tests for modeling/* IPC handlers."""

import json

import pytest

from process_intelligence_engine.main import handle_request


def _import_model_csv(tmp_path):
    import numpy as np
    rng = np.random.default_rng(1)
    rows = ["x1,x2,y"]
    for _ in range(120):
        x1 = rng.uniform(0, 1)
        x2 = rng.uniform(0, 1)
        y = 2.0 + 3.0 * x1 - 4.0 * x2 + rng.normal(0, 0.01)
        rows.append(f"{x1:.5f},{x2:.5f},{y:.5f}")
    path = tmp_path / "model.csv"
    path.write_text("\n".join(rows), encoding="utf-8")
    return handle_request("data/import", {"file_path": str(path)})["dataset_id"]


def test_modeling_fit_returns_dto(tmp_path):
    did = _import_model_csv(tmp_path)
    result = handle_request(
        "modeling/fit",
        {"dataset_id": did, "model_type": "doe_linear", "target": "y", "inputs": ["x1", "x2"]},
    )
    assert result["model_type"] == "doe_linear"
    assert result["metrics"]["r2"] > 0.9
    json.dumps(result)


def test_modeling_fit_residual_hybrid(tmp_path):
    did = _import_model_csv(tmp_path)
    result = handle_request(
        "modeling/fit",
        {"dataset_id": did, "model_type": "residual_hybrid", "target": "y", "inputs": ["x1", "x2"]},
    )
    assert result["model_type"] == "residual_hybrid"
    assert result["metrics"]["r2"] > 0.9


def test_modeling_fit_unknown_type_raises(tmp_path):
    did = _import_model_csv(tmp_path)
    with pytest.raises(ValueError):
        handle_request(
            "modeling/fit",
            {"dataset_id": did, "model_type": "nope", "target": "y", "inputs": ["x1"]},
        )


def test_modeling_transition_and_list(tmp_path):
    did = _import_model_csv(tmp_path)
    fit = handle_request(
        "modeling/fit",
        {"dataset_id": did, "model_type": "doe_linear", "target": "y", "inputs": ["x1", "x2"]},
    )
    assert fit["status"] == "draft"

    pending = handle_request("modeling/transition", {"model_id": fit["model_id"], "status": "pending_validation"})
    assert pending["status"] == "pending_validation"

    listing = handle_request("modeling/list", {})
    assert any(m["model_id"] == fit["model_id"] for m in listing["models"])


def test_modeling_transition_invalid_raises(tmp_path):
    did = _import_model_csv(tmp_path)
    fit = handle_request(
        "modeling/fit",
        {"dataset_id": did, "model_type": "doe_linear", "target": "y", "inputs": ["x1", "x2"]},
    )
    with pytest.raises(Exception) as exc:
        handle_request("modeling/transition", {"model_id": fit["model_id"], "status": "approved"})
    assert "transition" in str(exc.value).lower() or "Cannot" in str(exc.value)


def test_modeling_fit_rf_with_hyperparameters(tmp_path):
    did = _import_model_csv(tmp_path)
    result = handle_request(
        "modeling/fit",
        {
            "dataset_id": did,
            "model_type": "random_forest",
            "target": "y",
            "inputs": ["x1", "x2"],
            "n_estimators": 50,
            "max_depth": 5,
            "auto_select_features": False,
        },
    )
    assert result["model_type"] == "random_forest"
    assert result["metrics"]["r2"] > 0.5
    json.dumps(result)


def test_modeling_fit_rf_auto_select_features(tmp_path):
    """Test IPC layer with auto feature selection."""
    import numpy as np
    rng = np.random.default_rng(42)
    n = 200
    x1 = rng.uniform(0, 1, n)
    x2 = rng.uniform(0, 1, n)
    noise = rng.uniform(0, 1, n)
    y = 2.0 + 3.0 * x1 - 4.0 * x2 + rng.normal(0, 0.01, n)
    rows = ["x1,x2,noise,y"]
    for i in range(n):
        rows.append(f"{x1[i]:.5f},{x2[i]:.5f},{noise[i]:.5f},{y[i]:.5f}")
    path = tmp_path / "rf_select.csv"
    path.write_text("\n".join(rows), encoding="utf-8")
    did = handle_request("data/import", {"file_path": str(path)})["dataset_id"]
    
    result = handle_request(
        "modeling/fit",
        {
            "dataset_id": did,
            "model_type": "random_forest",
            "target": "y",
            "inputs": ["x1", "x2", "noise"],
            "auto_select_features": True,
        },
    )
    assert result["model_type"] == "random_forest"
    assert "selected_inputs" in result
    assert len(result["selected_inputs"]) <= 2
    assert "noise" not in result["selected_inputs"]
