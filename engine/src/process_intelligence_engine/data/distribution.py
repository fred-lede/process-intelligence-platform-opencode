"""Distribution fitting.

Fits a set of candidate distributions to numeric data, ranks them by AIC,
and reports KS test results plus histogram info. All outputs are plain
Python types so they serialize cleanly to JSON for IPC.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy import stats

SUPPORTED_DISTRIBUTIONS = [
    "normal",
    "lognormal",
    "uniform",
    "triangular",
    "weibull",
    "gamma",
    "beta",
    "poisson",
    "negative_binomial",
    "empirical",
]


@dataclass
class DistributionFit:
    """A single fitted distribution candidate."""

    name: str
    params: dict[str, float]
    aic: float
    bic: float
    ks_statistic: float
    ks_p_value: float
    loglik: float
    skewness: float | None
    kurtosis: float | None
    histogram: dict[str, list[float]]
    pdf: dict[str, list[float]] = field(
        default_factory=lambda: {"x": [], "y": []},
        repr=False,
    )


# Backward-compatible alias: both names resolve to the same type.
FitResult = DistributionFit


def _clean_numeric(values: list) -> np.ndarray:
    out = []
    for v in values:
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if math.isnan(f) or math.isinf(f):
            continue
        out.append(f)
    return np.asarray(out, dtype=float)


def _hist_bins(series: np.ndarray, name: str) -> tuple[list[float], list[float]]:
    """Return (counts, edges) using scipy's histogram rule."""
    if series.size == 0:
        return [], []
    bins = min(30, max(5, int(np.sqrt(len(series)))))
    counts, edges = np.histogram(series, bins=bins)
    return counts.tolist(), edges.tolist()


def _fit_continuous(
    series: np.ndarray,
    dist: Any,
    name: str,
) -> DistributionFit | None:
    """Fit a continuous scipy distribution; returns None if the fit fails."""
    data = series
    try:
        if name in {"beta", "gamma", "lognormal"}:
            # These require strictly positive data or are fit on lower bounds.
            if name in {"beta"}:
                if data.min() <= 0 or data.max() >= 1:
                    # beta needs (0,1); scale-free beta has issues. Skip.
                    return None
                params = dist.fit(data, floc=0, fscale=1)
            elif name == "gamma":
                if data.min() <= 0:
                    # shift so min > 0
                    shifted = data - data.min() + 1e-6
                else:
                    shifted = data
                params = dist.fit(shifted, floc=0)
            else:  # lognormal
                if data.min() <= 0:
                    shifted = data - data.min() + 1e-6
                else:
                    shifted = data
                params = dist.fit(shifted, floc=0)
        elif name == "uniform":
            params = dist.fit(data)
        elif name == "triangular":
            params = dist.fit(data)
        else:
            params = dist.fit(data)
    except Exception:
        return None

    try:
        loglik = dist.logpdf(data, *params).sum()
        k = len(params)
        n = len(data)
        aic = 2 * k - 2 * loglik
        bic = k * math.log(n) - 2 * loglik
        ks_stat, ks_p = stats.kstest(data, dist.cdf, args=params)
    except Exception:
        return None

    params_dict = _params_dict(name, params)
    return DistributionFit(
        name=name,
        params=params_dict,
        aic=float(aic),
        bic=float(bic),
        ks_statistic=float(ks_stat),
        ks_p_value=float(ks_p),
        loglik=float(loglik),
        skewness=float(stats.skew(data)) if data.size > 2 else None,
        kurtosis=float(stats.kurtosis(data)) if data.size > 2 else None,
        histogram=_to_hist(data),
        pdf=_pdf_curve(name, params_dict, data),
    )


