import math
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from process_intelligence_engine.main import REGISTRY, handle_request
from process_intelligence_engine.main import MODEL_REGISTRY
from process_intelligence_engine.modeling import time_series_models
from process_intelligence_engine.modeling.time_series_persistence import load_estimator


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
        ("temporal_fusion_transformer", 128, ["insufficient_history"]),
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
            "pytorch_forecasting", ["dependency_missing"],
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


def test_tft_capability_declares_data_contract_and_protocols(monkeypatch):
    original_find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name: None if name == "pytorch_forecasting" else original_find_spec(name),
    )
    frame = pd.read_csv(
        Path(__file__).parents[2] / "data/test_dataset_timeseries_transformer.csv"
    )
    dataset_id = REGISTRY.register(frame, {})
    input_columns = [
        "input_temperature", "input_voltage", "input_pressure",
        "input_speed", "input_load",
    ]
    result = handle_request("features/time_series/fit", {
        "dataset_id": dataset_id, "time_column": "datetime",
        "target": "output_thickness", "inputs": input_columns,
        "evaluation_protocol": "fixed_horizon_forecast",
        "lstm_sequence_length": 1000, "transformer_sequence_length": 1000,
        "tft_sequence_length": 24,
    })

    tft = next(item for item in result["results"] if item["model_type"] == "temporal_fusion_transformer")
    assert tft["status"] == "unavailable"
    assert tft["reason_code"] == "dependency_missing"
    assert tft["capability"]["backend"] == "pytorch"
    assert tft["capability"]["dependency"] == {
        "name": "pytorch_forecasting", "available": False,
    }
    assert tft["capability"]["reason_codes"] == ["dependency_missing"]
    assert tft["capability"]["data_contract"] == {
        "time_column": "datetime",
        "target": "output_thickness",
        "inputs": input_columns,
        "sequence_length": 24,
        "minimum_sequences": 128,
        "evaluation_protocol": "fixed_horizon_forecast",
        "supported_protocols": ["fixed_horizon_forecast", "observed_feature_holdout"],
    }


def test_tft_fits_when_dependency_and_sequence_requirements_are_met():
    if importlib.util.find_spec("pytorch_forecasting") is None:
        pytest.skip("pytorch_forecasting is optional")
    frame = pd.read_csv(
        Path(__file__).parents[2] / "data/test_dataset_timeseries_transformer.csv"
    )
    dataset_id = REGISTRY.register(frame, {})
    inputs = [
        "input_temperature", "input_voltage", "input_pressure",
        "input_speed", "input_load",
    ]
    result = handle_request("features/time_series/fit", {
        "dataset_id": dataset_id, "time_column": "datetime",
        "target": "output_thickness", "inputs": inputs,
        "evaluation_protocol": "fixed_horizon_forecast",
        "lstm_sequence_length": 1000, "transformer_sequence_length": 1000,
        "tft_sequence_length": 24,
    })
    tft = next(item for item in result["results"] if item["model_type"] == "temporal_fusion_transformer")
    assert tft["status"] == "available"
    assert tft["backend"] == "pytorch"
    assert tft["metrics"] is not None


def test_tft_persistence_uses_pytorch_artifact():
    if importlib.util.find_spec("pytorch_forecasting") is None:
        pytest.skip("pytorch_forecasting is optional")
    frame = pd.read_csv(Path(__file__).parents[2] / "data/test_dataset_timeseries_transformer.csv")
    dataset_id = REGISTRY.register(frame, {})
    inputs = ["input_temperature", "input_voltage", "input_pressure", "input_speed", "input_load"]
    result = handle_request("features/time_series/fit", {
        "dataset_id": dataset_id, "time_column": "datetime", "target": "output_thickness",
        "inputs": inputs, "evaluation_protocol": "fixed_horizon_forecast",
        "lstm_sequence_length": 1000, "transformer_sequence_length": 1000,
        "tft_sequence_length": 24, "persist_models": True,
        "persist_model_types": ["temporal_fusion_transformer"],
    })
    model_id = result["provenance"]["model_ids"]["temporal_fusion_transformer"]
    loaded = handle_request("features/time_series/load", {"dataset_id": dataset_id, "model_id": model_id})
    assert loaded["metadata"]["schema_version"] == "ts-tft-1"
    assert loaded["metadata"]["artifact_format"] == "pytorch"
    assert loaded["status"] == "loaded"


