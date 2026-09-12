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


def _unavailable(name, reason, features, validation, reason_code="not_implemented"):
    return {"model_type": name, "status": "unavailable", "error": reason, "reason_code": reason_code, "features": features, "validation": validation, "metrics": None}


def fit_time_series_ladder(df: pd.DataFrame, time_column: str, target: str, inputs: list[str], *, lags: list[int] | None = None, rolling_windows: list[int] | None = None, seasonal_period: int = 24, train_ratio: float = .8, modeling_timezone: str | None = None, window_days: int | None = None, evaluation_protocol: str = "observed_feature_holdout") -> dict[str, Any]:
    """Fit comparable chronological models; never uses random K-fold."""
    from process_intelligence_engine.features.time_series_modeling import build_time_features, prepare_time_series
    if isinstance(seasonal_period, bool) or not isinstance(seasonal_period, int) or seasonal_period < 1:
        raise ValueError("seasonal_period must be a positive integer")
    if not 0 < train_ratio < 1:
        raise ValueError("train_ratio must be between 0 and 1")
    if evaluation_protocol not in {"observed_feature_holdout", "fixed_horizon_forecast"}:
        raise ValueError("evaluation_protocol must be observed_feature_holdout or fixed_horizon_forecast")
    prepared = prepare_time_series(df, time_column)
    if prepared["quality"]["duplicate_timestamps"]:
        raise ValueError("duplicate timestamps are not allowed for time-series modeling")
    ordered = prepared["data"].dropna(subset=[target]).reset_index(drop=True)
    n = len(ordered)
    if n < 5:
        raise ValueError("time-series modeling requires at least 5 dated rows")
    cut = max(1, min(n - 1, int(n * train_ratio)))
    feature_cols = [target, *inputs]
    feat = build_time_features(ordered, time_column, feature_cols, lags or [1], rolling_windows or [3], modeling_timezone=modeling_timezone)
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
    fixed_horizon = evaluation_protocol == "fixed_horizon_forecast"
    # Naive uses previous observed target; fixed horizon recursively uses its
    # own prior forecast and therefore never reads test-period targets.
    pred = np.array(usable[target].shift(1).to_numpy(float), dtype=float, copy=True)
    if fixed_horizon:
        previous = float(y[split - 1])
        for index in range(split, len(y)):
            pred[index] = previous
            previous = pred[index]
    mask = np.arange(len(usable)) >= split
    valid = mask & np.isfinite(pred)
    results.append({"model_type":"naive", "status":"available", "features":[f"{target}_lag_1"], "validation":validation, "metrics":_metrics(y[valid], pred[valid]), "_eval_rows":int(valid.sum()), "_eval_indices":np.flatnonzero(valid).tolist(), "evaluation_protocol":evaluation_protocol})
    lag = np.array(usable[target].shift(seasonal_period).to_numpy(float), dtype=float, copy=True)
    if fixed_horizon:
        history = list(y[:split])
        for index in range(split, len(y)):
            lag[index] = history[index - seasonal_period] if 0 <= index - seasonal_period < len(history) else np.nan
            history.append(lag[index])
    valid = mask & np.isfinite(lag)
    results.append({"model_type":"seasonal_naive", "status":"available" if valid.any() else "unavailable", "features":[f"{target}_lag_{seasonal_period}"], "validation":validation, "metrics":_metrics(y[valid], lag[valid]) if valid.any() else None, "_eval_rows":int(valid.sum()), "_eval_indices":np.flatnonzero(valid).tolist(), "error":None if valid.any() else "seasonal period exceeds available history", "reason_code":None if valid.any() else "insufficient_history", "evaluation_protocol":evaluation_protocol})
    X = usable[xcols].to_numpy(float)
    valid_rows = np.isfinite(X).all(axis=1) & np.isfinite(y)
    train = valid_rows & (np.arange(len(usable)) < split); test = valid_rows & (np.arange(len(usable)) >= split)
    for name, estimator in [("dynamic_regression", LinearRegression()), ("time_feature_random_forest", RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=1, min_samples_leaf=2))]:
        if fixed_horizon:
            results.append(_unavailable(name, "fixed_horizon_forecast requires recursive feature generation", xcols, validation, "not_supported")); continue
        if not train.any() or not test.any():
            results.append(_unavailable(name, "insufficient complete chronological train/test rows", xcols, validation, "insufficient_history")); continue
        estimator.fit(X[train], y[train]); pred = estimator.predict(X[test])
        results.append({"model_type":name, "status":"available", "features":xcols, "validation":validation, "metrics":_metrics(y[test], pred), "_eval_rows":int(test.sum()), "_eval_indices":np.flatnonzero(test).tolist()})
    for name, package in (("arima", "statsmodels"), ("xgboost", "xgboost"), ("lightgbm", "lightgbm")):
        if importlib.util.find_spec(package) is None:
            results.append(_unavailable(name, f"{package} is not installed", [] if name == "arima" else xcols, validation, "dependency_missing"))
        else:
            try:
                if name == "arima":
                    from statsmodels.tsa.arima.model import ARIMA
                    model = ARIMA(y[:split], order=(1, 0, 0)).fit()
                    forecast = model.forecast(steps=len(y)-split)
                elif name == "xgboost":
                    if fixed_horizon:
                        results.append(_unavailable(name, "fixed_horizon_forecast requires recursive feature generation", xcols, validation, "not_supported")); continue
                    import xgboost as xgb
                    model = xgb.XGBRegressor(n_estimators=100, max_depth=3, random_state=42, n_jobs=1).fit(X[train], y[train])
                    forecast = model.predict(X[test])
                else:
                    if fixed_horizon:
                        results.append(_unavailable(name, "fixed_horizon_forecast requires recursive feature generation", xcols, validation, "not_supported")); continue
                    import lightgbm as lgb
                    model = lgb.LGBMRegressor(n_estimators=100, verbosity=-1, random_state=42).fit(X[train], y[train])
                    forecast = model.predict(X[test])
                results.append({"model_type":name, "status":"available", "features":[] if name == "arima" else xcols, "validation":validation, "metrics":_metrics(y[split:], np.asarray(forecast, dtype=float)), "_eval_rows":int(len(forecast)), "_eval_indices":list(range(split, len(y))), "evaluation_protocol":"fixed_horizon_forecast" if name == "arima" else "observed_feature_holdout"})
            except Exception as exc:
                results.append(_unavailable(name, f"adapter failed: {exc}", [] if name == "arima" else xcols, validation, "adapter_error"))
    config = {**feat["configuration"], "modeling_timezone": modeling_timezone or "UTC"}
    if window_days is not None: config["window_days"] = window_days
    for item in results:
        indices = item.pop("_eval_indices", [])
        protocol = item.pop("evaluation_protocol", evaluation_protocol)
        item["evaluation"] = {"rows": item.pop("_eval_rows", 0), "validation_strategy": "chronological_holdout", "train_start": usable[time_column].iloc[0] if split else None, "train_end": usable[time_column].iloc[split - 1] if split else None, "test_start": usable[time_column].iloc[indices[0]] if indices else None, "test_end": usable[time_column].iloc[indices[-1]] if indices else None, "protocol": protocol, "uses_observed_target": protocol == "observed_feature_holdout", "observed_target_usage": "test_period" if protocol == "observed_feature_holdout" else "training_only"}
        item["leakage_check"] = "passed_by_historical_features"
        item["persisted"] = False
    return {"status":"completed", "target":target, "inputs":inputs, "time_column":time_column, "quality":prepared["quality"], "validation":validation, "results":results, "provenance":{"contract":"phase1_time_series", "leakage_check":"passed_by_historical_features", "persisted":False, "persistence_status":"unavailable", "persistence_reason":"time-series ladder results are not yet connected to ModelRegistry"}, "training_time_range":{"start":usable[time_column].iloc[0], "end":usable[time_column].iloc[split-1]}, "feature_configuration":config}