def _params_dict(name: str, params: tuple) -> dict[str, float]:
    """Map positionally-fitted scipy params to readable keys."""
    mapping: dict[str, list[str]] = {
        "normal": ["loc", "scale"],
        "lognormal": ["shape", "loc", "scale"],
        "uniform": ["loc", "scale"],
        "triangular": ["c", "loc", "scale"],
        "weibull": ["shape", "loc", "scale"],
        "gamma": ["shape", "loc", "scale"],
        "beta": ["a", "b", "loc", "scale"],
        "poisson": ["mu"],
        "negative_binomial": ["n", "p"],
    }
    keys = mapping.get(name, [f"p{i}" for i in range(len(params))])
    return {k: float(v) for k, v in zip(keys, params)}


# Name -> (scipy distribution "name", whether it uses pmf instead of pdf)
_CPDFS: dict[str, tuple[str, bool]] = {
    "normal": ("norm", False),
    "lognormal": ("lognorm", False),
    "uniform": ("uniform", False),
    "triangular": ("triang", False),
    "weibull": ("weibull_min", False),
    "gamma": ("gamma", False),
    "beta": ("beta", False),
    "poisson": ("poisson", True),
    "negative_binomial": ("nbinom", True),
}


def _pdf_curve(
    name: str,
    params: dict[str, float],
    series: np.ndarray,
    npts: int = 160,
) -> dict[str, list[float]]:
    """Evaluate the fitted pdf/pmf curve over the data domain.

    Returns {"x": [...], "y": [...]}. For empirical fits returns empty
    curves (the histogram itself is the empirical distribution).
    """
    if name == "empirical" or series.size == 0:
        return {"x": [], "y": []}

    entry = _CPDFS.get(name)
    if entry is None:
        return {"x": [], "y": []}
    scipy_name, is_discrete = entry
    dist = getattr(stats, scipy_name)

    # Reconstruct the positional parameter vector for the scipy call.
    keys = list(params.keys())
    arg_values = [params[k] for k in keys]

    xmin = float(series.min())
    xmax = float(series.max())
    pad = (xmax - xmin) * 0.08
    if pad <= 0:
        pad = 1.0

    if is_discrete:
        xs = np.arange(max(xmin - pad, 0), xmax + pad + 1)
        try:
            ys = dist.pmf(xs, *arg_values)
        except Exception:
            return {"x": [], "y": []}
        finite = np.isfinite(ys)
        return {
            "x": xs[finite].tolist(),
            "y": ys[finite].astype(float).tolist(),
        }

    xs = np.linspace(xmin - pad, xmax + pad, npts)
    try:
        ys = dist.pdf(xs, *arg_values)
        if not np.all(np.isfinite(ys)):
            return {"x": [], "y": []}
        return {"x": xs.tolist(), "y": ys.astype(float).tolist()}
    except Exception:
        return {"x": [], "y": []}


def _to_hist(data: np.ndarray) -> dict[str, list[float]]:
    counts, edges = _hist_bins(data, "auto")
    return {"counts": counts, "edges": edges}


def fit_best_distribution(
    values: list,
    top_n: int = 3,
) -> list[FitResult]:
    """Fit candidate distributions and rank them by AIC.

    Args:
        values: Numeric column values (non-numeric entries are skipped).
        top_n: How many best-fitting candidates to return.

    Returns:
        List of fits sorted ascending by AIC (best first).
    """
    series = _clean_numeric(values)
    if series.size == 0:
        return []

    # Small samples cannot support parametric fits; recommend empirical
    # distribution as the spec directs when a fit is unstable.
    if series.size < 10:
        return [_empirical_fit(series)]

    # Poisson / negative binomial: only meaningful for integer counts.
    is_integerish = bool(np.allclose(series, np.round(series)))

    candidates: list[DistributionFit] = []

    # Continuous fits (all scipy.rv_continuous)
    continuous: dict[str, Any] = {
        "normal": stats.norm,
        "lognormal": stats.lognorm,
        "uniform": stats.uniform,
        "triangular": stats.triang,
        "weibull": stats.weibull_min,
        "gamma": stats.gamma,
    }
    for name, dist in continuous.items():
        fitted = _fit_continuous(series, dist, name)
        if fitted is not None:
            candidates.append(fitted)

    if is_integerish:
        # Integer count distributions (fit via MLE on rounded data)
        ints = np.round(series).astype(int)
        for name in ["poisson", "negative_binomial"]:
            fitted = _fit_discrete(ints, name)
            if fitted is not None:
                candidates.append(fitted)

    # Empirical fallback always present (never crashes, always interpretable)
    empirical = _empirical_fit(series)
    candidates.append(empirical)

    # Sort by AIC ascending
    candidates.sort(key=lambda c: c.aic)

    return candidates[:top_n]