def test_tft_persistence_replays_predictions():
    if importlib.util.find_spec("pytorch_forecasting") is None:
        pytest.skip("pytorch_forecasting is optional")
    frame = pd.read_csv(Path(__file__).parents[2] / "data/test_dataset_timeseries_transformer.csv")
    dataset_id = REGISTRY.register(frame, {})
    inputs = ["input_temperature", "input_voltage", "input_pressure", "input_speed", "input_load"]
    result = handle_request("features/time_series/fit", {
        "dataset_id": dataset_id, "time_column": "datetime", "target": "output_thickness",
        "inputs": inputs, "evaluation_protocol": "fixed_horizon_forecast",
        "lstm_sequence_length": 1000, "transformer_sequence_length": 1000,
        "tft_sequence_length": 24, "persist_models": True,
        "persist_model_types": ["temporal_fusion_transformer"],
    })
    model_id = result["provenance"]["model_ids"]["temporal_fusion_transformer"]
    replayed = handle_request("features/time_series/predict", {"dataset_id": dataset_id, "model_id": model_id})
    assert replayed["success"] is True
    assert replayed["predictions"]


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
    assert transformer["backend"] == "tensorflow"
    assert transformer["framework_version"]
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


def test_time_series_transformer_persistence_replays_without_future_values():
    if importlib.util.find_spec("tensorflow") is None:
        pytest.skip("tensorflow is optional")
    frame = pd.read_csv(
        Path(__file__).parents[2] / "data/test_dataset_timeseries_transformer.csv"
    )
    input_columns = [
        "input_temperature", "input_voltage", "input_pressure",
        "input_speed", "input_load",
    ]
    dataset_id = REGISTRY.register(frame, {})
    result = handle_request("features/time_series/fit", {
        "dataset_id": dataset_id, "time_column": "datetime",
        "target": "output_thickness", "inputs": input_columns,
        "evaluation_protocol": "fixed_horizon_forecast",
        "lstm_sequence_length": 1000, "transformer_sequence_length": 24,
        "persist_models": True, "persist_model_types": ["transformer"],
        "validation_gate_evidence": {"transformer": {"gate_status": "approved"}},
    })
    model_id = result["provenance"]["model_ids"]["transformer"]

    loaded = handle_request("features/time_series/load", {
        "dataset_id": dataset_id, "model_id": model_id,
    })
    metadata = loaded["metadata"]
    assert metadata["schema_version"] == "ts-transformer-1"
    assert metadata["model_type"] == "time_series_transformer"
    assert metadata["backend"] == "tensorflow"
    assert metadata["framework_version"]
    assert metadata["replay"]["sequence_length"] == 24
    assert metadata["validation_gate_evidence"] == {"gate_status": "approved"}

    original = handle_request("features/time_series/predict", {
        "dataset_id": dataset_id, "model_id": model_id,
    })
    changed = frame.copy()
    training_end = pd.Timestamp(result["training_time_range"]["end"])
    future = pd.to_datetime(changed["datetime"], utc=True) > training_end
    changed.loc[future, [*input_columns, "output_thickness"]] = 9999.0
    changed_id = REGISTRY.register(changed, {})
    replayed = handle_request("features/time_series/predict", {
        "dataset_id": changed_id, "model_id": model_id,
    })

    assert replayed["predictions"] == original["predictions"]


