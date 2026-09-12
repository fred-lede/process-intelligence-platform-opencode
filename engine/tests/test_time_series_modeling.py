import pandas as pd
import pytest

from process_intelligence_engine.features.time_series_modeling import (
    build_time_features,
    prepare_time_series,
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
        "lags": [1, 7],
        "rolling_windows": [7],
        "frequency": "daily",
    }
    assert explicit["feature_configuration"] == {
        "columns": ["target", "input"],
        "lags": [2],
        "rolling_windows": [3],
        "frequency": "daily",
    }