def _fit_discrete(ints: np.ndarray, name: str) -> DistributionFit | None:
    from scipy.stats import nbinom, poisson

    n = len(ints)
    try:
        if name == "poisson":
            mu = ints.mean()
            if mu <= 0:
                return None
            loglik = poisson.logpmf(ints, mu).sum()
            k = 1
            ks_stat, ks_p = stats.kstest(ints, "poisson", args=(mu,))
        else:  # negative_binomial
            # Method-of-moments initial estimate, then scipy fit on n, p
            mean = ints.mean()
            var = ints.var()
            if mean <= 0 or var <= mean:
                return None
            p = mean / var
            n_est = (mean * p) / (1 - p)
            params = (max(n_est, 1e-6), min(max(p, 1e-6), 1 - 1e-6))
            loglik = nbinom.logpmf(ints, params[0], params[1]).sum()
            k = 2
            ks_stat, ks_p = stats.kstest(ints, "nbinom", args=params)
    except Exception:
        return None

    aic = 2 * k - 2 * loglik
    bic = k * math.log(n) - 2 * loglik
    hist = _to_hist(ints.astype(float))
    params_dict = _params_dict(name, params if name == "negative_binomial" else (float(mu),))
    return DistributionFit(
        name=name,
        params=params_dict,
        aic=float(aic),
        bic=float(bic),
        ks_statistic=float(ks_stat),
        ks_p_value=float(ks_p),
        loglik=float(loglik),
        skewness=float(stats.skew(ints)) if n > 2 else None,
        kurtosis=float(stats.kurtosis(ints)) if n > 2 else None,
        histogram=hist,
        pdf=_pdf_curve(name, params_dict, ints.astype(float)),
    )


def _empirical_fit(series: np.ndarray) -> DistributionFit:
    """Empirical distribution-fit descriptor.

    AIC is computed from the histogram so it is comparable to parametric
    fits: each bin acts as a parameter. For well-fitted parametric data a
    parametric candidate will usually beat the empirical reference.
    """
    n = len(series)
    hist = _to_hist(series)
    counts = np.asarray(hist["counts"], dtype=float)
    edges = np.asarray(hist["edges"], dtype=float)
    bin_widths = np.diff(edges)

    loglik = float("nan")
    aic = float("inf")
    bic = float("inf")
    if n > 0 and counts.size > 0 and np.all(bin_widths > 0):
        # density per bin: count / (n * binwidth)
        densities = counts / (n * bin_widths)
        loglik = float(np.sum(counts * np.log(densities + np.finfo(float).eps)))
        k = int(counts.size)  # each bin is an effective parameter
        aic = float(2 * k - 2 * loglik)
        bic = float(k * math.log(n) - 2 * loglik)

    return DistributionFit(
        name="empirical",
        params={"n": float(n), "min": float(series.min()), "max": float(series.max())},
        aic=aic,
        bic=bic,
        ks_statistic=0.0,
        ks_p_value=0.0,
        loglik=loglik,
        skewness=float(stats.skew(series)) if n > 2 else None,
        kurtosis=float(stats.kurtosis(series)) if n > 2 else None,
        histogram=hist,
    )


__all__ = ["DistributionFit", "FitResult", "fit_best_distribution", "SUPPORTED_DISTRIBUTIONS"]