"""Monte Carlo simulation engine with DOE prediction and anomaly handling."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from .copula import compute_joint_probabilities, CopulaResult
from .spc import compute_capability


def sample_with_name(
    values: list[float],
    dist_name: str = "normal",
    n: int = 1000,
    seed: int | None = None,
    params: dict[str, Any] | None = None,
    mean_override: float | None = None,
) -> tuple[list[float], str]:
    """Sample from a statistical distribution; return (samples, applied_name).

    Supported: normal/gamma/lognormal/uniform/triangular/weibull/poisson.
    Failed fits and unknown names fall back to empirical resampling, and
    the applied name reflects what was actually used so callers record
    truthful sampling metadata.

    mean_override: shift the location (mean) to the given value while
    keeping the data's spread (sigma/range width). This is the "mu = DOE
    best point, sigma = machine precision" process-tuning semantics.
    """
    rng = np.random.default_rng(seed)
    arr = np.array(values, dtype=float)
    params = params or {}

    if dist_name == "normal" and len(arr) >= 2:
        mu = float(mean_override) if mean_override is not None else float(arr.mean())
        sigma = float(arr.std(ddof=1))
        if sigma <= 0:
            sigma = 1.0
        return rng.normal(mu, sigma, n).tolist(), "normal"

    if dist_name == "gamma" and len(arr) >= 2:
        mu, sigma = float(arr.mean()), float(arr.std(ddof=1))
        if sigma <= 0:
            sigma = 1.0
        k = (mu / sigma) ** 2
        theta = sigma ** 2 / mu
        return rng.gamma(k, theta, n).tolist(), "gamma"

    if dist_name == "lognormal" and len(arr) >= 2:
        mu = float(mean_override) if mean_override is not None else float(arr.mean())
        sigma = float(arr.std(ddof=1))
        if mu > 0 and sigma > 0:
            log_mu = math.log(mu / math.sqrt(1.0 + (sigma / mu) ** 2))
            log_sigma = math.sqrt(math.log(1.0 + (sigma / mu) ** 2))
            return rng.lognormal(log_mu, log_sigma, n).tolist(), "lognormal"
        # 非正均值/零變異 → empirical fallback（lognormal 物理上恆正）

    if dist_name == "uniform" and len(arr) >= 2:
        lo, hi = float(arr.min()), float(arr.max())
        if hi > lo:
            if mean_override is not None:
                # 保留範圍寬度，以 mean_override 為中心平移
                half = (hi - lo) / 2.0
                lo, hi = mean_override - half, mean_override + half
            return rng.uniform(lo, hi, n).tolist(), "uniform"

    if dist_name == "triangular" and len(arr) >= 2:
        lo, hi = float(arr.min()), float(arr.max())
        if hi > lo:
            mode = params.get("mode")
            if mode is None and params.get("params"):
                p = params["params"]
                if isinstance(p, (list, tuple)) and len(p) >= 2:
                    mode = float(p[1])
            if mode is None:
                mode = (lo + hi) / 2
            mode = min(max(float(mode), lo), hi)  # clamp 進 [lo, hi]
            if mean_override is not None:
                # 保留形狀：mode 的相對位置不變，整體平移至 mean_override
                width = hi - lo
                rel = (mode - lo) / width
                lo, hi = mean_override - width / 2.0, mean_override + width / 2.0
                mode = lo + rel * width
            return rng.triangular(lo, mode, hi, n).tolist(), "triangular"

    if dist_name == "weibull" and len(arr) >= 2:
        try:
            from scipy.stats import weibull_min
            positive = arr[arr > 0]
            if positive.size < 2:
                raise ValueError("weibull needs positive data")
            shape, loc, scale = weibull_min.fit(positive, floc=0)
            # rng.weibull 回傳標準 Weibull（scale=1）；須乘回擬合的 scale，
            # 否則抽樣值量級錯誤（差 1/scale 倍）。
            if mean_override is not None:
                # 保留 shape，調整 scale 使 E[X] = mean_override
                from scipy.special import gamma as _gamma
                expected_unit = _gamma(1.0 + 1.0 / shape)
                scale = float(mean_override) / expected_unit
                if scale <= 0:
                    raise ValueError("weibull mean_override must be positive")
            return (scale * rng.weibull(shape, n)).tolist(), "weibull"
        except Exception:
            pass  # fall through to empirical fallback

    if dist_name == "poisson" and len(arr) >= 2:
        lam = float(mean_override) if mean_override is not None else float(arr.mean())
        integerish = bool(np.all(arr == np.round(arr))) if bool(np.isfinite(arr).all()) else False
        if lam > 0 and lam < 9e18 and (integerish or mean_override is not None):
            try:
                return rng.poisson(lam, n).astype(float).tolist(), "poisson"
            except (ValueError, OverflowError):
                pass  # 超大 λ → empirical fallback

    # Histogram / empirical resampling fallback
    if len(arr) > 0:
        indices = rng.integers(0, len(arr), n)
        return arr[indices].tolist(), "empirical"
    return [0.0] * n, "empirical"


def sample_from_distribution(
    values: list[float],
    dist_name: str = "normal",
    n: int = 1000,
    seed: int | None = None,
) -> list[float]:
    """Backward-compatible wrapper: samples only (no applied name)."""
    samples, _ = sample_with_name(values, dist_name=dist_name, n=n, seed=seed)
    return samples


def _get_magnitude(anomaly: dict[str, Any], rng: np.random.Generator) -> float:
    """Extract a scalar magnitude from an anomaly dict, handling both formats."""
    if "magnitude" in anomaly:
        return float(anomaly["magnitude"])
    mag_dist = anomaly.get("magnitude_distribution", {})
    mag_type = mag_dist.get("type", "constant")
    if mag_type == "constant":
        return float(mag_dist.get("value", 0.0))
    if mag_type == "normal":
        loc = float(mag_dist.get("loc", 0.0))
        scale = float(mag_dist.get("scale", 1.0))
        return float(rng.normal(loc, scale))
    if mag_type == "gamma":
        loc = float(mag_dist.get("loc", 0.0))
        scale = float(mag_dist.get("scale", 1.0))
        shape = float(mag_dist.get("value", 1.0))
        return float(rng.gamma(shape, scale) + loc)
    return 0.0


def apply_anomalies(
    values: list[float],
    anomalies: list[dict[str, Any]] | None,
    rng: np.random.Generator,
    copula_result: CopulaResult | None = None,
) -> list[float]:
    """Apply anomaly events to input values based on occurrence probability.

    Each anomaly is checked independently; when triggered the magnitude is
    added (direction ``"above"``) or subtracted (direction ``"below"``).

    If a ``copula_result`` is provided, joint occurrence probabilities are
    used to determine correlated anomaly events.
    """
    if not anomalies:
        return list(values)

    result = list(values)
    n_anomalies = len(anomalies)
    ids = [a.get("anomaly_id", f"anomaly_{j}") for j, a in enumerate(anomalies)]
    probs = np.array([a.get("occurrence_probability", 0.0) for a in anomalies])

    for i in range(len(result)):
        if copula_result and copula_result.mode != "independent" and n_anomalies >= 2:
            # Sample joint occurrence pattern from Copula
            u = rng.uniform(0, 1, n_anomalies)
            for j in range(n_anomalies):
                if u[j] > probs[j]:
                    continue
                anomaly = anomalies[j]
                magnitude = _get_magnitude(anomaly, rng)
                direction = anomaly.get("direction", "above")
                if direction == "below":
                    result[i] -= magnitude
                else:
                    result[i] += magnitude
        else:
            # Original independent behavior
            for anomaly in anomalies:
                if rng.random() >= anomaly.get("occurrence_probability", 0.0):
                    continue
                magnitude = _get_magnitude(anomaly, rng)
                direction = anomaly.get("direction", "above")
                if direction == "below":
                    result[i] -= magnitude
                else:
                    result[i] += magnitude
    return result


def predict_output(
    model_type: str,
    coefficients: dict[str, float],
    inputs: dict[str, float],
    model: Any = None,
    feature_names: list[str] | None = None,
) -> float:
    """Predict output using model coefficients or trained model object.

    Supports all model types: doe_linear, doe_quadratic, doe_categorical_factorial, logistic_regression,
    weibull_regression, random_forest, xgboost, lightgbm, residual_hybrid.

    ``feature_names`` must be the fitted input order: deriving it from the dict
    keys silently permutes the columns whenever training order is not
    alphabetical.
    """
    # Use trained model object when available (tree models)
    if model is not None:
        try:
            if model_type == "doe_categorical_factorial":
                order = list(feature_names) if feature_names else list(inputs.keys())
                frame = pd.DataFrame([{col: inputs[col] for col in order}])
                return float(model.predict(frame)[0])
            if model_type in ("doe_linear", "doe_quadratic"):
                input_names = list(inputs.keys())
                values = [float(inputs.get(col, 0.0)) for col in input_names]
                # Match fitters._design_matrix exactly: intercept, then each
                # input (and its square), followed by pairwise interactions.
                features = [1.0]
                for value in values:
                    features.append(value)
                    if model_type == "doe_quadratic":
                        features.append(value * value)
                if model_type == "doe_quadratic":
                    features.extend(
                        values[i] * values[j]
                        for i in range(len(values))
                        for j in range(i + 1, len(values))
                    )
                input_array = np.array([features])
            else:
                order = list(feature_names) if feature_names else sorted(inputs.keys())
                input_array = np.array([[float(inputs.get(col, 0.0)) for col in order]])
            pred = model.predict(input_array)
            return float(pred[0])
        except Exception:
            pass

    input_names = sorted(inputs.keys())

    if model_type == "doe_linear":
        result = float(coefficients.get("_intercept", 0.0))
        for x in input_names:
            result += float(coefficients.get(x, 0.0)) * inputs[x]
        return result

    if model_type == "doe_quadratic":
        result = float(coefficients.get("_intercept", 0.0))
        for x in input_names:
            c = coefficients.get(x, 0.0)
            result += c * inputs[x]
        for i, xi in enumerate(input_names):
            xi_val = inputs[xi]
            for key in (f"{xi}_x_{xi}", f"{xi}^2", f"{xi}{xi}"):
                if key in coefficients:
                    result += coefficients[key] * xi_val ** 2
                    break
            for xj in input_names[i + 1:]:
                xj_val = inputs[xj]
                for key in (
                    f"{xi}_x_{xj}", f"{xj}_x_{xi}",
                    f"{xi}*{xj}", f"{xj}*{xi}",
                    f"{xi}{xj}", f"{xj}{xi}",
                ):
                    if key in coefficients:
                        result += coefficients[key] * xi_val * xj_val
                        break
        return result

    if model_type == "doe_categorical_factorial":
        raise ValueError("categorical DOE Monte Carlo requires the fitted model artifact")

    if model_type == "logistic_regression":
        logit = float(coefficients.get("_intercept", 0.0))
        for x in input_names:
            logit += float(coefficients.get(x, 0.0)) * inputs[x]
        return 1.0 / (1.0 + math.exp(-logit))

    if model_type == "weibull_regression":
        intercept = float(coefficients.get("_intercept", 0.0))
        k = float(coefficients.get("_weibull_shape", 1.0))
        log_lambda = intercept
        for x in input_names:
            log_lambda += float(coefficients.get(x, 0.0)) * inputs[x]
        log_lambda = max(min(log_lambda, 700.0), -700.0)
        lambda_val = float(np.exp(log_lambda))
        from scipy.special import gamma
        return float(lambda_val * gamma(1.0 + 1.0 / k))

    raise ValueError(f"Unknown model_type: {model_type}")


def _compute_histogram(
    output_values: np.ndarray, n_bins: int = 30
) -> dict[str, list]:
    counts, bin_edges = np.histogram(output_values, bins=n_bins)
    bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
    return {
        "bins": bin_centers.tolist(),
        "counts": counts.tolist(),
    }


def _compute_cdf(output_values: np.ndarray) -> dict[str, list]:
    sorted_vals = np.sort(output_values)
    cdf = np.arange(1, len(sorted_vals) + 1) / len(sorted_vals)
    return {
        "x": sorted_vals.tolist(),
        "y": cdf.tolist(),
    }


def _compute_boxplot(output_values: np.ndarray) -> dict[str, float]:
    return {
        "min": float(np.min(output_values)),
        "q1": float(np.percentile(output_values, 25)),
        "median": float(np.median(output_values)),
        "q3": float(np.percentile(output_values, 75)),
        "max": float(np.max(output_values)),
    }


def run_monte_carlo(
    df: pd.DataFrame,
    model_type: str,
    coefficients: dict[str, float],
    input_columns: list[str],
    output_column: str,
    n_simulations: int = 10000,
    seed: int = 42,
    enable_anomalies: bool = False,
    anomalies: list[dict[str, Any]] | None = None,
    lsl: float | None = None,
    usl: float | None = None,
    model: Any = None,
    sampling_method: str = "bootstrap",
    input_distributions: dict[str, dict[str, Any]] | None = None,
    input_means: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Run a full Monte Carlo simulation.

    Parameters
    ----------
    df : pd.DataFrame
        Source data containing input columns.
    model_type : str
        One of ``"doe_linear"``, ``"doe_quadratic"``, ``"logistic_regression"``,
        or ``"weibull_regression"``.
    coefficients : dict
        DOE model coefficients.
    input_columns : list[str]
        Column names used as model inputs.
    output_column : str
        Name of the target column (used for distribution sampling).
    n_simulations : int
        Number of simulation runs.
    seed : int
        Random seed for reproducibility.
    enable_anomalies : bool
        Whether to inject anomaly events.
    anomalies : list[dict] | None
        Anomaly definitions.
    lsl : float | None
        Lower specification limit.
    usl : float | None
        Upper specification limit.

    Returns
    -------
    dict
        Simulation results including statistics, histograms, and violation counts.
    """
    rng = np.random.default_rng(seed)

    # Bootstrap complete historical rows to preserve correlations between inputs.
    # Independent per-column draws can create impossible combinations for
    # quadratic/interacting DOE models and extreme artificial outputs.
    sampled_inputs: dict[str, np.ndarray] = {}
    applied_distributions: dict[str, dict[str, Any]] = {}
    if sampling_method == "auto" and input_distributions:
        for col in input_columns:
            values = df[col].to_numpy(dtype=float)
            spec = input_distributions.get(col, {})
            name = str(spec.get("name", "empirical")).lower()
            normed = {
                "normal": "normal", "norm": "normal",
                "triangular": "triangular", "triangle": "triangular",
                "uniform": "uniform",
                "lognormal": "lognormal", "lognorm": "lognormal",
                "weibull": "weibull",
                "poisson": "poisson",
            }.get(name)
            if normed and len(values) >= 2:
                # 呼叫 sample_with_name 取得 (samples, applied_name)；
                # applied_name 反映實際套用（fit 失敗 fallback 時為 empirical），
                # 統計報告不再宣稱未真正使用的分佈。
                mean_override = (input_means or {}).get(col)
                seed_i = int(rng.integers(1 << 31))
                tri_params: dict[str, Any] | None = None
                if normed == "triangular" and spec.get("params"):
                    p = spec["params"]
                    if isinstance(p, (list, tuple)) and len(p) >= 2:
                        tri_params = {"mode": float(p[1])}
                samples, applied_name = sample_with_name(
                    values.tolist(), dist_name=normed,
                    n=n_simulations, seed=seed_i, params=tri_params,
                    mean_override=mean_override)
                sampled_inputs[col] = np.asarray(samples, dtype=float)
                entry: dict[str, Any] = {"name": applied_name}
                if mean_override is not None:
                    entry["mean_override"] = float(mean_override)
                if applied_name == "normal":
                    entry.update(mean=mean_override if mean_override is not None else float(np.mean(values)),
                                 std=float(np.std(values, ddof=1)))
                elif applied_name == "uniform":
                    entry.update(min=float(np.min(values)), max=float(np.max(values)))
                elif applied_name == "triangular":
                    lo, hi = float(np.min(values)), float(np.max(values))
                    mode = tri_params["mode"] if tri_params else (lo + hi) / 2
                    entry.update(min=lo, max=hi, mode=mode)
                applied_distributions[col] = entry
            else:
                row_indices = rng.integers(0, len(df), size=n_simulations)
                sampled_inputs[col] = values[row_indices]
                applied_distributions[col] = {"name": "empirical"}
    elif sampling_method == "normal":
        for col in input_columns:
            values = df[col].to_numpy(dtype=float)
            sigma = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
            sampled_inputs[col] = rng.normal(float(np.mean(values)), sigma, n_simulations) if sigma > 0 else np.full(n_simulations, float(values[0]))
    else:
        sampling_method = "bootstrap"
        row_indices = rng.integers(0, len(df), size=n_simulations)
        for col in input_columns:
            sampled_inputs[col] = df[col].to_numpy(dtype=float)[row_indices]

    # Track whether anomaly injection or a future sampling strategy produces
    # values outside the model's observed training range.
    training_ranges = {
        col: {
            "min": float(df[col].min()),
            "max": float(df[col].max()),
        }
        for col in input_columns
    }

    # Apply anomalies to each input column
    copula_result: CopulaResult | None = None
    if enable_anomalies and anomalies:
        # Compute joint occurrence probabilities if multiple anomalies
        if len(anomalies) >= 2:
            corr_matrix = [a.get("correlation_matrix", []) for a in anomalies]
            # Check if any anomaly has a correlation_matrix (pairwise)
            has_correlation = any(
                a.get("correlation_matrix") for a in anomalies
            )
            if has_correlation:
                # Build correlation matrix from anomaly data
                n_a = len(anomalies)
                corr = np.eye(n_a)
                for a in anomalies:
                    if "correlation_matrix" in a and a["correlation_matrix"]:
                        cm = a["correlation_matrix"]
                        if len(cm) == n_a:
                            corr = np.array(cm, dtype=float)
                copula_result = compute_joint_probabilities(
                    anomalies, correlation_matrix=corr.tolist(), seed=seed
                )
            else:
                copula_result = compute_joint_probabilities(
                    anomalies, seed=seed
                )
        for col in input_columns:
            sampled_inputs[col] = np.array(
                apply_anomalies(sampled_inputs[col].tolist(), anomalies, rng, copula_result)
            )

    extrapolation_mask = np.zeros(n_simulations, dtype=bool)
    for col, limits in training_ranges.items():
        extrapolation_mask |= (
            (sampled_inputs[col] < limits["min"])
            | (sampled_inputs[col] > limits["max"])
        )

    # Predict outputs
    output_values = np.array([
        predict_output(model_type, coefficients, {col: sampled_inputs[col][i] for col in input_columns}, model=model, feature_names=input_columns)
        for i in range(n_simulations)
    ], dtype=float)

    # Basic statistics
    output_mean = float(np.mean(output_values))
    output_std = float(np.std(output_values, ddof=1)) if n_simulations > 1 else 0.0
    output_median = float(np.median(output_values))

    percentiles = {
        "p0_1": float(np.percentile(output_values, 0.1)),
        "p1": float(np.percentile(output_values, 1)),
        "p5": float(np.percentile(output_values, 5)),
        "p50": float(np.percentile(output_values, 50)),
        "p95": float(np.percentile(output_values, 95)),
        "p99": float(np.percentile(output_values, 99)),
        "p99_9": float(np.percentile(output_values, 99.9)),
    }

    # Specification violation counting
    ng_count = 0
    multi_anomaly_ng = 0
    violations: list[dict[str, Any]] = []

    if lsl is not None or usl is not None:
        below_lsl = output_values < (lsl or -np.inf)
        above_usl = output_values > (usl or np.inf)
        ng_mask = below_lsl | above_usl
        ng_count = int(np.sum(ng_mask))
        ng_probability = float(ng_count) / n_simulations if n_simulations > 0 else 0.0

        if lsl is not None:
            for i in np.where(below_lsl)[0]:
                violations.append({"index": int(i), "value": float(output_values[i]), "type": "below_lsl", "limit": lsl})
        if usl is not None:
            for i in np.where(above_usl)[0]:
                violations.append({"index": int(i), "value": float(output_values[i]), "type": "above_usl", "limit": usl})
    else:
        ng_count = 0
        # For logistic_regression, each output is P(NG) → use mean as ng_probability
        ng_probability = float(np.mean(output_values)) if model_type == "logistic_regression" else 0.0

    # Anomaly rankings (which anomalies contribute most to NG)
    anomaly_rankings: list[dict[str, Any]] = []
    if enable_anomalies and anomalies and lsl is not None:
        for idx, anomaly in enumerate(anomalies):
            target = anomaly.get("target_input", "")
            if not target or target not in sampled_inputs:
                continue
            target_col = sampled_inputs[target]
            modified = apply_anomalies(target_col.tolist(), [anomaly], rng)
            modified_arr = np.array(modified, dtype=float)
            shifted_outputs = np.array([
                predict_output(model_type, coefficients, {
                    col: (modified_arr if col == target else sampled_inputs[col])[i]
                    for col in input_columns
                }, model=model, feature_names=input_columns)
                for i in range(n_simulations)
            ])
            shift_ng = int(np.sum(shifted_outputs < lsl))
            anomaly_rankings.append({
                "anomaly_id": anomaly.get("anomaly_id", f"anomaly_{idx}"),
                "target_input": target,
                "ng_count": shift_ng,
                "ng_probability": shift_ng / n_simulations if n_simulations > 0 else 0.0,
            })
        anomaly_rankings.sort(key=lambda x: x["ng_count"], reverse=True)

    # Multi-anomaly NG (all anomalies active simultaneously)
    if enable_anomalies and anomalies:
        multi_inputs = {col: list(sampled_inputs[col]) for col in input_columns}
        for anomaly in anomalies:
            target = anomaly.get("target_input", "")
            if target in multi_inputs:
                multi_inputs[target] = apply_anomalies(multi_inputs[target], [anomaly], rng)
        multi_outputs = np.array([
            predict_output(model_type, coefficients, {col: multi_inputs[col][i] for col in input_columns}, model=model, feature_names=input_columns)
            for i in range(n_simulations)
        ], dtype=float)
        if lsl is not None:
            multi_anomaly_ng = int(np.sum(multi_outputs < lsl))
        else:
            multi_anomaly_ng = 0
    else:
        multi_anomaly_ng = 0

    # DPMO / Z-scores（僅在規格界存在時有意義）
    dpmo: float | None = None
    z_lsl = z_usl = None
    if lsl is not None or usl is not None:
        dpmo = float(ng_probability) * 1e6
        if output_std > 0:
            if lsl is not None:
                z_lsl = (output_mean - lsl) / output_std
            if usl is not None:
                z_usl = (usl - output_mean) / output_std

    return {
        "n_simulations": n_simulations,
        "seed": seed,
        "sampling_method": sampling_method,
        "input_distributions": applied_distributions,
        "ng_count": ng_count,
        "ng_probability": ng_probability,
        "output_mean": output_mean,
        "output_std": output_std,
        "output_median": output_median,
        "percentiles": percentiles,
        "dpmo": dpmo,
        "z_lsl": z_lsl,
        "z_usl": z_usl,
        "histogram": _compute_histogram(output_values),
        "cdf_data": _compute_cdf(output_values),
        "boxplot_data": _compute_boxplot(output_values),
        "anomaly_rankings": anomaly_rankings,
        "multi_anomaly_ng": multi_anomaly_ng,
        "violations": violations,
        "capability": compute_capability(output_values, lsl=lsl, usl=usl, subgroup_size=1),
        "output_values": output_values.tolist(),
        "copula": copula_result.to_dict() if copula_result else None,
        "training_input_ranges": training_ranges,
        "extrapolation_count": int(np.sum(extrapolation_mask)),
        "extrapolation_rate": float(np.mean(extrapolation_mask)) if n_simulations else 0.0,
    }
