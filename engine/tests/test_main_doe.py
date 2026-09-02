"""Tests for DOE IPC handlers."""
import pytest

from process_intelligence_engine.main import handle_request


def test_doe_generate_full_factorial():
    factors = [{"name": "A", "low": 0.0, "high": 1.0}, {"name": "B", "low": 0.0, "high": 1.0}]
    result = handle_request("modeling/doe/generate", {
        "factors": factors,
        "design_type": "full_factorial",
        "params": {"levels": 2},
    })
    assert result["design_type"] == "full_factorial"
    assert result["n_runs"] == 4
    assert len(result["runs"]) == 4


def test_doe_generate_ccd():
    factors = [{"name": "X", "low": -1.0, "high": 1.0}]
    result = handle_request("modeling/doe/generate", {
        "factors": factors,
        "design_type": "ccd",
        "params": {"alpha": 1.5, "center_points": 2},
    })
    assert result["design_type"] == "ccd"
    assert result["n_runs"] == 2 + 2 + 2  # factorial (2^1) + axial (2*1) + center


def test_doe_generate_unknown_type_raises():
    with pytest.raises(ValueError):
        handle_request("modeling/doe/generate", {
            "factors": [{"name": "A", "low": 0, "high": 1}],
            "design_type": "nonexistent",
        })


def test_doe_generate_empty_factors_raises():
    with pytest.raises((ValueError, TypeError)):
        handle_request("modeling/doe/generate", {
            "factors": [],
            "design_type": "full_factorial",
        })
