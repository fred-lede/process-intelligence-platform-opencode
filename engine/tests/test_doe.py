"""Tests for DOE design generators."""
import pytest

from process_intelligence_engine.modeling.doe import generate_design


def test_full_factorial_2_factors_2_levels():
    factors = [
        {"name": "temperature", "low": 150.0, "high": 250.0},
        {"name": "pressure", "low": 10.0, "high": 50.0},
    ]
    result = generate_design(factors, "full_factorial", {"levels": 2})
    assert result["design_type"] == "full_factorial"
    assert result["n_runs"] == 4
    assert len(result["runs"]) == 4
    assert len(result["coded_runs"]) == 4
    # Coded: each factor at -1 and +1
    a_coded = sorted([r["temperature"] for r in result["coded_runs"]])
    assert a_coded == [-1, -1, 1, 1]
    # Actual: low/high values
    a_actual = sorted([r["temperature"] for r in result["runs"]])
    assert a_actual == [150.0, 150.0, 250.0, 250.0]


def test_full_factorial_3_levels():
    factors = [{"name": "A", "low": -1.0, "high": 1.0}]
    result = generate_design(factors, "full_factorial", {"levels": 3})
    assert result["n_runs"] == 3
    coded = sorted([r["A"] for r in result["coded_runs"]])
    assert coded == [-1, 0, 1]
    actual = sorted([r["A"] for r in result["runs"]])
    assert actual == [-1.0, 0.0, 1.0]


def test_full_factorial_4_factors():
    factors = [{"name": f"f{i}", "low": 0.0, "high": 1.0} for i in range(4)]
    result = generate_design(factors, "full_factorial", {"levels": 2})
    assert result["n_runs"] == 16  # 2^4


def test_fractional_factorial_3_factors():
    factors = [
        {"name": "A", "low": 0.0, "high": 1.0},
        {"name": "B", "low": 0.0, "high": 1.0},
        {"name": "C", "low": 0.0, "high": 1.0},
    ]
    result = generate_design(factors, "fractional_factorial", {"levels": 2})
    assert result["design_type"] == "fractional_factorial"
    assert result["n_runs"] == 4  # 2^(3-1) = half fraction
    assert len(result["runs"]) == 4
    assert len(result["coded_runs"]) == 4


def test_unknown_design_type_raises():
    with pytest.raises(ValueError, match="Unknown design_type"):
        generate_design([{"name": "A", "low": 0, "high": 1}], "nonexistent")


def test_missing_factors_raises():
    with pytest.raises((ValueError, TypeError)):
        generate_design([], "full_factorial")


def test_ccd():
    factors = [
        {"name": "A", "low": -1.0, "high": 1.0},
        {"name": "B", "low": -1.0, "high": 1.0},
    ]
    result = generate_design(factors, "ccd", {"alpha": 1.414, "center_points": 3})
    assert result["design_type"] == "ccd"
    assert result["n_runs"] == 2**2 + 2*2 + 3  # 11
    assert len(result["runs"]) == 11
    axial_coded = [r for r in result["coded_runs"] if abs(r["A"]) == 1.414 or abs(r["B"]) == 1.414]
    assert len(axial_coded) == 4


def test_ccd_3_factors():
    factors = [{"name": f"f{i}", "low": 0.0, "high": 10.0} for i in range(3)]
    result = generate_design(factors, "ccd", {"alpha": 2.0, "center_points": 2})
    assert result["n_runs"] == 2**3 + 2*3 + 2  # 16


def test_box_behnken_3_factors():
    factors = [
        {"name": "A", "low": -1.0, "high": 1.0},
        {"name": "B", "low": -1.0, "high": 1.0},
        {"name": "C", "low": -1.0, "high": 1.0},
    ]
    result = generate_design(factors, "box_behnken", {"center_points": 3})
    assert result["design_type"] == "box_behnken"
    assert result["n_runs"] == 15
    non_center = [r for r in result["coded_runs"] if not all(v == 0 for v in r.values())]
    for r in non_center:
        zeros = sum(1 for v in r.values() if v == 0)
        assert zeros == 1


def test_box_behnken_4_factors():
    factors = [{"name": f"f{i}", "low": 0.0, "high": 1.0} for i in range(4)]
    result = generate_design(factors, "box_behnken", {"center_points": 3})
    assert result["n_runs"] == 27
