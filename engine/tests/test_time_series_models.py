import math
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from process_intelligence_engine.main import REGISTRY, handle_request
from process_intelligence_engine.main import MODEL_REGISTRY
from process_intelligence_engine.modeling import time_series_models


def test_time_series_lstm_reports_insufficient_sequence_history(monkeypatch):
    original_find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name: object() if name == "tensorflow" else original_find_spec(name),
    )
    dataset_id = REGISTRY.register(pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=50, freq="h"),
        "y": [float(index) for index in range(50)],
    }), {})

    result = handle_request("features/time_series/fit", {
        "dataset_id": dataset_id,
        "time_column": "ts",
        "target": "y",
        "inputs": [],
        "lstm_sequence_length": 24,
    })

    lstm = next(item for item in result["results"] if item["model_type"] == "lstm")
    assert lstm["status"] == "unavailable"
    assert lstm["reason_code"] == "insufficient_history"
    assert result["capabilities"]["lstm"] == lstm["capability"]
    assert lstm["capability"]["dependency"] == {"name": "tensorflow", "available": True}
    assert lstm["capability"]["data"] == {
        "training_rows": 37,
        "sequence_length": 24,
        "available_sequences": 13,
        "minimum_sequences": 32,
        "meets_threshold": False,
    }
    assert lstm["capability"]["eligible"] is False
    assert lstm["capability"]["reason_codes"] == ["insufficient_history"]


def test_time_series_lstm_reports_missing_optional_dependency(monkeypatch):
    original_find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name: None if name == "tensorflow" else original_find_spec(name),
    )
    dataset_id = REGISTRY.register(pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=100, freq="h"),
        "y": [float(index) for index in range(100)],
    }), {})

    result = handle_request("features/time_series/fit", {
        "dataset_id": dataset_id,
        "time_column": "ts",
        "target": "y",
        "inputs": [],
        "lstm_sequence_length": 12,
    })

    lstm = next(item for item in result["results"] if item["model_type"] == "lstm")
    assert lstm["status"] == "unavailable"
    assert lstm["reason_code"] == "dependency_missing"
    assert lstm["capability"]["dependency"] == {"name": "tensorflow", "available": False}
    assert lstm["capability"]["data"]["meets_threshold"] is True
    assert lstm["capability"]["eligible"] is False
    assert lstm["capability"]["reason_codes"] == ["dependency_missing"]


def test_advanced_time_series_rows_report_insufficient_sequence_history(monkeypatch):
    original_find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name: object()
        if name in {"tensorflow", "pytorch_forecasting"}
        else original_find_spec(name),
    )
    dataset_id = REGISTRY.register(pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=100, freq="h"),
        "y": [float(index) for index in range(100)],
    }), {})

    result = handle_request("features/time_series/fit", {
        "dataset_id": dataset_id,
        "time_column": "ts",
        "target": "y",
        "inputs": [],
        "lstm_sequence_length": 1000,
        "transformer_sequence_length": 24,
        "tft_sequence_length": 24,
    })

    rows = {item["model_type"]: item for item in result["results"]}
    for model_type, minimum_sequences, reason_codes in (
        ("transformer", 64, ["insufficient_history"]),
        ("temporal_fusion_transformer", 128, ["insufficient_history", "not_implemented"]),
    ):
        row = rows[model_type]
        assert row["status"] == "unavailable"
        assert row["reason_code"] == "insufficient_history"
        assert result["capabilities"][model_type] == row["capability"]
        assert row["capability"]["data"] == {
            "training_rows": 77,
            "sequence_length": 24,
            "available_sequences": 53,
            "minimum_sequences": minimum_sequences,
            "meets_threshold": False,
        }
        assert row["capability"]["eligible"] is False
        assert row["capability"]["reason_codes"] == reason_codes


def test_advanced_time_series_rows_report_missing_dependencies(monkeypatch):
    original_find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name: None
        if name in {"tensorflow", "pytorch_forecasting"}
        else original_find_spec(name),
    )
    dataset_id = REGISTRY.register(pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=220, freq="h"),
        "y": [float(index) for index in range(220)],
    }), {})

    result = handle_request("features/time_series/fit", {
        "dataset_id": dataset_id,
        "time_column": "ts",
        "target": "y",
        "inputs": [],
        "lstm_sequence_length": 1000,
        "transformer_sequence_length": 24,
        "tft_sequence_length": 24,
    })

    rows = {item["model_type"]: item for item in result["results"]}
    expected_dependencies = {
        "transformer": ("tensorflow", ["dependency_missing"]),
        "temporal_fusion_transformer": (
            "pytorch_forecasting", ["dependency_missing", "not_implemented"],
        ),
    }
    for model_type, (dependency, reason_codes) in expected_dependencies.items():
        row = rows[model_type]
        assert row["status"] == "unavailable"
        assert row["reason_code"] == "dependency_missing"
        assert row["capability"]["dependency"] == {
            "name": dependency, "available": False,
        }
        assert row["capability"]["data"]["meets_threshold"] is True
        assert row["capability"]["eligible"] is False
        assert row["capability"]["reason_codes"] == reason_codes


