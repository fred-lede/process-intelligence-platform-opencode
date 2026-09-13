"""Time-series-specific, non-causal model explanations."""
from __future__ import annotations

from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd


def feature_provenance(
    name: str,
    source_columns: list[str],
    time_column: str,
) -> dict[str, Any]:
    """Describe how one model feature was derived and when it is available."""
    if name in {"hour", "weekday"}:
        return {
            "kind": f"calendar_{name}",
            "source_column": time_column,
            "lag": None,
            "window": None,
            "availability": "prediction_timestamp",
        }

    for column in sorted(source_columns, key=len, reverse=True):
        prefix = f"{column}_"
        if not name.startswith(prefix):
            continue
        suffix = name[len(prefix):]
        if suffix.startswith("lag_"):
            return _provenance("lag", column, lag=int(suffix[4:]))
        if suffix.startswith("rolling_mean_"):
            return _provenance("rolling_mean", column, window=int(suffix.rsplit("_", 1)[1]))
        if suffix.startswith("rolling_std_"):
            return _provenance("rolling_std", column, window=int(suffix.rsplit("_", 1)[1]))
        if suffix == "first_difference":
            return _provenance("difference", column)
        if suffix == "rate_of_change":
            return _provenance("rate_of_change", column)

    return {
        "kind": "source",
        "source_column": name,
        "lag": None,
        "window": None,
        "availability": "prediction_time_input",
    }


def _provenance(kind: str, column: str, *, lag: int | None = None,
                window: int | None = None) -> dict[str, Any]:
    return {
        "kind": kind,
        "source_column": column,
        "lag": lag,
        "window": window,
        "availability": "historical_only",
    }


def _importance_values(estimator: Any, feature_count: int) -> tuple[str, np.ndarray]:
    if hasattr(estimator, "feature_importances_"):
        values = np.abs(np.asarray(estimator.feature_importances_, dtype=float).reshape(-1))
        method = "tree_feature_importance"
    elif hasattr(estimator, "coef_"):
        coefficients = np.asarray(estimator.coef_, dtype=float)
        values = np.mean(np.abs(coefficients.reshape(-1, feature_count)), axis=0)
        method = "absolute_linear_coefficient"
    else:
        raise ValueError("time-series estimator does not expose model-native feature importance")
    if len(values) != feature_count:
        raise ValueError("time-series estimator feature count does not match persisted metadata")
    total = float(values.sum())
    return method, values / total if total > 0 else np.zeros(feature_count, dtype=float)


def _permuted_blocks(values: np.ndarray, block_size: int, rng: np.random.Generator) -> np.ndarray:
    blocks = [values[start:start + block_size] for start in range(0, len(values), block_size)]
    if len(blocks) < 2:
        return values[::-1].copy()
    order = rng.permutation(len(blocks))
    if np.array_equal(order, np.arange(len(blocks))):
        order = np.roll(order, 1)
    return np.concatenate([blocks[index] for index in order])


def _block_sensitivity(
    estimator: Any,
    frame: pd.DataFrame,
    target: str,
    feature_names: list[str],
    provenance: dict[str, dict[str, Any]],
    block_size: int,
    random_seed: int,
) -> dict[str, Any]:
    actual = frame[target].to_numpy(dtype=float)
    baseline = np.asarray(estimator.predict(frame[feature_names].to_numpy(dtype=float)), dtype=float).reshape(-1)
    baseline_mae = float(np.mean(np.abs(actual - baseline)))
    rng = np.random.default_rng(random_seed)
    features = []
    for name in feature_names:
        perturbed = frame[feature_names].copy()
        perturbed[name] = _permuted_blocks(perturbed[name].to_numpy(copy=True), block_size, rng)
        prediction = np.asarray(estimator.predict(perturbed.to_numpy(dtype=float)), dtype=float).reshape(-1)
        perturbed_mae = float(np.mean(np.abs(actual - prediction)))
        increase = perturbed_mae - baseline_mae
        features.append({
            "name": name,
            "mae_increase": increase,
            "baseline_mae": baseline_mae,
            "perturbed_mae": perturbed_mae,
            "provenance": provenance[name],
        })
    features.sort(key=lambda item: item["mae_increase"], reverse=True)
    return {
        "method": "chronological_block_permutation",
        "block_size": block_size,
        "random_seed": random_seed,
        "features": features,
    }


