import warnings

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LinearRegression

from process_intelligence_engine import main as app
from process_intelligence_engine.features.time_series_modeling import build_time_features


@pytest.fixture
def explanation_request(monkeypatch):
    rows = 96
    hour = np.arange(rows, dtype=float)
    x = np.sin(hour / 6.0) + hour / 50.0
    y = 12.0 + 0.65 * hour + 3.0 * x
    frame = pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=rows, freq="h"),
        "x": x,
        "y": y,
    })
    featured = build_time_features(frame, "ts", ["y", "x"], [1], [3])["data"]
    feature_names = ["y_lag_1", "x_rolling_mean_3", "hour"]
    estimator = LinearRegression().fit(
        featured[feature_names].to_numpy(dtype=float),
        featured["y"].to_numpy(dtype=float),
    )
    metadata = {
        "model_id": "ts-model-1",
        "model_type": "time_series_dynamic_regression",
        "dataset_id": "dataset-1",
        "target": "y",
        "inputs": ["x"],
        "time_column": "ts",
        "feature_names": feature_names,
        "feature_configuration": {
            "lags": [1],
            "rolling_windows": [3],
            "modeling_timezone": "UTC",
        },
        "evaluation_protocol": "fixed_horizon_forecast",
    }
    dataset_id = app.REGISTRY.register(frame, {})
    monkeypatch.setattr(app, "load_estimator", lambda *args, **kwargs: (estimator, metadata))
    return {
        "dataset_id": dataset_id,
        "model_id": metadata["model_id"],
        "random_seed": 7,
        "block_size": 8,
    }


def test_time_series_explanation_labels_engineered_feature_provenance(explanation_request):
    result = app.handle_request("modeling/time_series/explain", explanation_request)

    features = {item["name"]: item for item in result["feature_importance"]["features"]}
    assert features["y_lag_1"]["provenance"] == {
        "kind": "lag",
        "source_column": "y",
        "lag": 1,
        "window": None,
        "availability": "historical_only",
    }
    assert features["x_rolling_mean_3"]["provenance"] == {
        "kind": "rolling_mean",
        "source_column": "x",
        "lag": None,
        "window": 3,
        "availability": "historical_only",
    }
    assert features["hour"]["provenance"] == {
        "kind": "calendar_hour",
        "source_column": "ts",
        "lag": None,
        "window": None,
        "availability": "prediction_timestamp",
    }
    assert result["feature_importance"]["shap_compatible"] is True


def test_time_series_explanation_reports_block_perturbation_and_conditional_interactions(explanation_request):
    result = app.handle_request("modeling/time_series/explain", explanation_request)

    sensitivity = result["sensitivity"]
    assert sensitivity["method"] == "chronological_block_permutation"
    assert sensitivity["block_size"] == 8
    assert sensitivity["random_seed"] == 7
    assert {item["name"] for item in sensitivity["features"]} == {
        "y_lag_1", "x_rolling_mean_3", "hour",
    }
    assert all(item["mae_increase"] is not None for item in sensitivity["features"])

    interactions = result["interactions"]
    assert interactions["method"] == "conditional_quantile_perturbation"
    assert interactions["conditioning"] == "within_feature_quantile_strata"
    assert len(interactions["pairs"]) == 3
    assert all(item["evidence_status"] == "model_inferred" for item in interactions["pairs"])


def test_time_series_explanation_never_presents_model_evidence_as_causal(explanation_request):
    result = app.handle_request("modeling/time_series/explain", explanation_request)

    assert result["metadata"] == {
        "analysis_type": "time_series_explanation",
        "evidence_status": "model_inferred",
        "causal_claim": False,
        "interpretation": "predictive_association_only",
        "requires_experimental_confirmation": True,
        "recommended_confirmation": "targeted_doe_or_engineering_experiment",
        "evaluation_protocol": "fixed_horizon_forecast",
    }


def test_time_series_explanation_matches_numpy_trained_estimator_input(explanation_request):
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        app.handle_request("modeling/time_series/explain", explanation_request)

    assert not [
        warning for warning in captured
        if "X has feature names" in str(warning.message)
    ]
