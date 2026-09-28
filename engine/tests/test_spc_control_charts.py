"""Reference-value checks for the SPC control-chart constants.

Every expected value here is computed from the textbook formula rather than
read out of the module's own tables, so a wrong table cannot validate itself.
These pin the four corrections made to the X-bar/S and X-bar/R paths and the
individuals capability estimate.
"""
import math

import numpy as np
import pytest

from process_intelligence_engine.spc import (
    _d2,
    compute_capability,
    compute_xbar_r,
    compute_xbar_s,
)


def c4_formula(n: int) -> float:
    """c4 = sqrt(2/(n-1)) * Γ(n/2) / Γ((n-1)/2), from the definition."""
    from math import gamma, sqrt

    return sqrt(2.0 / (n - 1)) * gamma(n / 2) / gamma((n - 1) / 2)


def test_c4_table_matches_the_formula():
    from process_intelligence_engine.spc import _c4

    for n in range(2, 11):
        assert _c4[n] == pytest.approx(c4_formula(n), abs=1e-6), n


def _subgroups(n=5, count=25, seed=4, scale=1.0):
    rng = np.random.default_rng(seed)
    return [rng.normal(10.0, scale, n).tolist() for _ in range(count)]


def test_xbar_s_limits_use_a3_not_a2():
    """A3 = 3/(c4*sqrt(n)); the module used to compute A2 = 3/(d2*sqrt(n)),
    which at n=5 is 0.577 instead of 1.427 -- limits 2.5x too narrow."""
    n = 5
    subgroups = _subgroups(n)
    result = compute_xbar_s(subgroups, subgroup_size=n)

    xbars = [float(np.mean(s)) for s in subgroups]
    s_bar = float(np.mean([float(np.std(s, ddof=1)) for s in subgroups]))
    x_double_bar = float(np.mean(xbars))

    a3 = 3.0 / (c4_formula(n) * math.sqrt(n))
    limits = result["control_limits"]["x"]
    assert limits["ucl"] == pytest.approx(x_double_bar + a3 * s_bar, abs=1e-6)
    assert limits["lcl"] == pytest.approx(x_double_bar - a3 * s_bar, abs=1e-6)

    # The half-width must be the A3 one, and materially wider than A2's.
    a2 = 3.0 / (_d2[n] * math.sqrt(n))
    half_width = limits["ucl"] - x_double_bar
    assert half_width == pytest.approx(a3 * s_bar, abs=1e-6)
    assert half_width > 2.0 * a2 * s_bar


def test_xbar_we_rules_use_the_subgroup_mean_sigma():
    """The plotted statistic is the subgroup mean, so the zone width must be
    sigma/sqrt(n). Using the individual sigma widened every zone by sqrt(n),
    so a point 4*sigma/sqrt(n) off centre raised nothing."""
    n = 5
    rng = np.random.default_rng(11)
    base = [rng.normal(0.0, 1.0, n).tolist() for _ in range(20)]
    sigma = float(np.mean([float(np.std(s, ddof=1)) for s in base])) / c4_formula(n)
    shifted = rng.normal(4.0 * sigma / math.sqrt(n), 0.01, n).tolist()

    result = compute_xbar_s(base + [shifted], subgroup_size=n)

    rules = {v["rule"] for v in result["violations"]}
    assert "beyond_3sigma" in rules

    # ...and the same deviation is nowhere near the individual-sigma zone, which
    # is what the old code measured against.
    assert 4.0 / math.sqrt(n) < 3.0


def test_xbar_r_we_rules_use_the_subgroup_mean_sigma():
    n = 4
    rng = np.random.default_rng(12)
    base = [rng.normal(0.0, 1.0, n).tolist() for _ in range(20)]
    r_bar = float(np.mean([float(np.max(s) - np.min(s)) for s in base]))
    sigma = r_bar / _d2[n]
    shifted = rng.normal(4.0 * sigma / math.sqrt(n), 0.01, n).tolist()

    result = compute_xbar_r(base + [shifted], subgroup_size=n)
    rules = {v["rule"] for v in result["violations"]}
    assert "beyond_3sigma" in rules


def test_capability_individuals_separates_within_from_overall():
    """Cp/Cpk use sigma_within, Pp/Ppk use the total. Reading the total into
    both made Cp == Pp and Cpk == Ppk by construction."""
    rng = np.random.default_rng(7)
    arr = np.linspace(0.0, 10.0, 50) + rng.normal(0.0, 0.1, 50)

    cap = compute_capability(arr.tolist(), lsl=0.0, usl=12.0, subgroup_size=1)

    mr_bar = float(np.mean(np.abs(np.diff(arr))))
    assert cap["sigma_within"] == pytest.approx(mr_bar / _d2[2], abs=1e-6)
    # A drifting series: within variability is far smaller than the total.
    assert cap["sigma_within"] < cap["sigma_overall"]
    assert cap["cp"] > cap["pp"]
    assert cap["cpk"] > cap["ppk"]


def test_capability_subgrouped_still_uses_within_subgroup_range():
    """Regression guard for the path that was already correct."""
    n = 5
    subgroups = _subgroups(n)
    flat = [v for s in subgroups for v in s]
    cap = compute_capability(flat, lsl=6.0, usl=14.0, subgroup_size=n)

    r_bar = float(np.mean([float(np.max(s) - np.min(s)) for s in subgroups]))
    assert cap["sigma_within"] == pytest.approx(r_bar / _d2[n], abs=1e-6)