def _conditional_interactions(
    estimator: Any,
    frame: pd.DataFrame,
    feature_names: list[str],
    provenance: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    pairs = []
    for left, right in combinations(feature_names, 2):
        low, high = frame[left].quantile([0.25, 0.75]).tolist()
        strata = pd.qcut(frame[right], q=3, labels=False, duplicates="drop")
        contrasts = []
        for stratum in sorted(strata.dropna().unique()):
            rows = frame.loc[strata == stratum, feature_names]
            if rows.empty:
                continue
            low_rows = rows.copy()
            high_rows = rows.copy()
            low_rows[left] = low
            high_rows[left] = high
            low_prediction = np.asarray(estimator.predict(low_rows.to_numpy(dtype=float)), dtype=float).reshape(-1)
            high_prediction = np.asarray(estimator.predict(high_rows.to_numpy(dtype=float)), dtype=float).reshape(-1)
            contrasts.append(float(np.mean(high_prediction - low_prediction)))
        strength = float(np.std(contrasts)) if len(contrasts) > 1 else 0.0
        pairs.append({
            "feature": left,
            "conditioning_feature": right,
            "strength": strength,
            "stratum_contrasts": contrasts,
            "feature_provenance": provenance[left],
            "conditioning_provenance": provenance[right],
            "evidence_status": "model_inferred",
        })
    pairs.sort(key=lambda item: item["strength"], reverse=True)
    return {
        "method": "conditional_quantile_perturbation",
        "conditioning": "within_feature_quantile_strata",
        "pairs": pairs,
    }


def explain_time_series_model(
    estimator: Any,
    frame: pd.DataFrame,
    *,
    target: str,
    feature_names: list[str],
    source_columns: list[str],
    time_column: str,
    evaluation_protocol: str,
    block_size: int = 8,
    random_seed: int = 42,
) -> dict[str, Any]:
    """Explain a fitted estimator using time-aware perturbations and provenance."""
    if not hasattr(estimator, "predict"):
        raise ValueError("time-series estimator is not fitted")
    if isinstance(block_size, bool) or not isinstance(block_size, int) or block_size < 1:
        raise ValueError("block_size must be a positive integer")
    if isinstance(random_seed, bool) or not isinstance(random_seed, int):
        raise ValueError("random_seed must be an integer")
    if not feature_names:
        raise ValueError("persisted time-series model has no engineered feature metadata")
    missing = [name for name in [target, *feature_names] if name not in frame.columns]
    if missing:
        raise ValueError(f"Missing explanation columns: {missing}")
    usable = frame.dropna(subset=[target, *feature_names]).copy()
    finite = np.isfinite(usable[[target, *feature_names]].to_numpy(dtype=float)).all(axis=1)
    usable = usable.loc[finite].reset_index(drop=True)
    if len(usable) < 3:
        raise ValueError("time-series explanation requires at least 3 complete feature rows")

    provenance = {
        name: feature_provenance(name, source_columns, time_column)
        for name in feature_names
    }
    importance_method, importance = _importance_values(estimator, len(feature_names))
    importance_features = [
        {"name": name, "importance": float(value), "provenance": provenance[name]}
        for name, value in zip(feature_names, importance)
    ]
    importance_features.sort(key=lambda item: item["importance"], reverse=True)
    expected_value = float(np.mean(estimator.predict(usable[feature_names].to_numpy(dtype=float))))

    return {
        "feature_importance": {
            "method": importance_method,
            "shap_compatible": True,
            "expected_value": expected_value,
            "features": importance_features,
        },
        "sensitivity": _block_sensitivity(
            estimator, usable, target, feature_names, provenance, block_size, random_seed,
        ),
        "interactions": _conditional_interactions(estimator, usable, feature_names, provenance),
        "metadata": {
            "analysis_type": "time_series_explanation",
            "evidence_status": "model_inferred",
            "causal_claim": False,
            "interpretation": "predictive_association_only",
            "requires_experimental_confirmation": True,
            "recommended_confirmation": "targeted_doe_or_engineering_experiment",
            "evaluation_protocol": evaluation_protocol,
        },
    }
