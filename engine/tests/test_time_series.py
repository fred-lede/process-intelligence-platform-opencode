"""Tests for time-series feature extraction."""
import pandas as pd

from process_intelligence_engine.features.time_series import compute_time_features


def _df(rows: int) -> pd.DataFrame:
    dt = pd.date_range("2026-09-01 08:00:00", periods=rows, freq="min")
    return pd.DataFrame({"datetime": dt, "output_thickness": [1.0] * rows})


def test_time_series_full_windows():
    result = compute_time_features(
        _df(20), "datetime", ["output_thickness"], [3, 5, 10]
    )
    assert result["n_rows"] == 20
    assert "output_thickness_lag1" in result["feature_columns"]
    assert "output_thickness_roll_mean_5" in result["feature_columns"]
    assert "output_thickness_roll_mean_10" in result["feature_columns"]
    assert "output_thickness_drift" in result["feature_columns"]


def test_time_series_short_series_does_not_raise():
    # Regression: drift referenced roll_mean_5 unconditionally, raising
    # KeyError when every window exceeded the row count (<5 rows).
    result = compute_time_features(
        _df(3), "datetime", ["output_thickness"], [3, 5, 10]
    )
    assert result["n_rows"] == 3
    assert "output_thickness_drift" in result["feature_columns"]
    assert len(result["preview"]) == 3


def test_time_series_partial_windows_uses_largest_fit():
    # rows==7 fits window 3 and 5 but not 10; drift should use window 5.
    result = compute_time_features(
        _df(7), "datetime", ["output_thickness"], [3, 5, 10]
    )
    assert result["n_rows"] == 7
    assert "output_thickness_roll_mean_5" in result["feature_columns"]
    assert "output_thickness_roll_mean_10" not in result["feature_columns"]
    assert "output_thickness_drift" in result["feature_columns"]