def test_time_series_experiment_validation_replays_metadata_without_observed_leakage():
    if importlib.util.find_spec("tensorflow") is None:
        pytest.skip("tensorflow is optional")
    frame = pd.read_csv(
        Path(__file__).parents[2] / "data/test_dataset_timeseries_transformer.csv"
    )
    input_columns = [
        "input_temperature", "input_voltage", "input_pressure",
        "input_speed", "input_load",
    ]
    dataset_id = REGISTRY.register(frame, {})
    fitted = handle_request("features/time_series/fit", {
        "dataset_id": dataset_id, "time_column": "datetime",
        "target": "output_thickness", "inputs": input_columns,
        "evaluation_protocol": "fixed_horizon_forecast",
        "lstm_sequence_length": 1000, "transformer_sequence_length": 24,
        "persist_models": True, "persist_model_types": ["transformer"],
        "validation_gate_evidence": {"transformer": {"gate_status": "approved"}},
    })
    model_id = fitted["provenance"]["model_ids"]["transformer"]
    metadata = handle_request("features/time_series/load", {
        "dataset_id": dataset_id, "model_id": model_id,
    })["metadata"]
    training_end = pd.Timestamp(fitted["training_time_range"]["end"])
    timestamps = pd.to_datetime(frame["datetime"], utc=True)
    history = frame.loc[timestamps <= training_end].to_dict("records")
    observed = frame.loc[timestamps > training_end].head(4).to_dict("records")

    result = handle_request("features/time_series/experiment_validation", {
        "model_id": model_id, "model_metadata": metadata,
        "history_rows": history, "observed_rows": observed,
    })

    assert result["status"] == "validated"
    assert result["metrics"]["mae"] >= 0
    assert result["metrics"]["rmse"] >= 0
    assert len(result["rows"]) == len(observed)
    assert set(result["rows"][0]) == {"timestamp", "predicted", "observed", "delta"}
    assert result["metadata"] == {
        key: metadata[key]
        for key in (
            "model_id", "model_type", "schema_version", "target", "inputs",
            "time_column", "evaluation_protocol", "backend", "framework_version",
        )
    }
    changed = [{**row, "output_thickness": 9999.0, **{column: 9999.0 for column in input_columns}} for row in observed]
    replayed = handle_request("features/time_series/experiment_validation", {
        "model_id": model_id, "model_metadata": metadata,
        "history_rows": history, "observed_rows": changed,
    })
    assert [row["predicted"] for row in replayed["rows"]] == [row["predicted"] for row in result["rows"]]
    assert replayed["metrics"]["mae"] != result["metrics"]["mae"]


def test_time_series_experiment_validation_rejects_metadata_version_mismatch():
    with pytest.raises(ValueError, match="metadata does not match"):
        handle_request("features/time_series/experiment_validation", {
            "model_id": "unknown",
            "model_metadata": {"schema_version": "ts-estimator-1"},
            "history_rows": [], "observed_rows": [],
        })


def test_time_series_retrain_compare_creates_unapproved_candidate_without_replacing_model():
    if importlib.util.find_spec("tensorflow") is None:
        pytest.skip("tensorflow is optional")
    frame = pd.read_csv(
        Path(__file__).parents[2] / "data/test_dataset_timeseries_transformer.csv"
    )
    input_columns = [
        "input_temperature", "input_voltage", "input_pressure",
        "input_speed", "input_load",
    ]
    dataset_id = REGISTRY.register(frame, {})
    fitted = handle_request("features/time_series/fit", {
        "dataset_id": dataset_id, "time_column": "datetime",
        "target": "output_thickness", "inputs": input_columns,
        "evaluation_protocol": "fixed_horizon_forecast",
        "lstm_sequence_length": 1000, "transformer_sequence_length": 24,
        "persist_models": True, "persist_model_types": ["transformer"],
        "validation_gate_evidence": {"transformer": {"gate_status": "approved"}},
    })
    model_id = fitted["provenance"]["model_ids"]["transformer"]
    metadata = handle_request("features/time_series/load", {
        "dataset_id": dataset_id, "model_id": model_id,
    })["metadata"]
    training_end = pd.Timestamp(fitted["training_time_range"]["end"])
    timestamps = pd.to_datetime(frame["datetime"], utc=True)
    history = frame.loc[timestamps <= training_end].to_dict("records")
    new_observed = frame.loc[timestamps > training_end].head(8).to_dict("records")
    prior_version = MODEL_REGISTRY.get(model_id).version

    result = handle_request("features/time_series/retrain_compare", {
        "model_id": model_id, "model_metadata": metadata,
        "history_rows": history, "new_observed_rows": new_observed,
    })

    assert result["status"] == "candidate_created"
    assert result["candidate"]["version"] == prior_version + 1
    assert result["candidate"]["status"] == "draft"
    assert result["candidate"]["persisted"] is False
    assert result["gate"]["status"] == "needs_review"
    assert result["before_metrics"]["mae"] >= 0
    assert result["after_metrics"]["rmse"] >= 0
    assert set(result["delta_metrics"]) == {"mae", "rmse"}
    assert result["provenance"] == {
        "source_model_id": model_id, "source_model_version": prior_version,
        "schema_version": "ts-transformer-1", "backend": "tensorflow",
        "framework_version": metadata["framework_version"],
        "evaluation_protocol": "fixed_horizon_forecast",
    }
    assert MODEL_REGISTRY.get(model_id).version == prior_version
    assert MODEL_REGISTRY.get(model_id).status == "draft"


