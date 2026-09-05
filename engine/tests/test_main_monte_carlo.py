"""Tests for Monte Carlo IPC handlers."""
import pytest
from process_intelligence_engine.main import handle_request


def _import_csv_for_mc(tmp_path):
    import numpy as np
    rng = np.random.default_rng(42)
    rows = ["x1,x2,y"]
    for _ in range(100):
        x1 = rng.normal(100, 5)
        x2 = rng.normal(50, 3)
        y = 10 + 2 * x1 - 1.5 * x2 + rng.normal(0, 1)
        rows.append(f"{x1:.4f},{x2:.4f},{y:.4f}")
    path = tmp_path / "mc.csv"
    path.write_text("\n".join(rows), encoding="utf-8")
    return handle_request("data/import", {"file_path": str(path)})["dataset_id"]


def _fit_model(tmp_path, did):
    return handle_request("modeling/fit", {
        "dataset_id": did,
        "model_type": "doe_linear",
        "target": "y",
        "inputs": ["x1", "x2"],
    })


def test_monte_carlo_run_basic(tmp_path):
    did = _import_csv_for_mc(tmp_path)
    fit = _fit_model(tmp_path, did)
    model_id = fit["model_id"]

    result = handle_request("monte_carlo/run", {
        "dataset_id": did,
        "model_id": model_id,
        "n_simulations": 500,
        "seed": 42,
        "enable_anomalies": False,
        "lsl": 50.0,
        "usl": 200.0,
    })
    assert result["success"]
    assert result["result"]["n_simulations"] == 500
    assert result["result"]["ng_count"] >= 0
    assert 0 <= result["result"]["ng_probability"] <= 1
    assert result["result"]["output_mean"] is not None
    assert "histogram" in result["result"]
    assert "cdf_data" in result["result"]
    assert "percentiles" in result["result"]
    import json
    json.dumps(result)  # verify JSON serializable


def test_monte_carlo_run_unknown_model_raises(tmp_path):
    did = _import_csv_for_mc(tmp_path)
    with pytest.raises(KeyError):
        handle_request("monte_carlo/run", {
            "dataset_id": did,
            "model_id": "nonexistent",
            "n_simulations": 100,
            "seed": 42,
            "enable_anomalies": False,
        })


def test_monte_carlo_run_with_anomalies(tmp_path):
    did = _import_csv_for_mc(tmp_path)
    fit = _fit_model(tmp_path, did)
    model_id = fit["model_id"]

    result = handle_request("monte_carlo/run", {
        "dataset_id": did,
        "model_id": model_id,
        "n_simulations": 200,
        "seed": 42,
        "enable_anomalies": True,
        "anomalies": [
            {
                "anomaly_id": "an-1",
                "name": "High x1",
                "target_input": "x1",
                "direction": "above",
                "occurrence_probability": 0.1,
                "magnitude_distribution": {"type": "constant", "value": 20.0},
            }
        ],
        "lsl": 50.0,
        "usl": 200.0,
    })
    assert result["success"]
    assert result["result"]["n_simulations"] == 200
    import json
    json.dumps(result)


def test_monte_carlo_run_no_bounds(tmp_path):
    did = _import_csv_for_mc(tmp_path)
    fit = _fit_model(tmp_path, did)
    model_id = fit["model_id"]

    result = handle_request("monte_carlo/run", {
        "dataset_id": did,
        "model_id": model_id,
        "n_simulations": 100,
        "seed": 42,
        "enable_anomalies": False,
    })
    assert result["success"]
    assert result["result"]["ng_count"] == 0
    assert result["result"]["ng_probability"] == 0.0


def test_monte_carlo_run_unknown_dataset_raises():
    with pytest.raises(KeyError):
        handle_request("monte_carlo/run", {
            "dataset_id": "nonexistent",
            "model_id": "some-model",
            "n_simulations": 100,
            "seed": 42,
            "enable_anomalies": False,
        })


def _import_csv_for_mc_filter(tmp_path):
    import numpy as np
    rng = np.random.default_rng(7)
    rows = ["work_order,x1,x2,y"]
    for i in range(80):
        group = "A" if i < 40 else "B"
        x1 = rng.uniform(90, 110) if group == "A" else rng.uniform(190, 210)
        x2 = rng.uniform(45, 55)
        y = 10 + 2 * x1 - 1.5 * x2 + rng.normal(0, 1)
        rows.append(f"{group},{x1:.4f},{x2:.4f},{y:.4f}")
    path = tmp_path / "mc_filter.csv"
    path.write_text("\n".join(rows), encoding="utf-8")
    return handle_request("data/import", {"file_path": str(path)})["dataset_id"]


def test_monte_carlo_run_with_filter(tmp_path):
    did = _import_csv_for_mc_filter(tmp_path)
    fit = _fit_model(tmp_path, did)
    model_id = fit["model_id"]

    params = {
        "dataset_id": did,
        "model_id": model_id,
        "n_simulations": 500,
        "seed": 42,
        "enable_anomalies": False,
    }
    unfiltered = handle_request("monte_carlo/run", dict(params))["result"]
    filtered = handle_request("monte_carlo/run", dict(
        params, filter_column="work_order", filter_value="A"
    ))["result"]

    assert sum(filtered["histogram"]["counts"]) == 500
    assert filtered["output_mean"] < 185
    assert unfiltered["output_mean"] > 185


def test_monte_carlo_run_with_filter_missing_value(tmp_path):
    did = _import_csv_for_mc_filter(tmp_path)
    fit = _fit_model(tmp_path, did)
    model_id = fit["model_id"]
    with pytest.raises(ValueError):
        handle_request("monte_carlo/run", {
            "dataset_id": did,
            "model_id": model_id,
            "n_simulations": 100,
            "seed": 42,
            "enable_anomalies": False,
            "filter_column": "work_order",
        })


def test_monte_carlo_run_with_filter_unknown_column(tmp_path):
    did = _import_csv_for_mc_filter(tmp_path)
    fit = _fit_model(tmp_path, did)
    model_id = fit["model_id"]
    with pytest.raises(KeyError):
        handle_request("monte_carlo/run", {
            "dataset_id": did,
            "model_id": model_id,
            "n_simulations": 100,
            "seed": 42,
            "enable_anomalies": False,
            "filter_column": "nonexistent",
            "filter_value": "A",
        })
