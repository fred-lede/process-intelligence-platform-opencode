import numpy as np
import pandas as pd
import pytest

from process_intelligence_engine.features.time_series_modeling import (
    build_time_features,
    check_feature_timestamp_leakage,
    prepare_time_series,
    time_split,
    walk_forward_splits,
)
from process_intelligence_engine.main import REGISTRY, handle_request


def test_prepare_time_series_sorts_and_reports_duplicates():
    df = pd.DataFrame(
        {
            "ts": ["2026-01-02", "2026-01-01", "2026-01-01"],
            "x": [2, 1, 3],
        }
    )

    result = prepare_time_series(df, "ts")

    assert result["data"]["ts"].is_monotonic_increasing
    assert result["quality"]["duplicate_timestamps"] == 1


def test_prepare_time_series_rejects_missing_time_column():
    with pytest.raises(ValueError, match="Unknown time column: missing"):
        prepare_time_series(pd.DataFrame({"ts": ["2026-01-01"]}), "missing")


def test_prepare_time_series_rejects_parse_errors():
    with pytest.raises(ValueError, match="contains 1 non-datetime value"):
        prepare_time_series(
            pd.DataFrame({"ts": ["2026-01-01", "not-a-timestamp"]}),
            "ts",
        )


def test_prepare_time_series_reports_interval_summary():
    result = prepare_time_series(
        pd.DataFrame({"ts": ["2026-01-04", "2026-01-01", "2026-01-02"]}),
        "ts",
    )

    assert result["quality"]["interval_summary"] == {
        "count": 2,
        "min_seconds": 86400.0,
        "median_seconds": 129600.0,
        "max_seconds": 172800.0,
    }


def test_prepare_time_series_preserves_source_timezone_evidence():
    result = prepare_time_series(
        pd.DataFrame(
            {
                "ts": [
                    "2026-01-01T00:00:00+08:00",
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:00:00",
                ]
            }
        ),
        "ts",
    )

    assert result["quality"]["timezone"] == "mixed"
    assert result["quality"]["timezone_representations"] == [
        "UTC",
        "UTC+08:00",
        "naive",
    ]
    assert result["quality"]["timezone_errors"] == 1
    assert result["quality"]["normalized_timezone"] == "UTC"


def test_time_series_model_handler_reports_missing_timestamps_and_row_count():
    dataset_id = REGISTRY.register(
        pd.DataFrame(
            {
                "ts": ["2026-01-02", None, "2026-01-01"],
                "target": [20, 30, 10],
                "input": [2, 3, 1],
            }
        ),
        {},
    )

    result = handle_request(
        "features/time_series/model",
        {
            "dataset_id": dataset_id,
            "time_column": "ts",
            "target": "target",
            "inputs": ["input"],
        },
    )

    assert result["sorted_row_count"] == 3
    assert result["quality"]["missing_timestamps"] == 1
    assert result["quality"]["excluded_undated_rows"] == 0
    assert result["dataset_id"] == dataset_id
    assert result["time_column"] == "ts"
    assert result["target"] == "target"
    assert result["inputs"] == ["input"]


@pytest.mark.parametrize(
    ("updates", "missing_column"),
    [
        ({"time_column": "unknown_time"}, "unknown_time"),
        ({"target": "unknown_target"}, "unknown_target"),
        ({"inputs": ["input", "unknown_input"]}, "unknown_input"),
    ],
)
def test_time_series_model_handler_rejects_unknown_columns(updates, missing_column):
    dataset_id = REGISTRY.register(
        pd.DataFrame(
            {
                "ts": ["2026-01-01", "2026-01-02"],
                "target": [10, 20],
                "input": [1, 2],
            }
        ),
        {},
    )
    params = {
        "dataset_id": dataset_id,
        "time_column": "ts",
        "target": "target",
        "inputs": ["input"],
        **updates,
    }

    with pytest.raises(ValueError, match=missing_column):
        handle_request("features/time_series/model", params)


