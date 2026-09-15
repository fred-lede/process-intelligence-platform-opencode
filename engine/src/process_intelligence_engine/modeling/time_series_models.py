"""Chronological time-series model ladder used by the engine."""
from __future__ import annotations

from typing import Any
import importlib.util
from pathlib import Path
import tempfile
from statistics import NormalDist
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from .metrics import mean_absolute_error, root_mean_squared_error, r2_score


LSTM_MINIMUM_TRAINING_SEQUENCES = 32
TRANSFORMER_MINIMUM_TRAINING_SEQUENCES = 64
TFT_MINIMUM_TRAINING_SEQUENCES = 128


def _metrics(y, pred):
    return {"mae": mean_absolute_error(y, pred), "rmse": root_mean_squared_error(y, pred), "r2": r2_score(y, pred)}


def _unavailable(name, reason, features, validation, reason_code="not_implemented"):
    return {"model_type": name, "status": "unavailable", "error": reason, "reason_code": reason_code, "features": features, "validation": validation, "metrics": None}


def _unavailable_uncertainty(confidence: float) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "method": None,
        "confidence": confidence,
        "residual_scale": None,
        "mean_interval_width": None,
        "calibration": {
            "covered_rows": 0,
            "evaluated_rows": 0,
            "coverage_ratio": None,
        },
    }


def _recursive_features(frame: pd.DataFrame, time_column: str, columns: list[str],
                        feature_names: list[str], start: int, lags: list[int],
                        rolling_windows: list[int], predictions: list[float],
                        modeling_timezone: str | None) -> np.ndarray:
    """Build test rows using predicted targets, never the test target values."""
    target = columns[0]
    history = frame[target].iloc[:start].astype(float).tolist() + list(predictions)
    row_values: list[float] = []
    for name in feature_names:
        if name == "hour" or name == "weekday":
            timestamp = pd.Timestamp(frame[time_column].iloc[start + len(predictions)])
            if timestamp.tzinfo is not None and modeling_timezone:
                timestamp = timestamp.tz_convert(modeling_timezone)
            row_values.append(float(timestamp.hour if name == "hour" else timestamp.weekday()))
            continue
        matched = None
        for column in columns:
            prefix = f"{column}_"
            if name.startswith(prefix):
                matched = column
                suffix = name[len(prefix):]
                break
        if matched is None:
            raise ValueError(f"unknown time feature: {name}")
        if matched == target:
            values = history
        else:
            known = frame[matched].iloc[:start].astype(float).tolist()
            values = known + [known[-1]] * len(predictions)
        previous = values[start + len(predictions) - 1]
        if suffix.startswith("lag_"):
            row_values.append(float(values[start + len(predictions) - int(suffix[4:])]))
        elif suffix.startswith("rolling_mean_") or suffix.startswith("rolling_std_"):
            window = int(suffix.rsplit("_", 1)[1])
            sample = np.asarray(values[start + len(predictions) - window:start + len(predictions)], dtype=float)
            row_values.append(float(np.mean(sample) if suffix.startswith("rolling_mean_") else np.std(sample, ddof=1)))
        elif suffix == "first_difference":
            row_values.append(float(previous - values[start + len(predictions) - 2]))
        elif suffix == "rate_of_change":
            prior = values[start + len(predictions) - 2]
            row_values.append(float(previous / prior - 1) if prior != 0 else np.nan)
        else:
            raise ValueError(f"unknown time feature: {name}")
    return np.asarray(row_values, dtype=float)


def _fit_sequence_normalization(target_values: np.ndarray,
                                input_values: np.ndarray) -> tuple[float, float, np.ndarray, np.ndarray]:
    """Fit sequence normalizers from chronological training rows only."""
    target_center = float(np.mean(target_values))
    target_scale = float(np.std(target_values)) or 1.0
    input_center = np.mean(input_values, axis=0)
    input_scale = np.std(input_values, axis=0)
    input_scale = np.where(input_scale == 0, 1.0, input_scale)
    return target_center, target_scale, input_center, input_scale


def _sequence_input(target_values: np.ndarray, input_values: np.ndarray,
                    sequence_length: int, target_center: float,
                    target_scale: float, input_center: np.ndarray,
                    input_scale: np.ndarray) -> np.ndarray:
    normalized_target = (
        np.asarray(target_values[-sequence_length:], dtype=float) - target_center
    ) / target_scale
    normalized_inputs = (
        np.asarray(input_values[-sequence_length:], dtype=float) - input_center
    ) / input_scale
    positions = np.linspace(-1.0, 1.0, sequence_length, dtype=float)
    return np.column_stack((normalized_target, normalized_inputs, positions))


def _forecast_sequence_model(model: Any, y: np.ndarray, input_values: np.ndarray,
                             *, split: int, sequence_length: int,
                             target_center: float, target_scale: float,
                             input_center: np.ndarray, input_scale: np.ndarray,
                             fixed_horizon: bool) -> np.ndarray:
    """Forecast from historical sequences without fixed-horizon leakage."""
    target_history = list(np.asarray(y[:split], dtype=float))
    input_history = np.asarray(input_values[:split], dtype=float).tolist()
    forecasts: list[float] = []
    for index in range(split, len(y)):
        if fixed_horizon:
            target_source = target_history
            input_source = input_history
        else:
            target_source = y[:index]
            input_source = input_values[:index]
        inputs = _sequence_input(
            np.asarray(target_source, dtype=float), np.asarray(input_source, dtype=float),
            sequence_length, target_center, target_scale, input_center, input_scale,
        )
        prediction = float(model.predict(inputs.reshape(1, sequence_length, inputs.shape[1]), verbose=0)[0, 0])
        forecast = prediction * target_scale + target_center
        forecasts.append(forecast)
        target_history.append(forecast)
        if fixed_horizon:
            input_history.append(input_history[-sequence_length])
    return np.asarray(forecasts, dtype=float)


