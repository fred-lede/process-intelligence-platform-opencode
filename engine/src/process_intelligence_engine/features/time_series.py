"""Time series feature extraction for process data.

Supports lag, rolling statistics, change features, drift, and consecutive
exceedance counts as requested in spec section 2.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def compute_time_features(
    df: pd.DataFrame,
    time_column: str,
    value_columns: list[str],
    window_sizes: list[int] | None = None,
) -> dict[str, Any]:
    """Compute time-series features for process data.

    Args:
        df: DataFrame with at least a time column and value columns.
        time_column: Name of the datetime / ordered column.
        value_columns: List of numeric columns to compute features for.
        window_sizes: Rolling window sizes (default [3, 5, 10]).

    Returns:
        dict with extracted feature columns and summary stats.
    """
    if window_sizes is None:
        window_sizes = [3, 5, 10]

    result_df = df[[time_column] + value_columns].copy()
    result_df[time_column] = pd.to_datetime(result_df[time_column])
    result_df = result_df.sort_values(time_column).reset_index(drop=True)

    feature_cols: dict[str, list] = {time_column: result_df[time_column].tolist()}
    for col in value_columns:
        series = result_df[col].astype(float)
        # Lag features
        for lag in [1, 2, 3]:
            feature_cols[f"{col}_lag{lag}"] = series.shift(lag).tolist()
        # Change (delta)
        feature_cols[f"{col}_delta"] = series.diff().tolist()
        # Rolling statistics
        for w in window_sizes:
            if w <= len(series):
                feature_cols[f"{col}_roll_mean_{w}"] = (
                    series.rolling(w, min_periods=1).mean().tolist()
                )
                feature_cols[f"{col}_roll_std_{w}"] = (
                    series.rolling(w, min_periods=1).std().tolist()
                )
        # Drift: difference between rolling mean and raw value.
        # Use the largest window actually computed (a window is only created
        # when it fits the row count), otherwise fall back to zero drift so a
        # short series does not raise KeyError on the roll_mean_5 reference.
        drift_win = max(
            (w for w in window_sizes if f"{col}_roll_mean_{w}" in feature_cols),
            default=None,
        )
        if drift_win is not None:
            feature_cols[f"{col}_drift"] = (
                series - feature_cols[f"{col}_roll_mean_{drift_win}"]
            ).tolist()
        else:
            feature_cols[f"{col}_drift"] = [0.0] * len(series)

    feature_df = pd.DataFrame(feature_cols)
    # Include the raw value columns in the returned rows so downstream charts
    # can draw the base series as reference. They are intentionally excluded
    # from feature_columns / n_features (they are not derived features).
    preview_df = feature_df.join(result_df[value_columns].reset_index(drop=True))
    return {
        "feature_columns": [
            c for c in feature_df.columns if c != time_column
        ],
        "n_rows": len(feature_df),
        "n_features": len([c for c in feature_df.columns if c != time_column]),
        "preview": preview_df.head(20).to_dict(orient="records"),
    }


def compute_consecutive_exceedance(
    df: pd.DataFrame,
    value_column: str,
    threshold: float,
    direction: str = "above",
) -> dict[str, Any]:
    """Count consecutive exceedances above or below a threshold.

    Returns the run lengths of consecutive values exceeding the threshold.
    """
    series = df[value_column].astype(float)
    if direction == "above":
        exceeded = series > threshold
    elif direction == "below":
        exceeded = series < threshold
    else:
        exceeded = series != series  # NaN

    runs: list[int] = []
    current_run = 0
    for val in exceeded:
        if val:
            current_run += 1
        else:
            if current_run > 0:
                runs.append(current_run)
            current_run = 0
    if current_run > 0:
        runs.append(current_run)

    return {
        "column": value_column,
        "direction": direction,
        "threshold": float(threshold),
        "n_exceedance_runs": len(runs),
        "max_consecutive": max(runs) if runs else 0,
        "mean_run_length": float(np.mean(runs)) if runs else 0.0,
        "run_lengths": runs[:20],  # cap at 20
    }
