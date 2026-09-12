"""Time-series data preparation contracts."""

from __future__ import annotations

import warnings
from typing import Any

import pandas as pd


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
