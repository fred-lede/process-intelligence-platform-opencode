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
