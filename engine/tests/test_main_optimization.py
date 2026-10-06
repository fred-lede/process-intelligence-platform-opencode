"""Tests for optimization IPC handler."""
import pytest
from process_intelligence_engine.main import handle_request


def _setup(tmp_path):
    import numpy as np
    rng = np.random.default_rng(42)
    rows = ["x1,x2,y"]
    for _ in range(100):
        x1 = rng.normal(100, 5)
        x2 = rng.normal(50, 3)
        y = 10 + 2 * x1 - 1.5 * x2 + rng.normal(0, 1)
        rows.append(f"{x1:.4f},{x2:.4f},{y:.4f}")
    path = tmp_path / "opt.csv"
    path.write_text("\n".join(rows), encoding="utf-8")
    did = handle_request("data/import", {"file_path": str(path)})["dataset_id"]
    fit = handle_request("modeling/fit", {"dataset_id": did, "model_type": "doe_linear",
                                          "target": "y", "inputs": ["x1", "x2"]})
    return did, fit["model_id"]


def test_optquest_run_success(tmp_path):
    did, mid = _setup(tmp_path)
    result = handle_request("optimization/optquest/run", {
        "model_id": mid, "dataset_id": did, "objective": "maximize_yield",
        "lsl": 150.0, "usl": 400.0, "n_candidates": 60, "n_eval_samples": 150, "seed": 42,
    })
    assert result["success"] is True
    r = result["result"]
    assert set(r["best_point"]) == {"x1", "x2"}
    assert r["baseline"] is not None and "yield" in r["baseline"]
    assert len(r["trajectory"]) == 60
    import json
    json.dumps(result)


def test_optquest_missing_spec_structured_error(tmp_path):
    did, mid = _setup(tmp_path)
    result = handle_request("optimization/optquest/run", {
        "model_id": mid, "dataset_id": did, "objective": "maximize_yield",
        "n_candidates": 10, "seed": 42,
    })
    assert result["success"] is False
    assert "LSL/USL" in result["error"]["message"]


def test_optquest_unknown_model_structured_error(tmp_path):
    did, mid = _setup(tmp_path)
    result = handle_request("optimization/optquest/run", {
        "model_id": "nonexistent", "dataset_id": did, "objective": "hit_target",
        "target_value": 100.0, "n_candidates": 10, "seed": 42,
    })
    assert result["success"] is False
