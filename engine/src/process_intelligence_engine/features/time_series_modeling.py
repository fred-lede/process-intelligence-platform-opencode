"""Time-series data preparation contracts."""

from __future__ import annotations

import warnings
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
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
    if interval_seconds < 3600:
        return {"frequency": "minute", "lags": [1, 60], "rolling_windows": [60]}
    if interval_seconds <= 3600:
        return {"frequency": "hourly", "lags": [1, 24], "rolling_windows": [24]}
    if interval_seconds <= 86400:
        return {"frequency": "daily", "lags": [1, 7], "rolling_windows": [7]}
    return {"frequency": "coarse", "lags": [1], "rolling_windows": [3]}


def _calendar_timezone(
    values: pd.Series, modeling_timezone: str | None
) -> tuple[str, Any | None]:
    parsed = [pd.Timestamp(value) for value in values.dropna()]
    timezones = {str(timestamp.tzinfo) for timestamp in parsed if timestamp.tzinfo}
    has_naive = any(timestamp.tzinfo is None for timestamp in parsed)
    if modeling_timezone is not None:
        try:
            requested_timezone = ZoneInfo(modeling_timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown modeling timezone: {modeling_timezone}") from exc
        if has_naive and timezones:
            raise ValueError("Mixed naive and aware timestamps are not supported")
        return modeling_timezone, None if has_naive else requested_timezone

    if has_naive and timezones or len(timezones) > 1:
        raise ValueError(
            "Mixed source timezones require an explicit modeling_timezone"
        )
    if timezones:
        source_timezone = next(
            timestamp.tzinfo for timestamp in parsed if timestamp.tzinfo
        )
        return next(iter(timezones)), source_timezone
    return "source_local_naive", None


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
    modeling_timezone: str | None = None,
) -> dict[str, Any]:
    """Build deterministic historical features without reading the current/future value."""
    missing_columns = [column for column in columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Unknown column(s): {', '.join(missing_columns)}")

    normalized_lags = _validate_positive_steps(lags, "lags")
    normalized_windows = _validate_positive_steps(rolling_windows, "rolling_windows")
    if any(window < 2 for window in normalized_windows):
        raise ValueError("rolling_windows must be at least 2 for rolling std")
    prepared = prepare_time_series(df, time_column)
    calendar_timezone, calendar_tzinfo = _calendar_timezone(
        df[time_column], modeling_timezone
    )
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
        featured[rate_name] = shifted.div(previous.where(previous.ne(0))).sub(1)
        feature_names.extend([difference_name, rate_name])

    calendar_timestamps = featured[time_column]
    if calendar_tzinfo is not None:
        calendar_timestamps = calendar_timestamps.dt.tz_convert(calendar_tzinfo)
    featured["hour"] = calendar_timestamps.dt.hour
    featured["weekday"] = calendar_timestamps.dt.weekday
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

    warmup_rows = min(
        max([2, *normalized_lags, *normalized_windows]),
        len(featured),
    )
    warmup_mask = pd.Series(False, index=featured.index)
    warmup_mask.iloc[:warmup_rows] = True
    finite_mask = pd.Series(
        np.isfinite(featured[feature_names].to_numpy(dtype=float)).all(axis=1),
        index=featured.index,
    )
    invalid_mask = ~warmup_mask & ~finite_mask
    complete_mask = ~warmup_mask & finite_mask
    complete_data = featured.loc[complete_mask].reset_index(drop=True)
    median_interval = prepared["quality"]["interval_summary"]["median_seconds"]
    suggestions = _frequency_suggestions(median_interval)
    return {
        "data": complete_data,
        "feature_names": feature_names,
        "dropped_warmup_rows": warmup_rows,
        "dropped_invalid_rows": int(invalid_mask.sum()),
        "warnings": warnings_found,
        "configuration": {
            "columns": list(columns),
            "lags": normalized_lags,
            "rolling_windows": normalized_windows,
            "frequency": suggestions["frequency"],
            "calendar_timezone": calendar_timezone,
        },
    }


def suggest_time_feature_configuration(
    interval_summary: dict[str, Any], columns: list[str]
) -> dict[str, Any]:
    """Return reproducible lag/window defaults derived from the median interval."""
    suggestions = _frequency_suggestions(interval_summary.get("median_seconds"))
    return {"columns": list(columns), **suggestions}


def _timestamp_values(
    df: pd.DataFrame, column: str, *, allow_missing: bool
) -> pd.Series:
    if column not in df.columns:
        raise ValueError(f"Unknown time column: {column}")

    parsed: list[Any] = []
    for value in df[column]:
        if pd.isna(value):
            if not allow_missing:
                raise ValueError(f"Time column '{column}' contains missing timestamps")
            parsed.append(pd.NaT)
            continue
        try:
            timestamp = pd.Timestamp(value)
            if pd.isna(timestamp):
                raise ValueError
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                f"Time column '{column}' contains a non-datetime value"
            ) from exc
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        else:
            timestamp = timestamp.tz_convert("UTC")
        parsed.append(timestamp)
    return pd.Series(parsed, index=df.index, dtype="datetime64[ns, UTC]")


