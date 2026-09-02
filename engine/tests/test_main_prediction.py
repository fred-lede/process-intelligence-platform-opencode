"""Tests for prediction IPC handlers."""
import pytest
from process_intelligence_engine.main import handle_request


def _import_csv_for_pred(tmp_path):
    import numpy as np
    rng = np.random.default_rng(42)
    rows = ["x1,x2,y"]
    for _ in range(100):
        x1 = rng.normal(100, 5)
        x2 = rng.normal(50, 3)
        y = 10 + 2 * x1 - 1.5 * x2 + rng.normal(0, 1)
        rows.append(f"{x1:.4f},{x2:.4f},{y:.4f}")
    path = tmp_path / "pred.csv"
    path.write_text("\n".join(rows), encoding="utf-8")
    return handle_request("data/import", {"file_path": str(path)})["dataset_id"]


def _fit_model(tmp_path, did):
    return handle_request("modeling/fit", {
        "dataset_id": did,
        "model_type": "doe_linear",
        "target": "y",
        "inputs": ["x1", "x2"],
    })


def test_prediction_predict_basic(tmp_path):
    did = _import_csv_for_pred(tmp_path)
    fit = _fit_model(tmp_path, did)
    model_id = fit["model_id"]

    result = handle_request("prediction/predict", {
        "model_id": model_id,
        "input_values": {"x1": 100.0, "x2": 50.0},
    })
    assert result["success"]
    assert result["predicted"] is not None
    assert isinstance(result["predicted"], float)
    assert result["equation"] is not None
    assert result["inputs"] == ["x1", "x2"]
    import json
    json.dumps(result)


def test_prediction_predict_unknown_model_raises(tmp_path):
    did = _import_csv_for_pred(tmp_path)
    with pytest.raises(KeyError):
        handle_request("prediction/predict", {
            "model_id": "nonexistent",
            "input_values": {"x1": 100.0},
        })


def test_prediction_model_info(tmp_path):
    did = _import_csv_for_pred(tmp_path)
    fit = _fit_model(tmp_path, did)
    model_id = fit["model_id"]

    result = handle_request("prediction/model_info", {
        "model_id": model_id,
    })
    assert result["success"]
    assert result["model_type"] == "doe_linear"
    assert result["inputs"] == ["x1", "x2"]
    assert result["equation"] is not None
    assert result["n_train"] > 0
    import json
    json.dumps(result)


def test_prediction_model_info_unknown_model_raises():
    with pytest.raises(KeyError):
        handle_request("prediction/model_info", {
            "model_id": "nonexistent",
        })