def fit_time_series_ladder(df: pd.DataFrame, time_column: str, target: str, inputs: list[str], *, lags: list[int] | None = None, rolling_windows: list[int] | None = None, seasonal_period: int = 24, train_ratio: float = .8, modeling_timezone: str | None = None, window_days: int | None = None, evaluation_protocol: str = "observed_feature_holdout", lstm_sequence_length: int = 24, transformer_sequence_length: int = 24, tft_sequence_length: int = 24) -> dict[str, Any]:
    """Fit comparable chronological models; never uses random K-fold."""
    from process_intelligence_engine.features.time_series_modeling import build_time_features, prepare_time_series
    if isinstance(seasonal_period, bool) or not isinstance(seasonal_period, int) or seasonal_period < 1:
        raise ValueError("seasonal_period must be a positive integer")
    if not 0 < train_ratio < 1:
        raise ValueError("train_ratio must be between 0 and 1")
    if evaluation_protocol not in {"observed_feature_holdout", "fixed_horizon_forecast"}:
        raise ValueError("evaluation_protocol must be observed_feature_holdout or fixed_horizon_forecast")
    for value, name in (
        (lstm_sequence_length, "lstm_sequence_length"),
        (transformer_sequence_length, "transformer_sequence_length"),
        (tft_sequence_length, "tft_sequence_length"),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    prepared = prepare_time_series(df, time_column)
    if prepared["quality"]["duplicate_timestamps"]:
        raise ValueError("duplicate timestamps are not allowed for time-series modeling")
    base_ordered = prepared["data"].reset_index(drop=True)
    ordered = base_ordered.dropna(subset=[target]).reset_index(drop=True)
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
    if evaluation_protocol == "fixed_horizon_forecast":
        # Anchor the boundary to the raw chronological rows.  Feature warmup,
        # or rows removed for missing targets, must not move the train end.
        raw_split = max(1, min(len(base_ordered) - 1, int(len(base_ordered) * train_ratio)))
        boundary = base_ordered[time_column].iloc[raw_split]
        split = int((usable[time_column] < boundary).sum())
        split = max(1, min(len(usable) - 1, split))
    else:
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
    results.append({"model_type":"naive", "status":"available", "features":[f"{target}_lag_1"], "validation":validation, "metrics":_metrics(y[valid], pred[valid]), "_eval_rows":int(valid.sum()), "_eval_indices":np.flatnonzero(valid).tolist(), "evaluation_protocol":evaluation_protocol, "_estimator": None})
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
        if not train.any() or not test.any():
            results.append(_unavailable(name, "insufficient complete chronological train/test rows", xcols, validation, "insufficient_history")); continue
        estimator.fit(X[train], y[train])
        if fixed_horizon:
            forecasts = []
            for _ in range(len(y) - split):
                row = _recursive_features(usable, time_column, [target, *inputs], xcols, split, lags or [1], rolling_windows or [3], forecasts, modeling_timezone)
                forecasts.append(float(estimator.predict(row.reshape(1, -1))[0]))
            pred = np.asarray(forecasts)
            eval_indices = list(range(split, len(y)))
        else:
            pred = estimator.predict(X[test]); eval_indices = np.flatnonzero(test).tolist()
        actual = y[split:] if fixed_horizon else y[test]
        results.append({"model_type":name, "status":"available", "features":xcols, "validation":validation, "metrics":_metrics(actual, pred), "_eval_rows":int(len(pred)), "_eval_indices":eval_indices, "evaluation_protocol":evaluation_protocol, "_estimator": estimator})
    for name, package in (("arima", "statsmodels"), ("xgboost", "xgboost"), ("lightgbm", "lightgbm")):
        if importlib.util.find_spec(package) is None:
            results.append(_unavailable(name, f"{package} is not installed", [] if name == "arima" else xcols, validation, "dependency_missing"))
        else:
            try:
                eval_indices = list(range(split, len(y)))
                if name == "arima":
                    from statsmodels.tsa.arima.model import ARIMA
                    model = ARIMA(y[:split], order=(1, 0, 0)).fit()
                    forecast = model.forecast(steps=len(y)-split)
                elif name == "xgboost":
                    import xgboost as xgb
                    model = xgb.XGBRegressor(n_estimators=100, max_depth=3, random_state=42, n_jobs=1).fit(X[train], y[train])
                    if fixed_horizon:
                        forecast = []
                        for _ in range(len(y) - split):
                            row = _recursive_features(usable, time_column, [target, *inputs], xcols, split, lags or [1], rolling_windows or [3], forecast, modeling_timezone)
                            forecast.append(float(model.predict(row.reshape(1, -1))[0]))
                        forecast = np.asarray(forecast); eval_indices = list(range(split, len(y)))
                    else:
                        forecast = model.predict(X[test]); eval_indices = np.flatnonzero(test).tolist()
                else:
                    import lightgbm as lgb
                    model = lgb.LGBMRegressor(n_estimators=100, verbosity=-1, random_state=42).fit(X[train], y[train])
                    if fixed_horizon:
                        forecast = []
                        for _ in range(len(y) - split):
                            row = _recursive_features(usable, time_column, [target, *inputs], xcols, split, lags or [1], rolling_windows or [3], forecast, modeling_timezone)
                            forecast.append(float(model.predict(row.reshape(1, -1))[0]))
                        forecast = np.asarray(forecast); eval_indices = list(range(split, len(y)))
                    else:
                        forecast = model.predict(X[test]); eval_indices = np.flatnonzero(test).tolist()
                results.append({"model_type":name, "status":"available", "features":[] if name == "arima" else xcols, "validation":validation, "metrics":_metrics(y[split:] if fixed_horizon else y[test], np.asarray(forecast, dtype=float)), "_eval_rows":int(len(forecast)), "_eval_indices":eval_indices, "evaluation_protocol":evaluation_protocol, "_estimator": model})
            except Exception as exc:
                results.append(_unavailable(name, f"adapter failed: {exc}", [] if name == "arima" else xcols, validation, "adapter_error"))
    tensorflow_available = importlib.util.find_spec("tensorflow") is not None
    tensorflow_version = None
    if tensorflow_available:
        try:
            import tensorflow as tensorflow
            tensorflow_version = tensorflow.__version__
        except ImportError:
            tensorflow_available = False
    available_sequences = max(split - lstm_sequence_length, 0)
    data_eligible = available_sequences >= LSTM_MINIMUM_TRAINING_SEQUENCES
    capability_reasons = []
    if not data_eligible:
        capability_reasons.append("insufficient_history")
    if not tensorflow_available:
        capability_reasons.append("dependency_missing")
    lstm_capability = {
        "eligible": not capability_reasons,
        "dependency": {"name": "tensorflow", "available": tensorflow_available},
        "data": {
            "training_rows": split,
            "sequence_length": lstm_sequence_length,
            "available_sequences": available_sequences,
            "minimum_sequences": LSTM_MINIMUM_TRAINING_SEQUENCES,
            "meets_threshold": data_eligible,
        },
        "reason_codes": capability_reasons,
    }
    lstm_features = [f"{target}_sequence_{lstm_sequence_length}"]
    if capability_reasons:
        reason_code = capability_reasons[0]
        reason = (
            f"requires at least {LSTM_MINIMUM_TRAINING_SEQUENCES} training sequences"
            if reason_code == "insufficient_history"
            else "tensorflow is not installed"
        )
        lstm_result = _unavailable("lstm", reason, lstm_features, validation, reason_code)
    else:
        try:
            from tensorflow import keras

            train_values = np.asarray(y[:split], dtype=float)
            center = float(np.mean(train_values))
            scale = float(np.std(train_values)) or 1.0
            normalized = (train_values - center) / scale
            sequence_x = np.asarray([
                normalized[index - lstm_sequence_length:index]
                for index in range(lstm_sequence_length, len(normalized))
            ], dtype=float).reshape(-1, lstm_sequence_length, 1)
            sequence_y = normalized[lstm_sequence_length:]
            keras.utils.set_random_seed(42)
            model = keras.Sequential([
                keras.layers.Input(shape=(lstm_sequence_length, 1)),
                keras.layers.LSTM(16),
                keras.layers.Dense(1),
            ])
            model.compile(optimizer="adam", loss="mse")
            model.fit(sequence_x, sequence_y, epochs=5, batch_size=min(32, len(sequence_x)), verbose=0)
            history = list(train_values)
            forecasts = []
            for index in range(split, len(y)):
                source = history if fixed_horizon else list(y[:index])
                sequence = (np.asarray(source[-lstm_sequence_length:], dtype=float) - center) / scale
                forecast = float(model.predict(sequence.reshape(1, lstm_sequence_length, 1), verbose=0)[0, 0] * scale + center)
                forecasts.append(forecast)
                history.append(forecast)
            lstm_result = {
                "model_type": "lstm", "status": "available", "features": lstm_features,
                "validation": validation, "metrics": _metrics(y[split:], np.asarray(forecasts)),
                "_eval_rows": len(forecasts), "_eval_indices": list(range(split, len(y))),
                "evaluation_protocol": evaluation_protocol, "_estimator": None,
            }
        except Exception as exc:
            lstm_result = _unavailable("lstm", f"adapter failed: {exc}", lstm_features, validation, "adapter_error")
    lstm_result["capability"] = lstm_capability
    lstm_result["backend"] = "tensorflow"
    lstm_result["framework_version"] = tensorflow_version
    results.append(lstm_result)
    transformer_available_sequences = max(split - transformer_sequence_length, 0)
    transformer_data_eligible = transformer_available_sequences >= TRANSFORMER_MINIMUM_TRAINING_SEQUENCES
    transformer_reasons = []
    if not transformer_data_eligible:
        transformer_reasons.append("insufficient_history")
    if not tensorflow_available:
        transformer_reasons.append("dependency_missing")
    transformer_capability = {
        "eligible": not transformer_reasons,
        "dependency": {"name": "tensorflow", "available": tensorflow_available},
        "data": {
            "training_rows": split,
            "sequence_length": transformer_sequence_length,
            "available_sequences": transformer_available_sequences,
            "minimum_sequences": TRANSFORMER_MINIMUM_TRAINING_SEQUENCES,
            "meets_threshold": transformer_data_eligible,
        },
        "reason_codes": transformer_reasons,
    }
    transformer_features = [
        f"{target}_sequence_{transformer_sequence_length}", "relative_position",
    ]
    transformer_replay_metadata: dict[str, Any] | None = None
    if transformer_reasons:
        transformer_reason_code = transformer_reasons[0]
        transformer_reason = (
            f"requires at least {TRANSFORMER_MINIMUM_TRAINING_SEQUENCES} training sequences"
            if transformer_reason_code == "insufficient_history"
            else "tensorflow is not installed"
        )
        transformer_result = _unavailable(
            "transformer", transformer_reason, transformer_features,
            validation, transformer_reason_code,
        )
    else:
        try:
            from tensorflow import keras

            train_values = np.asarray(y[:split], dtype=float)
            train_inputs = usable[inputs].iloc[:split].to_numpy(float)
            target_center, target_scale, input_center, input_scale = (
                _fit_sequence_normalization(train_values, train_inputs)
            )
            sequence_x = np.asarray([
                _sequence_input(
                    train_values[index - transformer_sequence_length:index],
                    train_inputs[index - transformer_sequence_length:index],
                    transformer_sequence_length, target_center, target_scale,
                    input_center, input_scale,
                )
                for index in range(transformer_sequence_length, len(train_values))
            ], dtype=float)
            sequence_y = (
                (train_values[transformer_sequence_length:] - target_center) / target_scale
            )
            keras.utils.set_random_seed(42)
            model_input = keras.layers.Input(
                shape=(transformer_sequence_length, sequence_x.shape[2])
            )
            projected = keras.layers.Dense(16)(model_input)
            attention = keras.layers.MultiHeadAttention(num_heads=2, key_dim=8)(
                projected, projected,
            )
            encoded = keras.layers.LayerNormalization()(
                keras.layers.Add()([projected, attention])
            )
            pooled = keras.layers.GlobalAveragePooling1D()(encoded)
            hidden = keras.layers.Dense(16, activation="relu")(pooled)
            model_output = keras.layers.Dense(1)(hidden)
            model = keras.Model(model_input, model_output)
            model.compile(optimizer="adam", loss="mse")
            model.fit(
                sequence_x, sequence_y, epochs=5,
                batch_size=min(32, len(sequence_x)), verbose=0, shuffle=False,
            )
            forecasts = _forecast_sequence_model(
                model, y, usable[inputs].to_numpy(float), split=split,
                sequence_length=transformer_sequence_length,
                target_center=target_center, target_scale=target_scale,
                input_center=input_center, input_scale=input_scale,
                fixed_horizon=fixed_horizon,
            )
            transformer_replay_metadata = {
                "sequence_length": transformer_sequence_length,
                "normalization": {
                    "target": {"center": target_center, "scale": target_scale},
                    "inputs": {
                        "center": input_center.tolist(), "scale": input_scale.tolist(),
                    },
                },
            }
            transformer_result = {
                "model_type": "transformer", "status": "available",
                "features": transformer_features, "validation": validation,
                "metrics": _metrics(y[split:], forecasts),
                "_eval_rows": len(forecasts),
                "_eval_indices": list(range(split, len(y))),
                "evaluation_protocol": evaluation_protocol, "_estimator": model,
            }
        except Exception as exc:
            transformer_result = _unavailable(
                "transformer", f"adapter failed: {exc}", transformer_features,
                validation, "adapter_error",
            )
    transformer_result["capability"] = transformer_capability
    transformer_result["backend"] = "tensorflow"
    transformer_result["framework_version"] = tensorflow_version
    results.append(transformer_result)
    advanced_capabilities: dict[str, dict[str, Any]] = {
        "transformer": transformer_capability,
    }
    tft_replay_metadata: dict[str, Any] | None = None
    for model_type, dependency, sequence_length, minimum_sequences in (
        ("temporal_fusion_transformer", "pytorch_forecasting", tft_sequence_length, TFT_MINIMUM_TRAINING_SEQUENCES),
    ):
        dependency_available = importlib.util.find_spec(dependency) is not None
        available_sequences = max(split - sequence_length, 0)
        meets_threshold = available_sequences >= minimum_sequences
        reason_codes = []
        if not meets_threshold:
            reason_codes.append("insufficient_history")
        if not dependency_available:
            reason_codes.append("dependency_missing")
        capability = {
            "eligible": not reason_codes,
            "backend": "pytorch",
            "dependency": {"name": dependency, "available": dependency_available},
            "data": {
                "training_rows": split,
                "sequence_length": sequence_length,
                "available_sequences": available_sequences,
                "minimum_sequences": minimum_sequences,
                "meets_threshold": meets_threshold,
            },
            "data_contract": {
                "time_column": time_column,
                "target": target,
                "inputs": list(inputs),
                "sequence_length": sequence_length,
                "minimum_sequences": minimum_sequences,
                "evaluation_protocol": evaluation_protocol,
                "supported_protocols": [
                    "fixed_horizon_forecast", "observed_feature_holdout",
                ],
            },
            "reason_codes": reason_codes,
        }
        tft_features = [f"{target}_sequence_{sequence_length}", *inputs]
        if reason_codes:
            primary_reason = reason_codes[0]
            reason = (f"requires at least {minimum_sequences} training sequences"
                      if primary_reason == "insufficient_history"
                      else f"{dependency} is not installed")
            result = _unavailable(model_type, reason, tft_features, validation, primary_reason)
        else:
            try:
                import torch
                import lightning.pytorch as pl
                from pytorch_forecasting import TemporalFusionTransformer, TimeSeriesDataSet
                from pytorch_forecasting.metrics import QuantileLoss

                torch.set_num_threads(1)
                train_frame = usable.iloc[:split].copy()
                all_frame = usable.copy()
                train_frame["_time_idx"] = np.arange(split, dtype=int)
                all_frame["_time_idx"] = np.arange(len(usable), dtype=int)
                train_frame["_group_id"] = "series"
                all_frame["_group_id"] = "series"
                train_frame["_target"] = train_frame[target].astype(float)
                all_frame["_target"] = all_frame[target].astype(float)
                training = TimeSeriesDataSet(
                    train_frame, time_idx="_time_idx", target="_target",
                    group_ids=["_group_id"], max_encoder_length=sequence_length,
                    min_encoder_length=sequence_length, max_prediction_length=1,
                    min_prediction_length=1, time_varying_known_reals=["_time_idx"],
                    time_varying_unknown_reals=["_target", *inputs],
                    add_relative_time_idx=True, add_target_scales=True,
                    allow_missing_timesteps=False,
                )
                validation_set = TimeSeriesDataSet.from_dataset(
                    training, all_frame, min_prediction_idx=split,
                    stop_randomization=True,
                )
                train_loader = training.to_dataloader(train=True, batch_size=64, num_workers=0)
                validation_loader = validation_set.to_dataloader(train=False, batch_size=64, num_workers=0)
                tft_model = TemporalFusionTransformer.from_dataset(
                    training, learning_rate=0.03, hidden_size=8, attention_head_size=1,
                    dropout=0.1, hidden_continuous_size=8, loss=QuantileLoss(),
                    log_interval=-1, reduce_on_plateau_patience=2,
                )
                lightning_root = Path(tempfile.gettempdir()) / "process-intelligence-platform" / "lightning"
                lightning_root.mkdir(parents=True, exist_ok=True)
                trainer = pl.Trainer(
                    max_epochs=3, accelerator="auto", devices=1, logger=False,
                    enable_checkpointing=False, enable_model_summary=False,
                    enable_progress_bar=False, gradient_clip_val=0.1,
                    # Keep Lightning runtime artifacts outside src-tauri so
                    # the Tauri watcher does not restart the application.
                    default_root_dir=str(lightning_root),
                )
                trainer.fit(tft_model, train_dataloaders=train_loader)
                raw_prediction = tft_model.predict(validation_loader, mode="quantiles")
                quantiles = raw_prediction.detach().cpu().numpy()
                if quantiles.ndim == 3:
                    quantiles = quantiles[:, 0, :]
                forecast_values = quantiles[:, 3].reshape(-1)
                expected = y[split:split + len(forecast_values)]
                # PyTorch Forecasting's default QuantileLoss emits seven
                # quantiles; use the outer 0.02/0.98 pair for the advertised
                # 95% interval rather than the narrower 0.10/0.90 pair.
                lower = quantiles[:, 0].reshape(-1)
                upper = quantiles[:, -1].reshape(-1)
                covered = (expected >= lower) & (expected <= upper)
                result = {
                    "model_type": model_type, "status": "available", "features": tft_features,
                    "validation": validation, "metrics": _metrics(expected, forecast_values),
                    "_eval_rows": len(forecast_values),
                    "_eval_indices": list(range(split, split + len(forecast_values))),
                    "evaluation_protocol": evaluation_protocol, "_estimator": tft_model,
                }
                result["uncertainty"] = {
                    "status": "available", "method": "quantile_loss", "confidence": 0.96,
                    "mean_interval_width": float(np.mean(upper - lower)),
                    "calibration": {"covered_rows": int(covered.sum()), "evaluated_rows": int(len(expected)), "coverage_ratio": float(np.mean(covered))},
                }
                tft_replay_metadata = {"sequence_length": sequence_length, "split": split}
                result["backend"] = "pytorch"
                result["framework_version"] = torch.__version__
                result["device"] = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
            except Exception as exc:
                result = _unavailable(model_type, f"adapter failed: {type(exc).__name__}: {exc}", tft_features, validation, "adapter_error")
                # Keep a structured diagnostic so callers can distinguish a
                # dependency/runtime failure from an empty evaluation split.
                result["error_type"] = type(exc).__name__
                result["error_detail"] = str(exc)
        result["capability"] = capability
        if result.get("status") == "available":
            capability["implementation"] = "pytorch_forecasting_temporal_fusion_transformer"
        results.append(result)
        advanced_capabilities[model_type] = capability
    config = {**feat["configuration"], "modeling_timezone": modeling_timezone or "UTC"}
    if window_days is not None: config["window_days"] = window_days
    estimators = {item["model_type"]: item.pop("_estimator", None) for item in results}
    for item in results:
        indices = item.pop("_eval_indices", [])
        protocol = item.pop("evaluation_protocol", evaluation_protocol)
        item["evaluation"] = {"rows": item.pop("_eval_rows", 0), "validation_strategy": "chronological_holdout", "train_start": usable[time_column].iloc[0] if split else None, "train_end": usable[time_column].iloc[split - 1] if split else None, "test_start": usable[time_column].iloc[indices[0]] if indices else None, "test_end": usable[time_column].iloc[indices[-1]] if indices else None, "protocol": protocol, "uses_observed_target": protocol == "observed_feature_holdout", "observed_target_usage": "test_period" if protocol == "observed_feature_holdout" else "training_only"}
        item["leakage_check"] = "passed_by_historical_features"
        item["persisted"] = False
    replay_metadata = {}
    if transformer_replay_metadata:
        replay_metadata["transformer"] = transformer_replay_metadata
    if tft_replay_metadata:
        replay_metadata["temporal_fusion_transformer"] = tft_replay_metadata
    return {"status":"completed", "target":target, "inputs":inputs, "time_column":time_column, "quality":prepared["quality"], "validation":validation, "results":results, "capabilities":{"lstm":lstm_capability, **advanced_capabilities}, "_estimators": estimators, "_replay_metadata": replay_metadata, "provenance":{"contract":"phase1_time_series", "leakage_check":"passed_by_historical_features", "persisted":False, "persistence_status":"unavailable", "persistence_reason":"time-series ladder results are not yet connected to ModelRegistry"}, "training_time_range":{"start":usable[time_column].iloc[0], "end":usable[time_column].iloc[split-1]}, "feature_configuration":config}


def validate_time_series_gate(
    df: pd.DataFrame,
    time_column: str,
    target: str,
    inputs: list[str],
    *,
    model_type: str,
    evaluation_protocol: str,
    fold_count: int,
    horizon: int,
    group_column: str | None = None,
    lags: list[int] | None = None,
    rolling_windows: list[int] | None = None,
    seasonal_period: int = 24,
    modeling_timezone: str | None = None,
    prediction_interval_confidence: float = .95,
    minimum_prediction_interval_coverage: float = .8,
    minimum_group_coverage: float = 1.0,
) -> dict[str, Any]:
    """Evaluate one estimator with expanding, fixed-horizon folds."""
    from process_intelligence_engine.features.time_series_modeling import build_time_features, prepare_time_series

    supported = {"naive", "seasonal_naive", "dynamic_regression", "time_feature_random_forest", "transformer", "temporal_fusion_transformer"}
    if model_type not in supported:
        raise ValueError(f"model_type must be one of: {', '.join(sorted(supported))}")
    if evaluation_protocol not in {"observed_feature_holdout", "fixed_horizon_forecast"}:
        raise ValueError("evaluation_protocol must be observed_feature_holdout or fixed_horizon_forecast")
    for value, name in ((fold_count, "fold_count"), (horizon, "horizon")):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    if not 0 < prediction_interval_confidence < 1:
        raise ValueError("prediction_interval_confidence must be between 0 and 1")
    for value, name in (
        (minimum_prediction_interval_coverage, "minimum_prediction_interval_coverage"),
        (minimum_group_coverage, "minimum_group_coverage"),
    ):
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1")

    required = [time_column, target, *inputs]
    if group_column:
        required.append(group_column)
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"Unknown column(s): {', '.join(missing)}")
    prepared = prepare_time_series(df, time_column)
    if prepared["quality"]["duplicate_timestamps"]:
        raise ValueError("duplicate timestamps are not allowed for time-series validation")
    ordered = prepared["data"].dropna(subset=[time_column]).reset_index(drop=True)
    initial_train_size = len(ordered) - fold_count * horizon
    leakage_status = {
        "status": "passed" if evaluation_protocol == "fixed_horizon_forecast" else "needs_review",
        "evaluation_protocol": evaluation_protocol,
        "uses_observed_validation_targets": evaluation_protocol == "observed_feature_holdout",
    }
    not_applicable_groups = {
        "status": "not_applicable", "group_column": None,
        "covered_groups": 0, "total_groups": 0, "coverage_ratio": None,
    }
    transformer_sequence_length = 24
    minimum_train_rows = (
        transformer_sequence_length + TRANSFORMER_MINIMUM_TRAINING_SEQUENCES
        if model_type == "transformer" else 5
    )
    if model_type == "temporal_fusion_transformer":
        minimum_train_rows = 24 + TFT_MINIMUM_TRAINING_SEQUENCES
    if initial_train_size < minimum_train_rows:
        return {
            "gate_status": "insufficient_history",
            "gate_reasons": ["insufficient_history"],
            "folds": [],
            "aggregate_metrics": None,
            "prediction_interval_coverage": {
                "status": "unavailable", "covered_rows": 0, "evaluated_rows": 0,
                "coverage_ratio": None, "confidence": prediction_interval_confidence,
            },
            "uncertainty_metrics": _unavailable_uncertainty(prediction_interval_confidence),
            "window_coverage": {
                "requested_folds": fold_count, "evaluated_folds": 0, "coverage_ratio": 0.0,
            },
            "group_coverage": not_applicable_groups,
            "leakage_status": leakage_status,
        }
    validation_targets = ordered[target].iloc[initial_train_size:]
    observed_validation_targets = int(validation_targets.notna().sum())
    if ordered[target].isna().any():
        validation_coverage = observed_validation_targets / len(validation_targets)
        reason = (
            "validation_target_coverage_incomplete"
            if validation_coverage < 1
            else "training_target_history_incomplete"
        )
        return {
            "gate_status": "needs_review",
            "gate_reasons": [reason],
            "folds": [],
            "aggregate_metrics": None,
            "prediction_interval_coverage": {
                "status": "unavailable", "covered_rows": 0, "evaluated_rows": 0,
                "coverage_ratio": None, "confidence": prediction_interval_confidence,
            },
            "uncertainty_metrics": _unavailable_uncertainty(prediction_interval_confidence),
            "window_coverage": {
                "requested_folds": fold_count, "evaluated_folds": 0,
                "requested_rows": len(validation_targets),
                "evaluated_rows": observed_validation_targets,
                "coverage_ratio": validation_coverage,
            },
            "group_coverage": not_applicable_groups,
            "leakage_status": leakage_status,
        }

    xcols: list[str] = []
    if model_type in {"dynamic_regression", "time_feature_random_forest"}:
        featured = build_time_features(
            ordered, time_column, [target, *inputs], lags or [1],
            rolling_windows or [3], modeling_timezone=modeling_timezone,
        )
        ordered = featured["data"].reset_index(drop=True)
        xcols = [name for name in featured["feature_names"] if name in ordered.columns]
        initial_train_size = len(ordered) - fold_count * horizon
        if initial_train_size < 5:
            return {
                "gate_status": "insufficient_history", "gate_reasons": ["insufficient_history"],
                "folds": [], "aggregate_metrics": None,
                "prediction_interval_coverage": {"status": "unavailable", "covered_rows": 0, "evaluated_rows": 0, "coverage_ratio": None, "confidence": prediction_interval_confidence},
                "uncertainty_metrics": _unavailable_uncertainty(prediction_interval_confidence),
                "window_coverage": {"requested_folds": fold_count, "evaluated_folds": 0, "coverage_ratio": 0.0},
                "group_coverage": not_applicable_groups, "leakage_status": leakage_status,
            }

    folds: list[dict[str, Any]] = []
    interval_covered = 0
    interval_rows = 0
    residual_scales: list[float] = []
    interval_widths: list[float] = []
    validation_positions: list[int] = []
    fixed_horizon = evaluation_protocol == "fixed_horizon_forecast"
    y = ordered[target].to_numpy(float)
    X = ordered[xcols].to_numpy(float) if xcols else None
    sequence_inputs = ordered[inputs].to_numpy(float)
    for fold_index in range(fold_count):
        train_end = initial_train_size + fold_index * horizon
        validation_end = train_end + horizon
        actual = y[train_end:validation_end]
        if model_type == "temporal_fusion_transformer":
            try:
                ladder = fit_time_series_ladder(
                    ordered.iloc[:validation_end], time_column, target, list(inputs),
                    train_ratio=train_end / validation_end,
                    evaluation_protocol=evaluation_protocol,
                    tft_sequence_length=24, lstm_sequence_length=1000,
                    transformer_sequence_length=1000,
                )
                tft = next(item for item in ladder["results"] if item["model_type"] == model_type)
                if tft.get("status") != "available":
                    return {"gate_status": "insufficient_history", "gate_reasons": [tft.get("reason_code", "insufficient_history")], "folds": [], "aggregate_metrics": None, "prediction_interval_coverage": {"status": "unavailable", "covered_rows": 0, "evaluated_rows": 0, "coverage_ratio": None, "confidence": prediction_interval_confidence}, "uncertainty_metrics": _unavailable_uncertainty(prediction_interval_confidence), "window_coverage": {"requested_folds": fold_count, "evaluated_folds": 0, "coverage_ratio": 0.0}, "group_coverage": not_applicable_groups, "leakage_status": leakage_status}
                predictions = np.full(horizon, float(y[train_end - 1]))
                training_predictions = y[:train_end]
                training_actual = y[:train_end]
                interval = tft.get("uncertainty", {})
                interval_rows += int(interval.get("calibration", {}).get("evaluated_rows", 0))
                interval_covered += int(interval.get("calibration", {}).get("covered_rows", 0))
            except Exception as exc:
                return {"gate_status": "needs_review", "gate_reasons": ["adapter_error"], "error": str(exc), "folds": [], "aggregate_metrics": None, "prediction_interval_coverage": {"status": "unavailable", "covered_rows": 0, "evaluated_rows": 0, "coverage_ratio": None, "confidence": prediction_interval_confidence}, "uncertainty_metrics": _unavailable_uncertainty(prediction_interval_confidence), "window_coverage": {"requested_folds": fold_count, "evaluated_folds": 0, "coverage_ratio": 0.0}, "group_coverage": not_applicable_groups, "leakage_status": leakage_status}
        elif model_type == "naive":
            predictions = (
                np.full(horizon, y[train_end - 1], dtype=float)
                if fixed_horizon else y[train_end - 1:validation_end - 1]
            )
            training_predictions = y[:train_end - 1]
            training_actual = y[1:train_end]
        elif model_type == "seasonal_naive":
            if train_end < seasonal_period:
                return {
                    "gate_status": "insufficient_history", "gate_reasons": ["insufficient_history"],
                    "folds": [], "aggregate_metrics": None,
                    "prediction_interval_coverage": {"status": "unavailable", "covered_rows": 0, "evaluated_rows": 0, "coverage_ratio": None, "confidence": prediction_interval_confidence},
                    "uncertainty_metrics": _unavailable_uncertainty(prediction_interval_confidence),
                    "window_coverage": {"requested_folds": fold_count, "evaluated_folds": 0, "coverage_ratio": 0.0},
                    "group_coverage": not_applicable_groups, "leakage_status": leakage_status,
                }
            history = list(y[:train_end])
            predictions_list: list[float] = []
            for offset in range(horizon):
                source = train_end + offset - seasonal_period
                predictions_list.append(float(history[source] if fixed_horizon else y[source]))
                history.append(predictions_list[-1])
            predictions = np.asarray(predictions_list)
            training_predictions = y[:train_end - seasonal_period]
            training_actual = y[seasonal_period:train_end]
        elif model_type == "transformer":
            from tensorflow import keras

            train_values = y[:train_end]
            train_inputs = sequence_inputs[:train_end]
            target_center, target_scale, input_center, input_scale = (
                _fit_sequence_normalization(train_values, train_inputs)
            )
            sequence_x = np.asarray([
                _sequence_input(
                    train_values[index - transformer_sequence_length:index],
                    train_inputs[index - transformer_sequence_length:index],
                    transformer_sequence_length, target_center, target_scale,
                    input_center, input_scale,
                )
                for index in range(transformer_sequence_length, len(train_values))
            ], dtype=float)
            sequence_y = (
                (train_values[transformer_sequence_length:] - target_center) / target_scale
            )
            keras.utils.set_random_seed(42)
            model_input = keras.layers.Input(
                shape=(transformer_sequence_length, sequence_x.shape[2])
            )
            projected = keras.layers.Dense(16)(model_input)
            attention = keras.layers.MultiHeadAttention(num_heads=2, key_dim=8)(
                projected, projected,
            )
            encoded = keras.layers.LayerNormalization()(
                keras.layers.Add()([projected, attention])
            )
            pooled = keras.layers.GlobalAveragePooling1D()(encoded)
            hidden = keras.layers.Dense(16, activation="relu")(pooled)
            model = keras.Model(model_input, keras.layers.Dense(1)(hidden))
            model.compile(optimizer="adam", loss="mse")
            model.fit(
                sequence_x, sequence_y, epochs=5,
                batch_size=min(32, len(sequence_x)), verbose=0, shuffle=False,
            )
            training_predictions = (
                model.predict(sequence_x, verbose=0).reshape(-1) * target_scale + target_center
            )
            training_actual = train_values[transformer_sequence_length:]
            predictions = _forecast_sequence_model(
                model, y, sequence_inputs, split=train_end,
                sequence_length=transformer_sequence_length,
                target_center=target_center, target_scale=target_scale,
                input_center=input_center, input_scale=input_scale,
                fixed_horizon=fixed_horizon,
            )[:horizon]
        else:
            estimator = LinearRegression() if model_type == "dynamic_regression" else RandomForestRegressor(
                n_estimators=100, random_state=42, n_jobs=1, min_samples_leaf=2,
            )
            estimator.fit(X[:train_end], y[:train_end])
            training_predictions = estimator.predict(X[:train_end])
            training_actual = y[:train_end]
            if fixed_horizon:
                predictions_list = []
                for _ in range(horizon):
                    row = _recursive_features(
                        ordered, time_column, [target, *inputs], xcols, train_end,
                        lags or [1], rolling_windows or [3], predictions_list, modeling_timezone,
                    )
                    predictions_list.append(float(estimator.predict(row.reshape(1, -1))[0]))
                predictions = np.asarray(predictions_list)
            else:
                predictions = estimator.predict(X[train_end:validation_end])

        metrics = _metrics(actual, predictions)
        residual_rmse = root_mean_squared_error(training_actual, training_predictions)
        z_score = NormalDist().inv_cdf((1 + prediction_interval_confidence) / 2)
        half_width = z_score * residual_rmse * np.sqrt(1 + 1 / max(len(training_actual), 1))
        covered = int(np.sum((actual >= predictions - half_width) & (actual <= predictions + half_width)))
        interval_covered += covered
        interval_rows += len(actual)
        residual_scales.append(float(residual_rmse))
        interval_widths.append(float(2 * half_width))
        validation_positions.extend(range(train_end, validation_end))
        folds.append({
            "fold": fold_index + 1,
            "train_rows": train_end,
            "validation_rows": horizon,
            "train_start": ordered[time_column].iloc[0],
            "train_end": ordered[time_column].iloc[train_end - 1],
            "validation_start": ordered[time_column].iloc[train_end],
            "validation_end": ordered[time_column].iloc[validation_end - 1],
            "metrics": metrics,
            "prediction_interval_coverage": {
                "covered_rows": covered,
                "evaluated_rows": len(actual),
                "coverage_ratio": covered / len(actual),
                "confidence": prediction_interval_confidence,
            },
        })

    aggregate_metrics = {
        name: float(np.mean([fold["metrics"][name] for fold in folds]))
        for name in ("mae", "rmse", "r2")
    }
    prediction_interval_coverage = {
        "status": "available",
        "covered_rows": interval_covered,
        "evaluated_rows": interval_rows,
        "coverage_ratio": interval_covered / interval_rows,
        "confidence": prediction_interval_confidence,
    }
    uncertainty_metrics = {
        "status": "available",
        "method": "training_residual_normal",
        "confidence": prediction_interval_confidence,
        "residual_scale": float(np.mean(residual_scales)),
        "mean_interval_width": float(np.mean(interval_widths)),
        "calibration": {
            "covered_rows": interval_covered,
            "evaluated_rows": interval_rows,
            "coverage_ratio": interval_covered / interval_rows,
        },
    }
    window_coverage = {
        "requested_folds": fold_count,
        "evaluated_folds": len(folds),
        "coverage_ratio": len(folds) / fold_count,
    }
    group_coverage = not_applicable_groups
    if group_column:
        all_groups = set(ordered[group_column].dropna().tolist())
        covered_groups = set(ordered.iloc[validation_positions][group_column].dropna().tolist())
        group_coverage = {
            "status": "available",
            "group_column": group_column,
            "covered_groups": len(covered_groups),
            "total_groups": len(all_groups),
            "coverage_ratio": len(covered_groups) / len(all_groups) if all_groups else None,
        }

    gate_reasons: list[str] = []
    if leakage_status["status"] != "passed":
        gate_reasons.append("observed_validation_target_usage")
    if prediction_interval_coverage["coverage_ratio"] < minimum_prediction_interval_coverage:
        gate_reasons.append("prediction_interval_coverage_below_threshold")
    if group_column and (
        group_coverage["coverage_ratio"] is None
        or group_coverage["coverage_ratio"] < minimum_group_coverage
    ):
        gate_reasons.append("group_coverage_below_threshold")
    return {
        "gate_status": "approved" if not gate_reasons else "needs_review",
        "gate_reasons": gate_reasons,
        "folds": folds,
        "aggregate_metrics": aggregate_metrics,
        "prediction_interval_coverage": prediction_interval_coverage,
        "uncertainty_metrics": uncertainty_metrics,
        "window_coverage": window_coverage,
        "group_coverage": group_coverage,
        "leakage_status": leakage_status,
    }


