import pandas as pd

from process_intelligence_engine.main import REGISTRY, handle_request


def test_time_series_fit_returns_model_ladder_and_unavailable_states():
    dataset_id = REGISTRY.register(
        pd.DataFrame({
            "ts": pd.date_range("2026-01-01", periods=40, freq="h"),
            "x": range(40),
            "y": [10 + i * 0.1 for i in range(40)],
        }), {}
    )
    result = handle_request("features/time_series/fit", {
        "dataset_id": dataset_id, "time_column": "ts", "target": "y",
        "inputs": ["x"], "lags": [1], "rolling_windows": [3],
    })
    names = {item["model_type"] for item in result["results"]}
    assert {"naive", "seasonal_naive", "dynamic_regression", "time_feature_random_forest"} <= names
    assert all(item["status"] in {"available", "unavailable"} for item in result["results"])
    assert result["validation"]["strategy"] == "chronological_holdout"
    assert result["training_time_range"]["end"] < result["validation"]["test_start"]


def test_time_series_fit_rejects_too_few_rows():
    dataset_id = REGISTRY.register(pd.DataFrame({"ts": pd.date_range("2026-01-01", periods=3), "y": [1, 2, 3]}), {})
    try:
        handle_request("features/time_series/fit", {"dataset_id": dataset_id, "time_column": "ts", "target": "y", "inputs": []})
    except ValueError as exc:
        assert "at least 5" in str(exc)
    else:
        raise AssertionError("expected small dataset error")


def test_time_series_fixed_horizon_is_explicit_and_does_not_mix_protocols():
    dataset_id = REGISTRY.register(pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=60, freq="h"),
        "x": range(60), "y": [10 + i * 0.1 for i in range(60)],
    }), {})
    result = handle_request("features/time_series/fit", {
        "dataset_id": dataset_id, "time_column": "ts", "target": "y",
        "inputs": ["x"], "lags": [1], "rolling_windows": [3],
        "evaluation_protocol": "fixed_horizon_forecast",
    })
    available = [item for item in result["results"] if item["status"] == "available"]
    assert available
    assert all(item["evaluation"]["protocol"] == "fixed_horizon_forecast" for item in available)
    assert all(item["evaluation"]["observed_target_usage"] == "training_only" for item in available)
    unsupported = [item for item in result["results"] if item.get("reason_code") == "not_supported"]
    assert unsupported
    assert result["validation"]["train_end"] < result["validation"]["test_start"]


def test_fixed_horizon_seasonal_naive_reports_insufficient_history_without_index_error():
    for rows, period in ((10, 24), (20, 20)):
        dataset_id = REGISTRY.register(pd.DataFrame({
            "ts": pd.date_range("2026-01-01", periods=rows, freq="h"),
            "y": [float(i) for i in range(rows)],
        }), {})
        result = handle_request("features/time_series/fit", {
            "dataset_id": dataset_id, "time_column": "ts", "target": "y",
            "inputs": [], "seasonal_period": period,
            "evaluation_protocol": "fixed_horizon_forecast",
        })
        seasonal = next(item for item in result["results"] if item["model_type"] == "seasonal_naive")
        assert seasonal["status"] == "unavailable"
        assert seasonal["reason_code"] == "insufficient_history"
        assert seasonal["evaluation"]["rows"] == 0
        assert seasonal["evaluation"]["protocol"] == "fixed_horizon_forecast"


def test_fixed_horizon_train_boundary_is_not_changed_by_test_target_values():
    frame = pd.DataFrame({"ts": pd.date_range("2026-01-01", periods=60, freq="h"), "y": [float(i) for i in range(60)]})
    first = REGISTRY.register(frame, {})
    changed = frame.copy(); changed.loc[50:, "y"] += 1000
    second = REGISTRY.register(changed, {})
    params = {"time_column": "ts", "target": "y", "inputs": [], "evaluation_protocol": "fixed_horizon_forecast"}
    left = handle_request("features/time_series/fit", {"dataset_id": first, **params})
    right = handle_request("features/time_series/fit", {"dataset_id": second, **params})
    assert left["validation"]["train_rows"] == right["validation"]["train_rows"]
    assert left["validation"]["train_end"] == right["validation"]["train_end"]