def test_time_series_retrain_candidate_review_requires_gate_then_persists_new_version():
    if importlib.util.find_spec("tensorflow") is None:
        pytest.skip("tensorflow is optional")
    frame = pd.read_csv(
        Path(__file__).parents[2] / "data/test_dataset_timeseries_transformer.csv"
    )
    input_columns = [
        "input_temperature", "input_voltage", "input_pressure",
        "input_speed", "input_load",
    ]
    dataset_id = REGISTRY.register(frame, {})
    fitted = handle_request("features/time_series/fit", {
        "dataset_id": dataset_id, "time_column": "datetime",
        "target": "output_thickness", "inputs": input_columns,
        "evaluation_protocol": "fixed_horizon_forecast",
        "lstm_sequence_length": 1000, "transformer_sequence_length": 24,
        "persist_models": True, "persist_model_types": ["transformer"],
        "validation_gate_evidence": {"transformer": {"gate_status": "approved"}},
    })
    model_id = fitted["provenance"]["model_ids"]["transformer"]
    metadata = handle_request("features/time_series/load", {
        "dataset_id": dataset_id, "model_id": model_id,
    })["metadata"]
    training_end = pd.Timestamp(fitted["training_time_range"]["end"])
    timestamps = pd.to_datetime(frame["datetime"], utc=True)
    candidate = handle_request("features/time_series/retrain_compare", {
        "model_id": model_id, "model_metadata": metadata,
        "history_rows": frame.loc[timestamps <= training_end].to_dict("records"),
        "new_observed_rows": frame.loc[timestamps > training_end].head(8).to_dict("records"),
    })["candidate"]

    with pytest.raises(ValueError, match="approved gate evidence"):
        handle_request("features/time_series/retrain_review", {
            "candidate_id": candidate["candidate_id"], "decision": "approve",
            "reviewer": "qa", "reason": "metrics reviewed",
            "gate_evidence": {"gate_status": "needs_review"},
        })
    approved = handle_request("features/time_series/retrain_review", {
        "candidate_id": candidate["candidate_id"], "decision": "approve",
        "reviewer": "qa", "reason": "independent evidence accepted",
        "gate_evidence": {"gate_status": "approved", "evidence_id": "gate-42"},
    })

    assert approved["status"] == "persisted_for_validation"
    assert approved["model_id"] != model_id
    assert approved["model_status"] == "validated"
    assert approved["review"] == {
        "reviewer": "qa", "decision": "approve",
        "reason": "independent evidence accepted",
        "gate_evidence": {"gate_status": "approved", "evidence_id": "gate-42"},
    }
    assert MODEL_REGISTRY.get(model_id).status == "draft"
    assert MODEL_REGISTRY.get(approved["model_id"]).status == "validated"


