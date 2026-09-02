"""Tests for SPC calculation engine."""
from __future__ import annotations

import numpy as np
import pytest

from process_intelligence_engine.spc import (
    compute_capability,
    compute_i_mr,
    compute_xbar_r,
    compute_xbar_s,
    detect_we_violations,
)


def test_i_mr_returns_expected_keys():
    values = [10.0, 11.0, 9.0, 10.5, 11.2, 9.8, 10.1, 10.9]
    result = compute_i_mr(values)
    assert result["chart_type"] == "I-MR"
    assert "x_values" in result
    assert "control_limits" in result
    assert "mr_values" in result
    assert "subgroup_stats" in result
    assert "violations" in result
    assert "capability" in result


def test_i_mr_x_values_count():
    values = [10.0, 11.0, 9.0, 10.5, 11.2, 9.8, 10.1, 10.9]
    result = compute_i_mr(values)
    assert len(result["x_values"]) == len(values)
    # MR padded with None at index 0 so length matches x_values
    assert len(result["mr_values"]) == len(values)
    assert result["mr_values"][0] is None
    assert result["mr_values"][1] == pytest.approx(1.0)


def test_i_mr_control_limits_reasonable():
    values = [10.0, 11.0, 9.0, 10.5, 11.2, 9.8, 10.1, 10.9]
    result = compute_i_mr(values)
    limits = result["control_limits"]["x"]
    mean = float(np.mean(values))
    assert limits["ucl"] > mean
    assert limits["lcl"] < mean
    assert limits["cl"] == pytest.approx(mean, abs=0.01)


def test_xbar_r_with_subgroups():
    data = [
        [10.0, 10.2, 9.8, 10.1, 10.3],
        [9.9, 10.0, 10.1, 9.8, 10.2],
        [10.3, 10.1, 9.9, 10.2, 10.0],
        [9.8, 10.0, 10.2, 9.9, 10.1],
    ]
    result = compute_xbar_r(data, subgroup_size=5)
    assert result["chart_type"] == "X-bar/R"
    assert len(result["xbar_values"]) == len(data)
    assert len(result["r_values"]) == len(data)
    assert "subgroups" in result
    assert "control_limits" in result
    assert "violations" in result
    assert "capability" in result


def test_xbar_s_with_subgroups():
    data = [
        [10.0, 10.2, 9.8, 10.1, 10.3, 9.9],
        [9.9, 10.0, 10.1, 9.8, 10.2, 10.0],
        [10.3, 10.1, 9.9, 10.2, 10.0, 9.8],
    ]
    result = compute_xbar_s(data, subgroup_size=6)
    assert result["chart_type"] == "X-bar/S"
    assert len(result["xbar_values"]) == len(data)
    assert len(result["s_values"]) == len(data)
    assert "subgroups" in result
    assert "control_limits" in result
    assert "violations" in result
    assert "capability" in result


def test_capability_returns_stats():
    values = [10.0, 11.0, 9.0, 10.5, 11.2, 9.8, 10.1, 10.9, 10.3, 9.7]
    result = compute_capability(values, lsl=8.0, usl=12.0)
    assert "cp" in result
    assert "cpk" in result
    assert "pp" in result
    assert "ppk" in result
    assert "sigma_within" in result
    assert "sigma_overall" in result
    assert "mean" in result
    assert "n_subgroups" in result
    assert "total_observations" in result
    assert result["total_observations"] == 10
    assert result["mean"] == pytest.approx(10.25, abs=0.01)
    assert result["cp"] > 0
    assert result["cpk"] > 0


def test_capability_no_limits():
    values = [10.0, 11.0, 9.0, 10.5]
    result = compute_capability(values)
    assert result["cp"] is None
    assert result["cpk"] is None
    assert result["pp"] is None
    assert result["ppk"] is None
    assert result["sigma_within"] is not None
    assert result["sigma_overall"] is not None
    assert result["total_observations"] == 4


def test_we_violations_detects_out_of_control():
    values = [10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 25.0]
    center = 10.0
    sigma = 1.0
    violations = detect_we_violations(values, center, sigma)
    assert any(v["rule"] == "beyond_3sigma" for v in violations)
    assert any(v["point_idx"] == 7 for v in violations)


def test_we_violations_empty_for_normal_data():
    np.random.seed(42)
    values = np.random.normal(10.0, 0.5, 50).tolist()
    violations = detect_we_violations(values, center=10.0, sigma=0.5)
    assert len(violations) == 0


def test_i_mr_handles_small_dataset():
    values = [10.0, 11.0]
    result = compute_i_mr(values)
    assert result["chart_type"] == "I-MR"
    assert len(result["x_values"]) == 2
    # MR padded with None at index 0
    assert len(result["mr_values"]) == 2
    assert result["mr_values"][0] is None
    assert result["mr_values"][1] == 1.0


def test_xbar_r_invalid_subgroup_size():
    data = [[10.0, 10.2, 9.8]]
    with pytest.raises(ValueError):
        compute_xbar_r(data, subgroup_size=1)


def test_we_rule_3_detection():
    values = [0] * 10 + [3.5] * 5
    violations = detect_we_violations(values, center=0, sigma=1.0)
    rule3 = [v for v in violations if v["rule"] == "4_of_5_beyond_1sigma"]
    assert len(rule3) > 0


def test_we_rule_4_detection():
    values = [0] * 10 + [1.5] * 10
    violations = detect_we_violations(values, center=0, sigma=1.0)
    rule4 = [v for v in violations if v["rule"] == "8_consecutive_same_side"]
    assert len(rule4) > 0


def test_we_rule_5_detection():
    values = [i * 0.5 for i in range(20)]
    violations = detect_we_violations(values, center=5, sigma=1.0)
    rule5 = [v for v in violations if v["rule"] == "6_consecutive_trend"]
    assert len(rule5) > 0


def test_we_rule_6_detection():
    values = [0.5 * ((-1) ** i) for i in range(20)]
    violations = detect_we_violations(values, center=0, sigma=1.0)
    rule6 = [v for v in violations if v["rule"] == "15_consecutive_within_1sigma"]
    assert len(rule6) > 0


def test_we_rule_7_detection():
    values = [1.5 if i % 2 == 0 else -1.5 for i in range(20)]
    violations = detect_we_violations(values, center=0, sigma=1.0)
    rule7 = [v for v in violations if v["rule"] == "14_consecutive_alternating"]
    assert len(rule7) > 0
