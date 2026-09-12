"""Time-series data preparation contracts."""

from __future__ import annotations

import warnings
from typing import Any

import pandas as pd


def _validate_positive_steps(values: list[int], name: str) -> list[int]:
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1
        for value in values
    ):
        raise ValueError(f"{name} must contain positive integers")
    return list(dict.fromkeys(values))


def _frequency_suggestions(interval_seconds: float | None) -> dict[str, Any]:
    if interval_seconds is None:
        return {"frequency": "unknown", "lags": [1], "rolling_windows": [3]}
    if interval_seconds <= 3600:
        return {"frequency": "hourly", "lags": [1, 24], "rolling_windows": [24]}
    if interval_seconds <= 86400:
        return {"frequency": "daily", "lags": [1, 7], "rolling_windows": [7]}
    return {"frequency": "coarse", "lags": [1], "rolling_windows": [3]}


def prepare_time_series(df: pd.DataFrame, time_column: str) -> dict[str, Any]:
    """Parse and chronologically sort a dataset while reporting time quality."""
    if time_column not in df.columns:
        raise ValueError(f"Unknown time column: {time_column}")

    prepared = df.copy()
    missing_mask = prepared[time_column].isna()
    parsed: list[Any] = []
    timezone_representations: set[str] = set()
    parse_errors = 0
    for value, missing in zip(prepared[time_column], missing_mask):
        if missing:
            parsed.append(pd.NaT)
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error")
                timestamp = pd.Timestamp(value)
            if pd.isna(timestamp):
                raise ValueError
        except (TypeError, ValueError, OverflowError, Warning):
            parse_errors += 1
            parsed.append(pd.NaT)
            continue

        if timestamp.tzinfo is None:
            timezone_representations.add("naive")
            timestamp = timestamp.tz_localize("UTC")
        else:
            timezone_representations.add(str(timestamp.tzinfo))
            timestamp = timestamp.tz_convert("UTC")
        parsed.append(timestamp)

    if parse_errors:
        raise ValueError(
            f"Time column '{time_column}' contains {parse_errors} non-datetime value(s)"
        )

    prepared[time_column] = pd.DatetimeIndex(parsed)
    prepared = prepared.sort_values(time_column, kind="stable").reset_index(drop=True)
    valid_timestamps = prepared[time_column].dropna()
    intervals = valid_timestamps.diff().dropna().dt.total_seconds()
    source_timezones = sorted(timezone_representations)

    interval_summary = {
        "count": int(len(intervals)),
        "min_seconds": float(intervals.min()) if not intervals.empty else None,
        "median_seconds": float(intervals.median()) if not intervals.empty else None,
        "max_seconds": float(intervals.max()) if not intervals.empty else None,
    }
    return {
        "data": prepared,
        "quality": {
            "duplicate_timestamps": int(valid_timestamps.duplicated().sum()),
            "missing_timestamps": int(missing_mask.sum()),
            "interval_summary": interval_summary,
            "timezone": (
                source_timezones[0]
                if len(source_timezones) == 1
                else "mixed" if source_timezones else None
            ),
            "timezone_representations": source_timezones,
            "normalized_timezone": "UTC",
            "timezone_errors": int(len(source_timezones) > 1),
            "parse_errors": parse_errors,
        },
    }


def build_time_features(
    df: pd.DataFrame,
    time_column: str,
    columns: list[str],
    lags: list[int],
    rolling_windows: list[int],
) -> dict[str, Any]:
    """Build deterministic historical features without reading the current/future value."""
    missing_columns = [column for column in columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Unknown column(s): {', '.join(missing_columns)}")

    normalized_lags = _validate_positive_steps(lags, "lags")
    normalized_windows = _validate_positive_steps(rolling_windows, "rolling_windows")
    prepared = prepare_time_series(df, time_column)
    featured = prepared["data"].copy()
    feature_names: list[str] = []

    for column in columns:
        shifted = featured[column].shift(1)
        for lag in normalized_lags:
            name = f"{column}_lag_{lag}"
            featured[name] = featured[column].shift(lag)
            feature_names.append(name)
        for window in normalized_windows:
            mean_name = f"{column}_rolling_mean_{window}"
            std_name = f"{column}_rolling_std_{window}"
            historical_window = shifted.rolling(window=window, min_periods=window)
            featured[mean_name] = historical_window.mean()
            featured[std_name] = historical_window.std()
            feature_names.extend([mean_name, std_name])

        difference_name = f"{column}_first_difference"
        rate_name = f"{column}_rate_of_change"
        previous = shifted.shift(1)
        featured[difference_name] = shifted - previous
        featured[rate_name] = shifted.div(previous).sub(1)
        feature_names.extend([difference_name, rate_name])

    featured["hour"] = featured[time_column].dt.hour
    featured["weekday"] = featured[time_column].dt.weekday
    feature_names.extend(["hour", "weekday"])

    warnings_found: list[str] = []
    intervals = featured[time_column].dropna().diff().dropna().dt.total_seconds()
    if intervals.nunique() > 1:
        warnings_found.append("irregular_intervals")
    if prepared["quality"]["missing_timestamps"]:
        warnings_found.append("missing_timestamps")
    warnings_found.extend(
        f"missing_values:{column}" for column in columns if featured[column].isna().any()
    )

    complete_mask = featured[feature_names].notna().all(axis=1)
    complete_data = featured.loc[complete_mask].reset_index(drop=True)
    median_interval = prepared["quality"]["interval_summary"]["median_seconds"]
    suggestions = _frequency_suggestions(median_interval)
    return {
        "data": complete_data,
        "feature_names": feature_names,
        "dropped_warmup_rows": int((~complete_mask).sum()),
        "warnings": warnings_found,
        "configuration": {
            "columns": list(columns),
            "lags": normalized_lags,
            "rolling_windows": normalized_windows,
            "frequency": suggestions["frequency"],
        },
    }


def suggest_time_feature_configuration(
    interval_summary: dict[str, Any], columns: list[str]
) -> dict[str, Any]:
    """Return reproducible lag/window defaults derived from the median interval."""
    suggestions = _frequency_suggestions(interval_summary.get("median_seconds"))
    return {"columns": list(columns), **suggestions}