def test_time_series_final_risk_gate_blocks_unreviewed_and_requires_sequence_simulation():
    if importlib.util.find_spec("tensorflow") is None:
        pytest.skip("tensorflow is optional")
    frame = pd.read_csv(
        Path(__file__).parents[2] / "data/test_dataset_timeseries_transformer.csv"
    )
    input_columns = [
        "input_temperature", "input_voltage", "input_pressure",
        "input_speed", "input_load",
    ]
    dataset_id = REGISTRY.register(frame, {})
    fitted = handle_request("features/time_series/fit", {
        "dataset_id": dataset_id, "time_column": "datetime",
        "target": "output_thickness", "inputs": input_columns,
        "evaluation_protocol": "fixed_horizon_forecast",
        "lstm_sequence_length": 1000, "transformer_sequence_length": 24,
        "persist_models": True, "persist_model_types": ["transformer"],
        "validation_gate_evidence": {"transformer": {"gate_status": "approved"}},
    })
    source_id = fitted["provenance"]["model_ids"]["transformer"]
    metadata = handle_request("features/time_series/load", {
        "dataset_id": dataset_id, "model_id": source_id,
    })["metadata"]
    blocked = handle_request("features/time_series/risk_use_gate", {
        "model_id": source_id, "dataset_id": dataset_id,
    })
    assert blocked["status"] == "blocked"
    assert "model_not_validated" in blocked["reasons"]

    training_end = pd.Timestamp(fitted["training_time_range"]["end"])
    timestamps = pd.to_datetime(frame["datetime"], utc=True)
    candidate = handle_request("features/time_series/retrain_compare", {
        "model_id": source_id, "model_metadata": metadata,
        "history_rows": frame.loc[timestamps <= training_end].to_dict("records"),
        "new_observed_rows": frame.loc[timestamps > training_end].head(8).to_dict("records"),
    })["candidate"]
    approved = handle_request("features/time_series/retrain_review", {
        "candidate_id": candidate["candidate_id"], "decision": "approve",
        "reviewer": "qa", "reason": "risk review complete",
        "gate_evidence": {"gate_status": "approved", "evidence_id": "gate-99"},
    })
    gate = handle_request("features/time_series/risk_use_gate", {
        "model_id": approved["model_id"], "dataset_id": dataset_id,
    })
    assert gate["status"] == "approved"
    assert gate["provenance"]["model_version"] == MODEL_REGISTRY.get(approved["model_id"]).version
    assert gate["provenance"]["backend"] == "tensorflow"

    monte_carlo = handle_request("monte_carlo/run", {
        "dataset_id": dataset_id, "model_id": approved["model_id"],
    })
    assert monte_carlo == {
        "success": False, "status": "not_supported",
        "reason": "needs_sequence_simulation", "model_id": approved["model_id"],
        "final_gate": gate,
    }
    copula = handle_request("copula/joint", {"model_id": approved["model_id"], "dataset_id": dataset_id})
    assert copula["status"] == "not_supported"
    assert copula["reason"] == "needs_sequence_simulation"