def test_time_series_transformer_fits_when_capability_requirements_are_met():
    if importlib.util.find_spec("tensorflow") is None:
        pytest.skip("tensorflow is optional")
    frame = pd.read_csv(
        Path(__file__).parents[2] / "data/test_dataset_timeseries_transformer.csv"
    )
    dataset_id = REGISTRY.register(frame, {})

    result = handle_request("features/time_series/fit", {
        "dataset_id": dataset_id,
        "time_column": "datetime",
        "target": "output_thickness",
        "inputs": [
            "input_temperature", "input_voltage", "input_pressure",
            "input_speed", "input_load",
        ],
        "lags": [1],
        "rolling_windows": [3],
        "evaluation_protocol": "fixed_horizon_forecast",
        "lstm_sequence_length": 1000,
        "transformer_sequence_length": 24,
    })

    transformer = next(
        item for item in result["results"] if item["model_type"] == "transformer"
    )
    assert transformer["status"] == "available"
    assert set(transformer["metrics"]) == {"mae", "rmse", "r2"}
    assert all(math.isfinite(value) for value in transformer["metrics"].values())
    capability = transformer["capability"]
    assert capability["eligible"] is True
    assert capability["dependency"] == {"name": "tensorflow", "available": True}
    assert capability["data"]["sequence_length"] == 24
    assert capability["data"]["available_sequences"] == capability["data"]["training_rows"] - 24
    assert capability["data"]["available_sequences"] >= 64
    assert capability["data"]["minimum_sequences"] == 64
    assert capability["data"]["meets_threshold"] is True
    assert capability["reason_codes"] == []
    assert transformer["evaluation"]["rows"] == transformer["validation"]["test_rows"]
    assert transformer["evaluation"]["rows"] > 0
    assert transformer["evaluation"]["protocol"] == "fixed_horizon_forecast"
    assert transformer["evaluation"]["uses_observed_target"] is False
    assert transformer["evaluation"]["observed_target_usage"] == "training_only"
    assert transformer["leakage_check"] == "passed_by_historical_features"


def test_transformer_sequence_normalization_is_fit_from_training_history():
    target_center, target_scale, input_center, input_scale = (
        time_series_models._fit_sequence_normalization(
            np.asarray([10.0, 20.0, 30.0]),
            np.asarray([
                [1.0, 2.0, 3.0, 4.0, 5.0],
                [3.0, 4.0, 5.0, 6.0, 7.0],
                [5.0, 6.0, 7.0, 8.0, 9.0],
            ]),
        )
    )

    assert target_center == 20.0
    assert target_scale == pytest.approx(np.std([10.0, 20.0, 30.0]))
    assert input_center.tolist() == [3.0, 4.0, 5.0, 6.0, 7.0]
    assert input_scale.tolist() == pytest.approx([np.std([1.0, 3.0, 5.0])] * 5)


def test_transformer_fixed_horizon_uses_historical_inputs_and_prior_predictions():
    class LastValueModel:
        def __init__(self):
            self.inputs = []

        def predict(self, values, verbose=0):
            self.inputs.append(values.copy())
            return np.asarray([[values[0, -1, 0]]])

    model = LastValueModel()
    predictions = time_series_models._forecast_sequence_model(
        model,
        np.asarray([1.0, 2.0, 3.0, 100.0, 200.0]),
        np.asarray([
            [10.0, 10.0, 10.0, 10.0, 10.0],
            [20.0, 20.0, 20.0, 20.0, 20.0],
            [30.0, 30.0, 30.0, 30.0, 30.0],
            [400.0, 400.0, 400.0, 400.0, 400.0],
            [500.0, 500.0, 500.0, 500.0, 500.0],
        ]),
        split=3,
        sequence_length=2,
        target_center=0.0,
        target_scale=1.0,
        input_center=np.zeros(5),
        input_scale=np.ones(5),
        fixed_horizon=True,
    )

    assert predictions.tolist() == [3.0, 3.0]
    assert model.inputs[0][0, :, 0].tolist() == [2.0, 3.0]
    assert model.inputs[1][0, :, 0].tolist() == [3.0, 3.0]
    assert model.inputs[0][0, :, 1:6].tolist() == [[20.0] * 5, [30.0] * 5]
    assert model.inputs[1][0, :, 1:6].tolist() == [[30.0] * 5, [20.0] * 5]


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


