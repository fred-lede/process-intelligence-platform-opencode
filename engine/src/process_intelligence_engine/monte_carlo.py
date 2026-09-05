"""Monte Carlo simulation engine with DOE prediction and anomaly handling."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from .copula import compute_joint_probabilities, CopulaResult
from .spc import compute_capability


def sample_from_distribution(
    values: list[float],
    dist_name: str = "normal",
    n: int = 1000,
    seed: int | None = None,
) -> list[float]:
    """Sample from a statistical distribution or fall back to histogram sampling.

    Supported distributions: ``"normal"``, ``"gamma"``, ``"lognormal"``.
    Unknown distribution names fall back to resampling from the input values.
    """
    rng = np.random.default_rng(seed)
    arr = np.array(values, dtype=float)

    if dist_name == "normal" and len(arr) >= 2:
        mu, sigma = float(arr.mean()), float(arr.std(ddof=1))
        if sigma <= 0:
            sigma = 1.0
        return rng.normal(mu, sigma, n).tolist()

    if dist_name == "gamma" and len(arr) >= 2:
        mu, sigma = float(arr.mean()), float(arr.std(ddof=1))
        if sigma <= 0:
            sigma = 1.0
        k = (mu / sigma) ** 2
        theta = sigma ** 2 / mu
        return rng.gamma(k, theta, n).tolist()

    if dist_name == "lognormal" and len(arr) >= 2:
        mu, sigma = float(arr.mean()), float(arr.std(ddof=1))
        if sigma <= 0:
            sigma = 1.0
        log_mu = math.log(mu / math.sqrt(1.0 + (sigma / mu) ** 2))
        log_sigma = math.sqrt(math.log(1.0 + (sigma / mu) ** 2))
        return rng.lognormal(log_mu, log_sigma, n).tolist()

    # Histogram / empirical resampling fallback
    if len(arr) > 0:
        indices = rng.integers(0, len(arr), n)
        return arr[indices].tolist()
    return [0.0] * n


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
) -> float:
    """Predict output using model coefficients.

    Supports ``"doe_linear"``, ``"doe_quadratic"``, ``"logistic_regression"``,
    and ``"weibull_regression"``.
    """
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
                for key in (f"{xi}_x_{xj}", f"{xi}*{xj}", f"{xi}{xj}"):
                    if key in coefficients:
                        result += coefficients[key] * xi_val * xj_val
                        break
        return result

    if model_type == "logistic_regression":
        logit = float(coefficients.get("_intercept", 0.0))
        for x in input_names:
            logit += float(coefficients.get(x, 0.0)) * inputs[x]
        # sigmoid → predicted P(NG) in [0, 1]
        return 1.0 / (1.0 + math.exp(-logit))

    if model_type == "weibull_regression":
        intercept = float(coefficients.get("_intercept", 0.0))
        k = float(coefficients.get("_weibull_shape", 1.0))
        log_lambda = intercept
        for x in input_names:
            log_lambda += float(coefficients.get(x, 0.0)) * inputs[x]
        lambda_val = math.exp(log_lambda)
        # mean time-to-failure = lambda * Gamma(1 + 1/k)
        from scipy.special import gamma
        mean_ttf = lambda_val * gamma(1.0 + 1.0 / k)
        return float(mean_ttf)

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

    # Sample input distributions from historical data
    sampled_inputs: dict[str, np.ndarray] = {}
    for col in input_columns:
        col_data = df[col].to_numpy(dtype=float)
        sampled_inputs[col] = np.array(sample_from_distribution(col_data.tolist(), n=n_simulations, seed=rng.integers(0, 2**31)))

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

    # Predict outputs
    output_values = np.array([
        predict_output(model_type, coefficients, {col: sampled_inputs[col][i] for col in input_columns})
        for i in range(n_simulations)
    ], dtype=float)

    # Basic statistics
    output_mean = float(np.mean(output_values))
    output_std = float(np.std(output_values, ddof=1)) if n_simulations > 1 else 0.0
    output_median = float(np.median(output_values))

    percentiles = {
        "p1": float(np.percentile(output_values, 1)),
        "p5": float(np.percentile(output_values, 5)),
        "p50": float(np.percentile(output_values, 50)),
        "p95": float(np.percentile(output_values, 95)),
        "p99": float(np.percentile(output_values, 99)),
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
                })
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
            predict_output(model_type, coefficients, {col: multi_inputs[col][i] for col in input_columns})
            for i in range(n_simulations)
        ], dtype=float)
        if lsl is not None:
            multi_anomaly_ng = int(np.sum(multi_outputs < lsl))
        else:
            multi_anomaly_ng = 0
    else:
        multi_anomaly_ng = 0

    return {
        "n_simulations": n_simulations,
        "seed": seed,
        "ng_count": ng_count,
        "ng_probability": ng_probability,
        "output_mean": output_mean,
        "output_std": output_std,
        "output_median": output_median,
        "percentiles": percentiles,
        "histogram": _compute_histogram(output_values),
        "cdf_data": _compute_cdf(output_values),
        "boxplot_data": _compute_boxplot(output_values),
        "anomaly_rankings": anomaly_rankings,
        "multi_anomaly_ng": multi_anomaly_ng,
        "violations": violations,
        "capability": compute_capability(output_values, lsl=lsl, usl=usl, subgroup_size=1),
        "output_values": output_values.tolist(),
        "copula": copula_result.to_dict() if copula_result else None,
    }
