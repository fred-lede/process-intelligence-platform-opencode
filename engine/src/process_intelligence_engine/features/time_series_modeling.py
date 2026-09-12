"""Time-series data preparation contracts."""

from __future__ import annotations

from typing import Any

import pandas as pd


def prepare_time_series(df: pd.DataFrame, time_column: str) -> dict[str, Any]:
    """Parse and chronologically sort a dataset while reporting time quality."""
    if time_column not in df.columns:
        raise ValueError(f"Unknown time column: {time_column}")

    prepared = df.copy()
    missing_mask = prepared[time_column].isna()
    parsed = pd.to_datetime(prepared[time_column], errors="coerce", utc=True)
    parse_errors = int((~missing_mask & parsed.isna()).sum())
    if parse_errors:
        raise ValueError(
            f"Time column '{time_column}' contains {parse_errors} non-datetime value(s)"
        )

    prepared[time_column] = parsed
    prepared = prepared.sort_values(time_column, kind="stable").reset_index(drop=True)
    valid_timestamps = prepared[time_column].dropna()
    intervals = valid_timestamps.diff().dropna().dt.total_seconds()

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
            "timezone": "UTC",
            "timezone_errors": 0,
            "parse_errors": parse_errors,
        },
    }
