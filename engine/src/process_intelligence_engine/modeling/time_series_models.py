"""Chronological time-series model ladder used by the engine."""
from __future__ import annotations

from typing import Any
import importlib.util
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from .metrics import mean_absolute_error, root_mean_squared_error, r2_score


def _metrics(y, pred):
    return {"mae": mean_absolute_error(y, pred), "rmse": root_mean_squared_error(y, pred), "r2": r2_score(y, pred)}


def _unavailable(name, reason, features, validation):
    return {"model_type": name, "status": "unavailable", "error": reason, "features": features, "validation": validation, "metrics": None}


def fit_time_series_ladder(df: pd.DataFrame, time_column: str, target: str, inputs: list[str], *, lags: list[int] | None = None, rolling_windows: list[int] | None = None, seasonal_period: int = 24, train_ratio: float = .8, modeling_timezone: str | None = None, window_days: int | None = None) -> dict[str, Any]:
    """Fit comparable chronological models; never uses random K-fold."""
    from process_intelligence_engine.features.time_series_modeling import build_time_features, prepare_time_series
    if isinstance(seasonal_period, bool) or not isinstance(seasonal_period, int) or seasonal_period < 1:
        raise ValueError("seasonal_period must be a positive integer")
    if not 0 < train_ratio < 1:
        raise ValueError("train_ratio must be between 0 and 1")
    prepared = prepare_time_series(df, time_column)
    if prepared["quality"]["duplicate_timestamps"]:
        raise ValueError("duplicate timestamps are not allowed for time-series modeling")
    ordered = prepared["data"].dropna(subset=[target]).reset_index(drop=True)
    n = len(ordered)
    if n < 5:
        raise ValueError("time-series modeling requires at least 5 dated rows")
    cut = max(1, min(n - 1, int(n * train_ratio)))
    feature_cols = [target, *inputs]
    feat = build_time_features(ordered, time_column, feature_cols, lags or [1], rolling_windows or [3])
    usable = feat["data"].dropna(subset=[target]).reset_index(drop=True)
    if len(usable) < 5:
        raise ValueError("insufficient complete rows after time features")
    feature_names = feat["feature_names"]
    # feature builder returns target lags too; exclude current target/input values and retain derived history.
    xcols = [c for c in feature_names if c in usable.columns]
    y = usable[target].to_numpy(float)
    split = max(1, min(len(usable)-1, int(len(usable)*train_ratio)))
    validation = {"strategy": "chronological_holdout", "train_rows": split, "test_rows": len(usable)-split, "train_end": usable[time_column].iloc[split-1], "test_start": usable[time_column].iloc[split], "modeling_timezone": modeling_timezone or "UTC"}
    results = []
    # Naive uses previous observed target.
    pred = usable[target].shift(1).to_numpy(float)
    mask = np.arange(len(usable)) >= split
    valid = mask & np.isfinite(pred)
    results.append({"model_type":"naive", "status":"available", "features":[f"{target}_lag_1"], "validation":validation, "metrics":_metrics(y[valid], pred[valid])})
    lag = usable[target].shift(seasonal_period).to_numpy(float)
    valid = mask & np.isfinite(lag)
    results.append({"model_type":"seasonal_naive", "status":"available" if valid.any() else "unavailable", "features":[f"{target}_lag_{seasonal_period}"], "validation":validation, "metrics":_metrics(y[valid], lag[valid]) if valid.any() else None, "error":None if valid.any() else "seasonal period exceeds available history"})
    X = usable[xcols].to_numpy(float)
    valid_rows = np.isfinite(X).all(axis=1) & np.isfinite(y)
    train = valid_rows & (np.arange(len(usable)) < split); test = valid_rows & (np.arange(len(usable)) >= split)
    for name, estimator in [("dynamic_regression", LinearRegression()), ("time_feature_random_forest", RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=1, min_samples_leaf=2))]:
        if not train.any() or not test.any():
            results.append(_unavailable(name, "insufficient complete chronological train/test rows", xcols, validation)); continue
        estimator.fit(X[train], y[train]); pred = estimator.predict(X[test])
        results.append({"model_type":name, "status":"available", "features":xcols, "validation":validation, "metrics":_metrics(y[test], pred)})
    for name, package in (("arima", "statsmodels"), ("xgboost", "xgboost"), ("lightgbm", "lightgbm")):
        results.append(_unavailable(name, f"{package} is not installed", xcols, validation) if importlib.util.find_spec(package) is None else _unavailable(name, f"{name} adapter is not enabled for this runtime", xcols, validation))
    config = {**feat["configuration"], "modeling_timezone": modeling_timezone or "UTC"}
    if window_days is not None: config["window_days"] = window_days
    for item in results:
        item["evaluation"] = {"rows": validation["test_rows"] if item["metrics"] is not None else 0, "validation_strategy": "chronological_holdout", "test_start": validation["test_start"] if item["metrics"] is not None else None, "test_end": usable[time_column].iloc[-1] if item["metrics"] is not None else None}
    return {"status":"completed", "target":target, "inputs":inputs, "time_column":time_column, "quality":prepared["quality"], "validation":validation, "results":results, "provenance":{"contract":"phase1_time_series", "leakage_check":"passed_by_historical_features", "persisted":False}, "training_time_range":{"start":usable[time_column].iloc[0], "end":usable[time_column].iloc[split-1]}, "feature_configuration":config}
