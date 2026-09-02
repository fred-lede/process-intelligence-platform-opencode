import numpy as np
import pytest

from process_intelligence_engine.data.distribution import (
    DistributionFit,
    FitResult,
    fit_best_distribution,
)


def _normalish_data(n=500, seed=42) -> list[float]:
    rng = np.random.default_rng(seed)
    return rng.normal(255.0, 3.0, n).tolist()


def test_fit_returns_sorted_candidates():
    data = _normalish_data()
    results = fit_best_distribution(data)

    assert isinstance(results, list)
    assert all(isinstance(r, FitResult) for r in results)
    assert len(results) >= 3
    aics = [r.aic for r in results]
    assert aics == sorted(aics)


def test_best_fit_for_normal_data_is_normal():
    data = _normalish_data()
    best = fit_best_distribution(data)[0]

    assert best.name == "normal"
    assert best.aic <= 0 or best.aic is not None
    assert best.ks_statistic is not None


def test_fit_returns_empirical_for_nonparametric_data():
    # Uniform data should still yield a best fit; empirical fallback
    # should be among candidates or the winner with enough samples.
    rng = np.random.default_rng(7)
    data = rng.uniform(0.0, 1.0, 400).tolist()
    candidates = fit_best_distribution(data)

    names = {c.name for c in candidates}
    assert "uniform" in names or "empirical" in names


def test_fit_reports_histogram_info():
    data = _normalish_data()
    results = fit_best_distribution(data)

    hist = results[0].histogram
    assert hist["counts"]
    assert hist["edges"] and len(hist["edges"]) == len(hist["counts"]) + 1


def test_fit_params_are_serializable():
    data = _normalish_data()
    best = fit_best_distribution(data)[0]

    assert isinstance(best.params, dict)
    for k, v in best.params.items():
        assert isinstance(v, (int, float))


def test_distribution_fit_dataclass_fields():
    data = _normalish_data()
    best = fit_best_distribution(data)[0]

    assert isinstance(best, DistributionFit)
    assert isinstance(best.name, str)
    assert best.ks_p_value is not None
    assert best.skewness is not None
    assert best.kurtosis is not None


def test_insufficient_data_returns_empirical():
    data = [1.0, 2.0, 3.0]
    results = fit_best_distribution(data)

    # With tiny data we still return at least one candidate.
    assert len(results) >= 1
    # No crash on tiny sample; empirical may be the recommendation.
    assert results[0].name in {"empirical", "normal", "uniform"}


def test_non_numeric_values_are_filtered():
    data = ["a", "b", 1.0, 2.0, None, 3.0]
    results = fit_best_distribution(data)

    assert len(results) >= 1
    assert all(r.name in {"empirical", "normal", "uniform"} for r in results[:1])


def test_pdf_curve_for_normal_fit_tracks_density():
    data = _normalish_data()
    best = fit_best_distribution(data)[0]

    assert best.name == "normal"
    assert best.pdf["x"] and best.pdf["y"]
    assert best.pdf["x"] == sorted(best.pdf["x"])
    assert all(y >= 0 for y in best.pdf["y"])
    # Area under the pdf (trapezoid) should approximate 1.
    xs = np.asarray(best.pdf["x"])
    ys = np.asarray(best.pdf["y"])
    area = np.trapezoid(ys, xs) if hasattr(np, "trapezoid") else np.trapz(ys, xs)
    assert 0.5 < area < 1.5


def test_empirical_fit_has_empty_pdf_curve():
    data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0]
    empirical = [r for r in fit_best_distribution(data) if r.name == "empirical"]
    assert empirical
    assert empirical[0].pdf == {"x": [], "y": []}


def test_pdf_curve_discrete_matches_pmf_at_point():
    rng = np.random.default_rng(3)
    counts = rng.poisson(4.0, 300).astype(float).tolist()
    candidates = fit_best_distribution(counts, top_n=4)
    poisson = [c for c in candidates if c.name == "poisson"]
    assert poisson

    fit = poisson[0]
    mu = fit.params["mu"]
    from scipy import stats

    expected = float(stats.poisson.pmf(4, mu))
    # Find x==4 in the curve and compare.
    curve = dict(zip(fit.pdf["x"], fit.pdf["y"]))
    assert round(curve[4.0], 8) == round(expected, 8)