import pandas as pd
import pytest

from process_intelligence_engine.features.time_series_modeling import prepare_time_series
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