def test_time_series_windows_adapt_to_seven_day_span():
    dataset_id = REGISTRY.register(pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=168, freq="h"), "y": range(168),
    }), {})
    result = handle_request("features/time_series/windows", {
        "dataset_id": dataset_id, "time_column": "ts",
    })
    statuses = {item["window_days"]: item["status"] for item in result["windows"]}
    assert result["observed_span_days"] == 167 / 24
    assert result["effective_span_days"] == 7
    assert statuses[3] == "available" and statuses[7] == "available"
    assert statuses[14] == "insufficient_history"


def test_time_series_windows_allow_ninety_day_span():
    dataset_id = REGISTRY.register(pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=91, freq="D"), "y": range(91),
    }), {})
    result = handle_request("features/time_series/windows", {
        "dataset_id": dataset_id, "time_column": "ts",
    })
    statuses = {item["window_days"]: item["status"] for item in result["windows"]}
    assert statuses[90] == "available"


def test_time_series_fit_persistence_is_explicit_and_registers_metadata():
    dataset_id = REGISTRY.register(pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=40, freq="h"),
        "x": range(40), "y": [10 + i * 0.1 for i in range(40)],
    }), {})
    params = {"dataset_id": dataset_id, "time_column": "ts", "target": "y", "inputs": ["x"], "lags": [1], "rolling_windows": [3]}
    result = handle_request("features/time_series/fit", params)
    assert result["provenance"]["persisted"] is False
    persisted = handle_request("features/time_series/fit", {**params, "persist_models": True})
    assert persisted["provenance"]["persisted"] is True
    assert persisted["provenance"]["model_ids"]
    for model_id in persisted["provenance"]["model_ids"].values():
        assert MODEL_REGISTRY.get(model_id).model is None


def test_time_series_fit_persists_only_selected_model_types():
    dataset_id = REGISTRY.register(pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=40, freq="h"),
        "x": range(40), "y": [10 + i * 0.1 for i in range(40)],
    }), {})
    result = handle_request("features/time_series/fit", {
        "dataset_id": dataset_id, "time_column": "ts", "target": "y", "inputs": ["x"],
        "lags": [1], "rolling_windows": [3], "persist_models": True,
        "persist_model_types": ["naive"],
    })
    assert set(result["provenance"]["model_ids"]) == {"naive"}
    assert result["results"][0]["persisted"] is True
    assert all(item.get("persisted") is not True for item in result["results"] if item["model_type"] != "naive")


def test_time_series_fit_rejects_invalid_persistence_selection():
    dataset_id = REGISTRY.register(pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=10, freq="h"), "y": range(10),
    }), {})
    for selection in ("naive", ["naive", 1], [""]):
        try:
            handle_request("features/time_series/fit", {
                "dataset_id": dataset_id, "time_column": "ts", "target": "y",
                "persist_models": True, "persist_model_types": selection,
            })
        except ValueError as exc:
            assert "persist_model_types" in str(exc)
        else:
            raise AssertionError("expected invalid persistence selection error")


def test_time_series_fit_reports_no_models_to_persist_for_unmatched_selection():
    dataset_id = REGISTRY.register(pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=40, freq="h"), "y": range(40),
    }), {})
    result = handle_request("features/time_series/fit", {
        "dataset_id": dataset_id, "time_column": "ts", "target": "y",
        "persist_models": True, "persist_model_types": ["missing_model"],
    })
    assert result["provenance"]["persisted"] is False
    assert result["provenance"]["persistence_status"] == "no_models_to_persist"


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
    # All currently implemented ladder adapters support recursive fixed-horizon
    # evaluation.  Optional adapters may still be unavailable when their
    # dependency is not installed, but they must never silently use the
    # observed test target.
    for item in result["results"]:
        if item["status"] == "available":
            assert item["evaluation"]["protocol"] == "fixed_horizon_forecast"
            assert item["evaluation"]["observed_target_usage"] == "training_only"
        else:
            assert item.get("reason_code") in {"dependency_missing", "adapter_error", "insufficient_history"}
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