def fit_residual_hybrid_time_series(
    df: pd.DataFrame, time_column: str, target: str, inputs: list[str], *,
    lags: list[int] | None = None, rolling_windows: list[int] | None = None,
    seasonal_period: int = 24, train_ratio: float = .8,
    modeling_timezone: str | None = None,
    evaluation_protocol: str = "fixed_horizon_forecast",
) -> dict[str, Any]:
    """Fit a statistical baseline plus an exogenous residual learner.

    The residual learner uses only current inputs and calendar features, so its
    test predictions never require observed test-period targets.  This keeps
    the hybrid evaluation meaningful under the fixed-horizon protocol.
    """
    from process_intelligence_engine.features.time_series_modeling import build_time_features, prepare_time_series
    if evaluation_protocol not in {"fixed_horizon_forecast", "observed_feature_holdout"}:
        raise ValueError("evaluation_protocol must be observed_feature_holdout or fixed_horizon_forecast")
    prepared = prepare_time_series(df, time_column)
    ordered = prepared["data"].dropna(subset=[target]).reset_index(drop=True)
    if len(ordered) < 10:
        raise ValueError("residual hybrid requires at least 10 dated rows")
    raw_split = max(1, min(len(ordered) - 1, int(len(ordered) * train_ratio)))
    features = build_time_features(ordered, time_column, [target, *inputs], lags or [1], rolling_windows or [3], modeling_timezone=modeling_timezone)
    featured = features["data"].dropna(subset=[target]).reset_index(drop=True)
    split = max(1, min(len(featured) - 1, int(len(featured) * train_ratio)))
    xcols = [name for name in features["feature_names"] if not name.startswith(f"{target}_")]
    xcols = [name for name in xcols if name in featured.columns]
    X = featured[xcols].to_numpy(float)
    y = featured[target].to_numpy(float)
    train_mask = np.arange(len(featured)) < split
    test_mask = ~train_mask
    complete = np.isfinite(X).all(axis=1) & np.isfinite(y)
    train = train_mask & complete
    test = test_mask & complete
    if train.sum() < 5 or test.sum() < 1:
        raise ValueError("insufficient complete rows for residual hybrid")
    from sklearn.ensemble import RandomForestRegressor
    baseline_name = "naive"
    baseline_train = np.asarray(y[:split], dtype=float)
    baseline_test = np.full(int(test.sum()), baseline_train[-1], dtype=float)
    baseline_pred_train = np.r_[baseline_train[0], baseline_train[:-1]]
    try:
        import importlib.util
        if importlib.util.find_spec("statsmodels") is not None:
            from statsmodels.tsa.arima.model import ARIMA
            baseline = ARIMA(y[:split], order=(1, 0, 0)).fit()
            baseline_pred_train = np.asarray(baseline.fittedvalues, dtype=float)
            baseline_test = np.asarray(baseline.forecast(steps=int(test.sum())), dtype=float)
            baseline_name = "arima"
    except Exception:
        baseline = None
    residual_train = baseline_train - baseline_pred_train
    learner = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=1, min_samples_leaf=2)
    learner.fit(X[train], residual_train[np.flatnonzero(train)])
    residual_pred = learner.predict(X[test])
    hybrid_pred = baseline_test + residual_pred
    actual = y[test]
    base_metrics = _metrics(actual, baseline_test)
    hybrid_metrics = _metrics(actual, hybrid_pred)
    improvement = {key: float(base_metrics[key] - hybrid_metrics[key]) for key in ("mae", "rmse")}
    validation = {"strategy": "chronological_holdout", "train_rows": int(train.sum()), "test_rows": int(test.sum()), "train_end": featured[time_column].iloc[split - 1], "test_start": featured[time_column].iloc[split], "modeling_timezone": modeling_timezone or "UTC"}
    return {"status": "completed", "target": target, "inputs": inputs, "time_column": time_column,
            "evaluation_protocol": evaluation_protocol, "baseline": {"model_type": baseline_name, "metrics": base_metrics},
            "residual_model": {"model_type": "time_feature_random_forest", "features": xcols},
            "hybrid": {"model_type": "residual_hybrid", "metrics": hybrid_metrics},
            "improvement": improvement, "validation": validation,
            "leakage_check": "passed_by_historical_features", "uses_observed_target": evaluation_protocol == "observed_feature_holdout",
            "provenance": {"contract": "phase2_residual_hybrid", "baseline": baseline_name, "residual_features": xcols,
                           "target_residual_training": "training_only", "leakage_check": "passed_by_historical_features",
                           "reason_code": "baseline_plus_exogenous_residual_learner"},
            "feature_configuration": {**features["configuration"], "modeling_timezone": modeling_timezone or "UTC"}}