def test_build_time_features_uses_only_prior_values_for_history_features():
    df = pd.DataFrame(
        {
            "ts": pd.date_range("2026-01-05 08:00", periods=4, freq="h"),
            "x": [10.0, 20.0, 22.0, 999.0],
        }
    )

    result = build_time_features(df, "ts", ["x"], [1], [2])

    assert result["feature_names"] == [
        "x_lag_1",
        "x_rolling_mean_2",
        "x_rolling_std_2",
        "x_first_difference",
        "x_rate_of_change",
        "hour",
        "weekday",
    ]
    assert result["dropped_warmup_rows"] == 2
    assert result["data"]["x_lag_1"].tolist() == [20.0, 22.0]
    assert result["data"]["x_rolling_mean_2"].tolist() == [15.0, 21.0]
    assert result["data"]["x_rolling_std_2"].tolist() == pytest.approx(
        [7.0710678119, 1.4142135624]
    )
    assert result["data"]["x_first_difference"].tolist() == [10.0, 2.0]
    assert result["data"]["x_rate_of_change"].tolist() == pytest.approx([1.0, 0.1])
    assert result["data"]["hour"].tolist() == [10, 11]
    assert result["data"]["weekday"].tolist() == [0, 0]


def test_build_time_features_does_not_change_earlier_rows_when_future_changes():
    base = pd.DataFrame(
        {
            "ts": pd.date_range("2026-01-01", periods=5, freq="D"),
            "x": [1.0, 2.0, 3.0, 4.0, 5.0],
        }
    )
    changed_future = base.copy()
    changed_future.loc[4, "x"] = 5000.0

    before = build_time_features(base, "ts", ["x"], [1], [2])["data"]
    after = build_time_features(changed_future, "ts", ["x"], [1], [2])["data"]

    feature_columns = [column for column in before if column not in {"ts", "x"}]
    pd.testing.assert_frame_equal(
        before[feature_columns],
        after[feature_columns],
    )
    assert after.iloc[-1]["x_lag_1"] == 4.0


def test_build_time_features_warns_for_missing_values_and_irregular_intervals():
    result = build_time_features(
        pd.DataFrame(
            {
                "ts": ["2026-01-01", "2026-01-02", "2026-01-04", "2026-01-05"],
                "x": [1.0, None, 3.0, 4.0],
            }
        ),
        "ts",
        ["x"],
        [1],
        [2],
    )

    assert set(result["warnings"]) == {"irregular_intervals", "missing_values:x"}


def test_time_series_model_handler_uses_daily_defaults_and_accepts_explicit_lists():
    dataset_id = REGISTRY.register(
        pd.DataFrame(
            {
                "ts": pd.date_range("2026-01-01", periods=10, freq="D"),
                "target": range(10),
                "input": range(10, 20),
            }
        ),
        {},
    )
    base_params = {
        "dataset_id": dataset_id,
        "time_column": "ts",
        "target": "target",
        "inputs": ["input"],
    }

    defaults = handle_request("features/time_series/model", base_params)
    explicit = handle_request(
        "features/time_series/model",
        {**base_params, "lags": [2], "rolling_windows": [3]},
    )

    assert defaults["feature_configuration"] == {
        "columns": ["target", "input"],
        "target": "target",
        "inputs": ["input"],
        "lags": [1, 7],
        "rolling_windows": [7],
        "frequency": "daily",
        "calendar_timezone": "source_local_naive",
    }
    assert explicit["feature_configuration"] == {
        "columns": ["target", "input"],
        "target": "target",
        "inputs": ["input"],
        "lags": [2],
        "rolling_windows": [3],
        "frequency": "daily",
        "calendar_timezone": "source_local_naive",
    }


def test_build_time_features_rejects_rolling_window_one():
    df = pd.DataFrame(
        {"ts": pd.date_range("2026-01-01", periods=3, freq="D"), "x": [1, 2, 3]}
    )

    with pytest.raises(ValueError, match="rolling_windows must be at least 2"):
        build_time_features(df, "ts", ["x"], [1], [1])


def test_build_time_features_reports_warmup_and_invalid_drops_separately():
    result = build_time_features(
        pd.DataFrame(
            {
                "ts": pd.date_range("2026-01-01", periods=5, freq="D"),
                "x": [1.0, 2.0, None, 4.0, 5.0],
            }
        ),
        "ts",
        ["x"],
        [1],
        [2],
    )

    assert result["dropped_warmup_rows"] == 2
    assert result["dropped_invalid_rows"] == 2