def test_time_series_validation_gate_returns_chronological_fold_metrics():
    dataset_id = REGISTRY.register(pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=50, freq="h"),
        "y": [float(index) for index in range(50)],
    }), {})

    result = handle_request("features/time_series/validation_gate", {
        "dataset_id": dataset_id,
        "time_column": "ts",
        "target": "y",
        "inputs": [],
        "model_type": "naive",
        "evaluation_protocol": "fixed_horizon_forecast",
        "fold_count": 3,
        "horizon": 4,
    })

    assert len(result["folds"]) == 3
    assert [fold["train_rows"] for fold in result["folds"]] == [38, 42, 46]
    for fold in result["folds"]:
        assert fold["train_end"] < fold["validation_start"]
        assert fold["validation_rows"] == 4
        assert set(fold["metrics"]) == {"mae", "rmse", "r2"}
    assert set(result["aggregate_metrics"]) == {"mae", "rmse", "r2"}
    assert result["window_coverage"]["coverage_ratio"] == 1.0


def test_time_series_validation_gate_returns_uncertainty_metrics_schema():
    dataset_id = REGISTRY.register(pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=30, freq="h"),
        "y": [float(index) for index in range(30)],
    }), {})

    result = handle_request("features/time_series/validation_gate", {
        "dataset_id": dataset_id,
        "time_column": "ts",
        "target": "y",
        "inputs": [],
        "model_type": "naive",
        "evaluation_protocol": "fixed_horizon_forecast",
        "fold_count": 1,
        "horizon": 5,
        "prediction_interval_confidence": 0.9,
    })

    uncertainty = result["uncertainty_metrics"]
    assert set(uncertainty) == {
        "status", "method", "confidence", "residual_scale",
        "mean_interval_width", "calibration",
    }
    assert uncertainty["status"] == "available"
    assert uncertainty["method"] == "training_residual_normal"
    assert uncertainty["confidence"] == 0.9
    assert uncertainty["residual_scale"] == 1.0
    assert uncertainty["mean_interval_width"] > 0
    assert uncertainty["calibration"] == {
        "covered_rows": result["prediction_interval_coverage"]["covered_rows"],
        "evaluated_rows": result["prediction_interval_coverage"]["evaluated_rows"],
        "coverage_ratio": result["prediction_interval_coverage"]["coverage_ratio"],
    }


def test_time_series_validation_gate_fixed_horizon_naive_does_not_use_observed_targets():
    dataset_id = REGISTRY.register(pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=30, freq="h"),
        "y": [float(index) for index in range(30)],
    }), {})

    result = handle_request("features/time_series/validation_gate", {
        "dataset_id": dataset_id,
        "time_column": "ts",
        "target": "y",
        "inputs": [],
        "model_type": "naive",
        "evaluation_protocol": "fixed_horizon_forecast",
        "fold_count": 1,
        "horizon": 5,
    })

    assert result["folds"][0]["metrics"]["mae"] == 3.0
    assert math.isclose(result["folds"][0]["metrics"]["rmse"], math.sqrt(11))
    assert result["leakage_status"] == {
        "status": "passed",
        "evaluation_protocol": "fixed_horizon_forecast",
        "uses_observed_validation_targets": False,
    }


def test_time_series_validation_gate_reports_insufficient_history_without_metrics():
    dataset_id = REGISTRY.register(pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=8, freq="h"),
        "y": [float(index) for index in range(8)],
    }), {})

    result = handle_request("features/time_series/validation_gate", {
        "dataset_id": dataset_id,
        "time_column": "ts",
        "target": "y",
        "inputs": [],
        "model_type": "naive",
        "evaluation_protocol": "fixed_horizon_forecast",
        "fold_count": 2,
        "horizon": 2,
    })

    assert result["gate_status"] == "insufficient_history"
    assert "insufficient_history" in result["gate_reasons"]
    assert result["folds"] == []
    assert result["aggregate_metrics"] is None
    assert result["prediction_interval_coverage"]["status"] == "unavailable"


def test_time_series_validation_gate_approval_depends_on_interval_coverage():
    common = {
        "time_column": "ts",
        "target": "y",
        "inputs": [],
        "model_type": "naive",
        "evaluation_protocol": "fixed_horizon_forecast",
        "fold_count": 1,
        "horizon": 5,
        "minimum_prediction_interval_coverage": 0.8,
    }
    approved_id = REGISTRY.register(pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=30, freq="h"),
        "group": ["A", "B"] * 15,
        "y": [5.0] * 30,
    }), {})
    approved = handle_request("features/time_series/validation_gate", {
        "dataset_id": approved_id, "group_column": "group", **common,
    })
    assert approved["prediction_interval_coverage"]["coverage_ratio"] == 1.0
    assert approved["group_coverage"]["coverage_ratio"] == 1.0
    assert approved["gate_status"] == "approved"
    assert approved["gate_reasons"] == []

    review_id = REGISTRY.register(pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=30, freq="h"),
        "y": [0.0] * 25 + [100.0, -100.0, 50.0, -50.0, 0.0],
    }), {})
    review = handle_request("features/time_series/validation_gate", {
        "dataset_id": review_id, **common,
    })
    assert review["prediction_interval_coverage"]["coverage_ratio"] == 0.2
    assert review["gate_status"] == "needs_review"
    assert "prediction_interval_coverage_below_threshold" in review["gate_reasons"]


