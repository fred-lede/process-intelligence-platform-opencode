import numpy as np
import pandas as pd

from process_intelligence_engine.main import REGISTRY, handle_request


def test_residual_hybrid_returns_baseline_hybrid_metrics_and_provenance():
    n = 60
    x = np.linspace(0, 1, n)
    y = 10 + 2 * x + np.sin(np.arange(n) / 4) * 0.1
    dataset_id = REGISTRY.register(pd.DataFrame({"ts": pd.date_range("2026-01-01", periods=n, freq="h"), "x": x, "y": y}), {})
    result = handle_request("features/time_series/hybrid", {"dataset_id": dataset_id, "time_column": "ts", "target": "y", "inputs": ["x"], "lags": [1], "rolling_windows": [3]})
    assert result["status"] == "completed"
    assert set(result["hybrid"]["metrics"]) == {"mae", "rmse", "r2"}
    assert set(result["baseline"]["metrics"]) == {"mae", "rmse", "r2"}
    assert result["provenance"]["target_residual_training"] == "training_only"
    assert result["leakage_check"] == "passed_by_historical_features"


def test_residual_hybrid_fixed_horizon_does_not_change_when_test_targets_are_perturbed():
    n = 50
    frame = pd.DataFrame({"ts": pd.date_range("2026-01-01", periods=n, freq="h"), "x": np.linspace(0, 1, n), "y": np.linspace(10, 11, n)})
    one = REGISTRY.register(frame, {})
    changed = frame.copy()
    changed.loc[40:, "y"] += 1000
    two = REGISTRY.register(changed, {})
    params = {"time_column": "ts", "target": "y", "inputs": ["x"], "lags": [1], "rolling_windows": [3], "evaluation_protocol": "fixed_horizon_forecast"}
    left = handle_request("features/time_series/hybrid", {"dataset_id": one, **params})
    right = handle_request("features/time_series/hybrid", {"dataset_id": two, **params})
    assert left["hybrid"]["metrics"] != right["hybrid"]["metrics"]
    assert left["provenance"]["target_residual_training"] == right["provenance"]["target_residual_training"] == "training_only"