def test_build_time_features_drops_zero_denominator_rate_as_non_finite():
    result = build_time_features(
        pd.DataFrame(
            {
                "ts": pd.date_range("2026-01-01", periods=4, freq="D"),
                "x": [0.0, 1.0, 2.0, 3.0],
            }
        ),
        "ts",
        ["x"],
        [1],
        [2],
    )

    assert result["dropped_warmup_rows"] == 2
    assert result["dropped_invalid_rows"] == 1
    assert np.isfinite(result["data"]["x_rate_of_change"]).all()


def test_build_time_features_uses_source_local_calendar_and_explicit_timezone():
    df = pd.DataFrame(
        {
            "ts": pd.date_range(
                "2026-01-01 08:00", periods=4, freq="h", tz="Asia/Bangkok"
            ),
            "x": [1.0, 2.0, 3.0, 4.0],
        }
    )

    source_local = build_time_features(df, "ts", ["x"], [1], [2])
    new_york = build_time_features(
        df,
        "ts",
        ["x"],
        [1],
        [2],
        modeling_timezone="America/New_York",
    )

    assert source_local["data"]["hour"].tolist() == [10, 11]
    assert source_local["configuration"]["calendar_timezone"] == "Asia/Bangkok"
    assert new_york["data"]["hour"].tolist() == [22, 23]
    assert new_york["data"]["weekday"].tolist() == [2, 2]
    assert new_york["configuration"]["calendar_timezone"] == "America/New_York"


def test_time_series_model_handler_uses_minute_frequency_defaults():
    dataset_id = REGISTRY.register(
        pd.DataFrame(
            {
                "ts": pd.date_range("2026-01-01", periods=65, freq="min"),
                "target": range(65),
                "input": range(65),
            }
        ),
        {},
    )

    result = handle_request(
        "features/time_series/model",
        {
            "dataset_id": dataset_id,
            "time_column": "ts",
            "target": "target",
            "inputs": ["input"],
        },
    )

    assert result["feature_configuration"] == {
        "columns": ["target", "input"],
        "target": "target",
        "inputs": ["input"],
        "lags": [1, 60],
        "rolling_windows": [60],
        "frequency": "minute",
        "calendar_timezone": "source_local_naive",
    }


def test_time_series_model_handler_applies_trailing_day_window_and_snapshots_inputs():
    dataset_id = REGISTRY.register(
        pd.DataFrame(
            {
                "ts": pd.date_range("2026-01-01", periods=100, freq="D"),
                "target": range(100),
                "input": range(100, 200),
            }
        ),
        {},
    )
    params = {
        "dataset_id": dataset_id,
        "time_column": "ts",
        "target": "target",
        "inputs": ["input"],
        "lags": [1],
        "rolling_windows": [2],
    }

    seven_days = handle_request(
        "features/time_series/model", {**params, "window_days": 7}
    )
    ninety_days = handle_request(
        "features/time_series/model", {**params, "window_days": 90}
    )

    assert seven_days["sorted_row_count"] == 7
    assert ninety_days["sorted_row_count"] == 90
    assert seven_days["feature_configuration"]["target"] == "target"
    assert seven_days["feature_configuration"]["inputs"] == ["input"]
    assert seven_days["feature_configuration"]["window_days"] == 7
    assert seven_days["feature_configuration"]["window_start"] == "2026-04-04T00:00:00Z"
    assert seven_days["feature_configuration"]["window_end"] == "2026-04-10T00:00:00Z"


def test_time_series_model_handler_reports_quality_for_selected_window_only():
    dataset_id = REGISTRY.register(
        pd.DataFrame(
            {
                "ts": [
                    "2026-01-01",
                    "2026-01-01",
                    "2026-02-01",
                    "2026-02-02",
                    "2026-02-03",
                ],
                "target": [1, 2, 3, 4, 5],
                "input": [11, 12, 13, 14, 15],
            }
        ),
        {},
    )

    result = handle_request(
        "features/time_series/model",
        {
            "dataset_id": dataset_id,
            "time_column": "ts",
            "target": "target",
            "inputs": ["input"],
            "lags": [1],
            "rolling_windows": [2],
            "window_days": 3,
        },
    )

    assert result["sorted_row_count"] == 3
    assert result["quality"]["duplicate_timestamps"] == 0
    assert result["quality"]["interval_summary"]["count"] == 2