def test_validation_gate_fixed_horizon_ignores_validation_period_inputs():
    x_values = [float((index * 17) % 23 - 11) for index in range(60)]
    frame = pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=60, freq="h"),
        "x": x_values,
        "y": [0.0, *[2 * value for value in x_values[:-1]]],
    })
    original_id = REGISTRY.register(frame, {})
    changed = frame.copy()
    changed.loc[55:, "x"] = [1000.0, -1000.0, 500.0, -500.0, 250.0]
    changed_id = REGISTRY.register(changed, {})
    params = {
        "time_column": "ts", "target": "y", "inputs": ["x"],
        "model_type": "dynamic_regression",
        "evaluation_protocol": "fixed_horizon_forecast",
        "fold_count": 1, "horizon": 5, "lags": [1], "rolling_windows": [3],
    }

    original = handle_request(
        "features/time_series/validation_gate", {"dataset_id": original_id, **params}
    )
    perturbed = handle_request(
        "features/time_series/validation_gate", {"dataset_id": changed_id, **params}
    )

    assert perturbed["folds"] == original["folds"]
    assert perturbed["aggregate_metrics"] == original["aggregate_metrics"]
    assert perturbed["prediction_interval_coverage"] == original["prediction_interval_coverage"]

def test_validation_gate_transformer_runs_without_observed_validation_inputs():
    if importlib.util.find_spec("tensorflow") is None:
        pytest.skip("tensorflow is optional")
    frame = pd.read_csv(
        Path(__file__).parents[2] / "data/test_dataset_timeseries_transformer.csv"
    )
    input_columns = [
        "input_temperature", "input_voltage", "input_pressure",
        "input_speed", "input_load",
    ]
    original_id = REGISTRY.register(frame, {})
    changed = frame.copy()
    changed.loc[276:, input_columns] = 9999.0
    changed_id = REGISTRY.register(changed, {})
    params = {
        "time_column": "datetime", "target": "output_thickness",
        "inputs": input_columns, "model_type": "transformer",
        "evaluation_protocol": "fixed_horizon_forecast",
        "fold_count": 1, "horizon": 12,
    }

    original = handle_request(
        "features/time_series/validation_gate", {"dataset_id": original_id, **params}
    )
    perturbed = handle_request(
        "features/time_series/validation_gate", {"dataset_id": changed_id, **params}
    )

    assert len(original["folds"]) == 1
    assert set(original["aggregate_metrics"]) == {"mae", "rmse", "r2"}
    assert original["uncertainty_metrics"]["status"] == "available"
    assert original["leakage_status"] == {
        "status": "passed",
        "evaluation_protocol": "fixed_horizon_forecast",
        "uses_observed_validation_targets": False,
    }
    assert perturbed["folds"] == original["folds"]
    assert perturbed["aggregate_metrics"] == original["aggregate_metrics"]
    assert perturbed["prediction_interval_coverage"] == original["prediction_interval_coverage"]

    observed = handle_request("features/time_series/validation_gate", {
        "dataset_id": original_id,
        **{**params, "evaluation_protocol": "observed_feature_holdout"},
    })
    assert len(observed["folds"]) == 1
    assert observed["uncertainty_metrics"]["status"] == "available"
    assert observed["leakage_status"] == {
        "status": "needs_review",
        "evaluation_protocol": "observed_feature_holdout",
        "uses_observed_validation_targets": True,
    }


def test_validation_gate_missing_latest_targets_reduce_window_coverage():
    dataset_id = REGISTRY.register(pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=30, freq="h"),
        "y": [5.0] * 28 + [None, None],
    }), {})

    result = handle_request("features/time_series/validation_gate", {
        "dataset_id": dataset_id,
        "time_column": "ts",
        "target": "y",
        "inputs": [],
        "model_type": "naive",
        "evaluation_protocol": "fixed_horizon_forecast",
        "fold_count": 1,
        "horizon": 5,
    })

    assert result["gate_status"] == "needs_review"
    assert "validation_target_coverage_incomplete" in result["gate_reasons"]
    assert result["window_coverage"]["coverage_ratio"] == 0.6
    assert result["folds"] == []
    assert result["aggregate_metrics"] is None