def _chronological_positions(
    df: pd.DataFrame, time_column: str
) -> tuple[list[int], list[Any]]:
    timestamps = _timestamp_values(df, time_column, allow_missing=False)
    ordering = pd.DataFrame(
        {
            "timestamp": timestamps.to_numpy(),
            "position": np.arange(len(df)),
        }
    ).sort_values("timestamp", kind="stable")
    return ordering["position"].tolist(), ordering["timestamp"].tolist()


def _require_strict_boundary(
    timestamps: list[Any], boundary: int, boundary_name: str
) -> None:
    if (
        0 < boundary < len(timestamps)
        and timestamps[boundary - 1] >= timestamps[boundary]
    ):
        raise ValueError(
            f"{boundary_name} must not split rows with the same timestamp"
        )


def time_split(
    df: pd.DataFrame,
    time_column: str,
    train_ratio: float,
    validation_ratio: float,
) -> dict[str, list[int]]:
    """Return deterministic iloc positions for chronological train/validation/test."""
    if (
        isinstance(train_ratio, bool)
        or isinstance(validation_ratio, bool)
        or not 0 < train_ratio < 1
        or not 0 < validation_ratio < 1
        or train_ratio + validation_ratio >= 1
    ):
        raise ValueError(
            "train_ratio and validation_ratio must be positive and sum to less than 1"
        )

    positions, timestamps = _chronological_positions(df, time_column)
    train_end = int(len(positions) * train_ratio)
    validation_end = train_end + int(len(positions) * validation_ratio)
    if (
        train_end == 0
        or validation_end == train_end
        or validation_end == len(positions)
    ):
        raise ValueError(
            "time split must produce non-empty train, validation, and test sets"
        )
    _require_strict_boundary(timestamps, train_end, "train/validation boundary")
    _require_strict_boundary(timestamps, validation_end, "validation/test boundary")
    return {
        "train_indices": positions[:train_end],
        "validation_indices": positions[train_end:validation_end],
        "test_indices": positions[validation_end:],
    }


def walk_forward_splits(
    df: pd.DataFrame,
    time_column: str,
    initial_train_size: int,
    horizon: int,
    step: int,
) -> list[dict[str, list[int]]]:
    """Return expanding-window rolling-origin folds as deterministic iloc positions."""
    for value, name in (
        (initial_train_size, "initial_train_size"),
        (horizon, "horizon"),
        (step, "step"),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer")

    positions, timestamps = _chronological_positions(df, time_column)
    folds: list[dict[str, list[int]]] = []
    train_end = initial_train_size
    while train_end + horizon <= len(positions):
        validation_end = train_end + horizon
        _require_strict_boundary(timestamps, train_end, "train/validation boundary")
        folds.append(
            {
                "train_indices": positions[:train_end],
                "validation_indices": positions[train_end:validation_end],
            }
        )
        train_end += step
    if not folds:
        raise ValueError("initial_train_size and horizon do not produce any folds")
    return folds


def check_feature_timestamp_leakage(
    df: pd.DataFrame,
    prediction_time_column: str,
    feature_source_time_columns: list[str],
) -> dict[str, Any]:
    """Fail when a feature uses information newer than its prediction timestamp."""
    prediction_timestamps = _timestamp_values(
        df, prediction_time_column, allow_missing=False
    )
    source_columns = list(dict.fromkeys(feature_source_time_columns))
    for column in source_columns:
        source_timestamps = _timestamp_values(df, column, allow_missing=True)
        leaking = source_timestamps.notna() & source_timestamps.gt(prediction_timestamps)
        if leaking.any():
            row_position = int(np.flatnonzero(leaking.to_numpy())[0])
            raise ValueError(
                f"Feature timestamp leakage in '{column}' at row {row_position}"
            )
    return {
        "status": "passed",
        "checked_rows": len(df),
        "feature_source_time_columns": source_columns,
    }