def test_time_series_model_window_reports_excluded_undated_rows():
    dataset_id = REGISTRY.register(
        pd.DataFrame(
            {
                "ts": [
                    None,
                    "2026-01-01",
                    "2026-01-01",
                    "2026-02-01",
                    "2026-02-02",
                    "2026-02-03",
                ],
                "target": [0, 1, 2, 3, 4, 5],
                "input": [10, 11, 12, 13, 14, 15],
            }
        ),
        {},
    )
    params = {
        "dataset_id": dataset_id,
        "time_column": "ts",
        "target": "target",
        "inputs": ["input"],
        "lags": [1],
        "rolling_windows": [2],
    }

    without_window = handle_request("features/time_series/model", params)
    with_window = handle_request(
        "features/time_series/model", {**params, "window_days": 3}
    )

    assert without_window["quality"]["missing_timestamps"] == 1
    assert without_window["quality"]["excluded_undated_rows"] == 0
    assert without_window["quality"]["duplicate_timestamps"] == 1
    assert with_window["sorted_row_count"] == 3
    assert with_window["quality"]["missing_timestamps"] == 1
    assert with_window["quality"]["excluded_undated_rows"] == 1
    assert with_window["quality"]["duplicate_timestamps"] == 0


def test_time_series_validation_window_returns_normalized_timestamps_for_split_labels():
    dataset_id = REGISTRY.register(
        pd.DataFrame(
            {
                "ts": pd.date_range(
                    "2026-01-01 00:00", periods=10, freq="h", tz="Asia/Bangkok"
                )
            }
        ),
        {},
    )

    result = handle_request(
        "features/time_series/validation",
        {
            "dataset_id": dataset_id,
            "time_column": "ts",
            "window_days": 7,
            "strategy": "holdout",
            "train_ratio": 0.6,
            "validation_ratio": 0.2,
            "modeling_timezone": "Asia/Bangkok",
        },
    )

    assert result["configuration"]["window_days"] == 7
    assert result["normalized_timestamps"][0] == "2025-12-31T17:00:00Z"
    assert result["normalized_timestamps"][-1] == "2026-01-01T02:00:00Z"


def test_time_split_returns_chronological_original_row_positions():
    df = pd.DataFrame(
        {
            "ts": [
                "2026-01-05",
                "2026-01-01",
                "2026-01-04",
                "2026-01-02",
                "2026-01-03",
            ]
        },
        index=[50, 10, 40, 20, 30],
    )

    result = time_split(df, "ts", train_ratio=0.6, validation_ratio=0.2)

    assert result == {
        "train_indices": [1, 3, 4],
        "validation_indices": [2],
        "test_indices": [0],
    }
    train_times = df.iloc[result["train_indices"]]["ts"]
    validation_times = df.iloc[result["validation_indices"]]["ts"]
    test_times = df.iloc[result["test_indices"]]["ts"]
    assert pd.to_datetime(train_times).max() < pd.to_datetime(validation_times).min()
    assert pd.to_datetime(validation_times).max() < pd.to_datetime(test_times).min()


def test_walk_forward_splits_use_expanding_train_and_fixed_horizon():
    df = pd.DataFrame(
        {
            "ts": [
                "2026-01-03",
                "2026-01-01",
                "2026-01-02",
                "2026-01-06",
                "2026-01-04",
                "2026-01-05",
                "2026-01-08",
                "2026-01-07",
            ]
        }
    )

    folds = walk_forward_splits(
        df,
        "ts",
        initial_train_size=4,
        horizon=2,
        step=2,
    )

    assert folds == [
        {
            "train_indices": [1, 2, 0, 4],
            "validation_indices": [5, 3],
        },
        {
            "train_indices": [1, 2, 0, 4, 5, 3],
            "validation_indices": [7, 6],
        },
    ]
    for fold in folds:
        train_times = pd.to_datetime(df.iloc[fold["train_indices"]]["ts"])
        validation_times = pd.to_datetime(
            df.iloc[fold["validation_indices"]]["ts"]
        )
        assert train_times.max() < validation_times.min()


def test_feature_timestamp_leakage_check_accepts_same_or_earlier_sources():
    result = check_feature_timestamp_leakage(
        pd.DataFrame(
            {
                "prediction_ts": ["2026-01-02", "2026-01-03"],
                "sensor_source_ts": ["2026-01-01", "2026-01-03"],
                "batch_source_ts": [None, "2026-01-02"],
            }
        ),
        "prediction_ts",
        ["sensor_source_ts", "batch_source_ts"],
    )

    assert result == {
        "status": "passed",
        "checked_rows": 2,
        "feature_source_time_columns": [
            "sensor_source_ts",
            "batch_source_ts",
        ],
    }