def test_time_series_sequence_simulation_uses_scenarios_and_recursive_predictions_only():
    if importlib.util.find_spec("tensorflow") is None:
        pytest.skip("tensorflow is optional")
    frame = pd.read_csv(
        Path(__file__).parents[2] / "data/test_dataset_timeseries_transformer.csv"
    )
    input_columns = [
        "input_temperature", "input_voltage", "input_pressure",
        "input_speed", "input_load",
    ]
    dataset_id = REGISTRY.register(frame, {})
    fitted = handle_request("features/time_series/fit", {
        "dataset_id": dataset_id, "time_column": "datetime",
        "target": "output_thickness", "inputs": input_columns,
        "evaluation_protocol": "fixed_horizon_forecast",
        "lstm_sequence_length": 1000, "transformer_sequence_length": 24,
        "persist_models": True, "persist_model_types": ["transformer"],
        "validation_gate_evidence": {"transformer": {"gate_status": "approved"}},
    })
    source_id = fitted["provenance"]["model_ids"]["transformer"]
    metadata = handle_request("features/time_series/load", {
        "dataset_id": dataset_id, "model_id": source_id,
    })["metadata"]
    training_end = pd.Timestamp(fitted["training_time_range"]["end"])
    timestamps = pd.to_datetime(frame["datetime"], utc=True)
    history_rows = frame.loc[timestamps <= training_end].to_dict("records")
    source_gate = handle_request("features/time_series/risk_use_gate", {
        "model_id": source_id, "dataset_id": dataset_id,
    })
    assert source_gate["status"] == "blocked"
    assert "model_not_validated" in source_gate["reasons"]
    candidate = handle_request("features/time_series/retrain_compare", {
        "model_id": source_id, "model_metadata": metadata,
        "history_rows": history_rows,
        "new_observed_rows": frame.loc[timestamps > training_end].head(8).to_dict("records"),
    })["candidate"]
    with pytest.raises(ValueError, match="approved gate evidence"):
        handle_request("features/time_series/retrain_review", {
            "candidate_id": candidate["candidate_id"], "decision": "approve",
            "reviewer": "qa", "reason": "missing evidence",
            "gate_evidence": {"gate_status": "needs_review"},
        })
    approved = handle_request("features/time_series/retrain_review", {
        "candidate_id": candidate["candidate_id"], "decision": "approve",
        "reviewer": "qa", "reason": "sequence risk review complete",
        "gate_evidence": {"gate_status": "approved", "evidence_id": "gate-100"},
    })
    scenarios = frame.loc[timestamps > training_end, ["datetime", *input_columns]].head(3).to_dict("records")

    result = handle_request("features/time_series/sequence_simulation", {
        "model_id": approved["model_id"], "dataset_id": dataset_id,
        "history_rows": history_rows, "input_scenarios": scenarios, "horizon": 3,
    })

    assert result["status"] == "dry_run"
    assert result["history_window"]["rows"] == len(history_rows)
    assert result["history_window"]["sequence_length"] == 24
    assert result["scenario_provenance"] == {
        "rows": 3, "input_columns": input_columns,
        "target_usage": "not_accepted", "forecast_mode": "recursive_predictions_only",
    }
    assert [row["timestamp"] for row in result["predictions"]] == [
        pd.Timestamp(scenario["datetime"]).isoformat() for scenario in scenarios
    ]
    assert all(math.isfinite(row["predicted"]) for row in result["predictions"])
    assert result["uncertainty"]["status"] == "not_available"
    assert result["uncertainty"]["reason"] == "deterministic_dry_run"

    stochastic_params = {
        "model_id": approved["model_id"], "dataset_id": dataset_id,
        "history_rows": history_rows, "input_scenarios": scenarios, "horizon": 3,
        "simulation_mode": "sequence_stochastic", "seed": 17, "n_simulations": 12,
        "observed_rows": frame.loc[timestamps > training_end, ["datetime", "output_thickness"]].head(3).to_dict("records"),
    }
    stochastic = handle_request("features/time_series/sequence_simulation", stochastic_params)
    repeated = handle_request("features/time_series/sequence_simulation", stochastic_params)
    assert stochastic["status"] == "stochastic"
    assert stochastic["summary"] == repeated["summary"]
    assert stochastic["simulation"] == {
        "mode": "sequence_stochastic", "seed": 17, "n_simulations": 12,
        "residual_method": "training_history_recursive_residuals",
    }
    assert len(stochastic["summary"]) == 3
    assert set(stochastic["summary"][0]) == {"timestamp", "mean", "p05", "p50", "p95"}
    assert stochastic["interval_coverage"] == {
        "status": "not_available", "reason": "future_observations_required", "confidence": 0.9,
    }
    assert stochastic["calibration"]["status"] == "available"
    assert stochastic["calibration"]["nominal_confidence"] == 0.9
    assert stochastic["calibration"]["overall_coverage"] is not None
    assert len(stochastic["calibration"]["steps"]) == 3

    unsupported = handle_request("features/time_series/sequence_simulation", {
        "model_id": approved["model_id"], "dataset_id": dataset_id,
        "history_rows": history_rows, "input_scenarios": scenarios, "horizon": 3,
        "simulation_mode": "independent",
    })
    assert unsupported["status"] == "not_supported"
    assert unsupported["reason"] == "needs_sequence_simulation"


def test_time_series_load_rejects_unknown_persistence_metadata_version(tmp_path):
    directory = tmp_path / "models" / "time_series"
    directory.mkdir(parents=True)
    (directory / "unknown.json").write_text(json.dumps({"schema_version": "unknown"}))

    with pytest.raises(ValueError, match="metadata version"):
        load_estimator(tmp_path, "unknown", df=pd.DataFrame())


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