def test_feature_timestamp_leakage_check_fails_for_future_source():
    with pytest.raises(
        ValueError,
        match="Feature timestamp leakage.*sensor_source_ts.*row 1",
    ):
        check_feature_timestamp_leakage(
            pd.DataFrame(
                {
                    "prediction_ts": ["2026-01-02", "2026-01-03"],
                    "sensor_source_ts": ["2026-01-01", "2026-01-04"],
                }
            ),
            "prediction_ts",
            ["sensor_source_ts"],
        )


def test_time_series_validation_handler_returns_holdout_schema():
    dataset_id = REGISTRY.register(
        pd.DataFrame(
            {
                "ts": [
                    "2026-01-05",
                    "2026-01-01",
                    "2026-01-04",
                    "2026-01-02",
                    "2026-01-03",
                ],
                "source_ts": [
                    "2026-01-04",
                    "2025-12-31",
                    "2026-01-03",
                    "2026-01-01",
                    "2026-01-02",
                ],
            }
        ),
        {},
    )

    result = handle_request(
        "features/time_series/validation",
        {
            "dataset_id": dataset_id,
            "time_column": "ts",
            "strategy": "holdout",
            "train_ratio": 0.6,
            "validation_ratio": 0.2,
            "feature_source_time_columns": ["source_ts"],
        },
    )

    assert result["dataset_id"] == dataset_id
    assert result["time_column"] == "ts"
    assert result["strategy"] == "holdout"
    assert result["configuration"] == {
        "train_ratio": 0.6,
        "validation_ratio": 0.2,
        "modeling_timezone": "UTC",
        "prediction_time_column": "ts",
    }
    assert result["splits"] == [
        {
            "train_indices": [1, 3, 4],
            "validation_indices": [2],
            "test_indices": [0],
        }
    ]
    assert result["quality"]["duplicate_timestamps"] == 0
    assert result["leakage_check"] == {
        "status": "passed",
        "checked_rows": 5,
        "feature_source_time_columns": ["source_ts"],
    }


def test_time_series_validation_handler_returns_walk_forward_schema():
    dataset_id = REGISTRY.register(
        pd.DataFrame(
            {
                "ts": pd.date_range("2026-01-01", periods=8, freq="D"),
            }
        ),
        {},
    )

    result = handle_request(
        "features/time_series/validation",
        {
            "dataset_id": dataset_id,
            "time_column": "ts",
            "strategy": "walk_forward",
            "initial_train_size": 4,
            "horizon": 2,
            "step": 2,
        },
    )

    assert result["configuration"] == {
        "initial_train_size": 4,
        "horizon": 2,
        "step": 2,
        "modeling_timezone": "UTC",
        "prediction_time_column": "ts",
    }
    assert result["splits"] == [
        {
            "train_indices": [0, 1, 2, 3],
            "validation_indices": [4, 5],
        },
        {
            "train_indices": [0, 1, 2, 3, 4, 5],
            "validation_indices": [6, 7],
        },
    ]
    assert result["leakage_check"] == {
        "status": "not_checked",
        "checked_rows": 0,
        "feature_source_time_columns": [],
    }


def test_time_series_validation_handler_propagates_leakage_failure():
    dataset_id = REGISTRY.register(
        pd.DataFrame(
            {
                "ts": pd.date_range("2026-01-01", periods=5, freq="D"),
                "source_ts": pd.date_range("2026-01-02", periods=5, freq="D"),
            }
        ),
        {},
    )

    with pytest.raises(ValueError, match="Feature timestamp leakage"):
        handle_request(
            "features/time_series/validation",
            {
                "dataset_id": dataset_id,
                "time_column": "ts",
                "strategy": "holdout",
                "train_ratio": 0.6,
                "validation_ratio": 0.2,
                "feature_source_time_columns": ["source_ts"],
            },
        )


def test_time_split_rejects_mixed_naive_and_aware_timestamps():
    df = pd.DataFrame(
        {
            "ts": [
                "2026-01-01T00:00:00",
                "2026-01-02T00:00:00Z",
                "2026-01-03T00:00:00",
            ]
        }
    )

    with pytest.raises(ValueError, match="Mixed naive and aware timestamps"):
        time_split(df, "ts", train_ratio=0.34, validation_ratio=0.33)
