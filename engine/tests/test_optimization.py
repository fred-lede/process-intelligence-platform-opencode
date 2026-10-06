"""Tests for OptQuest-style parameter optimization."""
import numpy as np
import pandas as pd
import pytest

from process_intelligence_engine.modeling.fitters import ModelFit
from process_intelligence_engine.optimization import run_optquest, _lhs_samples


def _linear_fit():
    return ModelFit(model_type="doe_linear", target="y", inputs=["x1", "x2"],
                    coefficients={"_intercept": 0.0, "x1": 2.0, "x2": -1.0})


def _df():
    rng = np.random.default_rng(1)
    return pd.DataFrame({"x1": rng.uniform(0, 10, 100),
                         "x2": rng.uniform(0, 10, 100),
                         "y": 0.0})


def test_lhs_covers_each_stratum():
    samples = _lhs_samples({"x1": (0.0, 10.0), "x2": (0.0, 10.0)}, n=50, seed=42)
    assert set(samples) == {"x1", "x2"}
    for col, vals in samples.items():
        assert len(vals) == 50
        # 每維 50 分層各一樣本：排序後無重複層
        s = np.sort(vals)
        assert s[0] >= 0.0 and s[-1] <= 10.0
        gaps = np.diff(s)
        assert np.all(gaps > 0)


def test_lhs_single_input_works():
    samples = _lhs_samples({"x1": (0.0, 10.0)}, n=20, seed=42)
    assert len(samples["x1"]) == 20


def test_maximize_yield_finds_high_x1():
    # y = 2*x1 - x2；yield 目標區間 [15, 25] → best 應靠近 2*x1-x2 ∈ [15,25]
    fit = _linear_fit()
    result = run_optquest(fit, _df(), objective="maximize_yield",
                          lsl=15.0, usl=25.0, n_candidates=80,
                          n_eval_samples=200, seed=42)
    assert result["best_point"]["x1"] > 7.0
    assert 0.0 <= result["best"]["yield"] <= 1.0
    assert result["best"]["dpmo"] == pytest.approx((1 - result["best"]["yield"]) * 1e6)
    assert len(result["trajectory"]) == 80
    # 軌跡單調不變差
    bests = [t["best_so_far"] for t in result["trajectory"]]
    assert all(bests[i] >= bests[i - 1] - 1e-9 for i in range(1, len(bests)))


def test_minimize_dpmo_same_direction():
    fit = _linear_fit()
    r = run_optquest(fit, _df(), objective="minimize_dpmo",
                     lsl=15.0, usl=25.0, n_candidates=50,
                     n_eval_samples=200, seed=42)
    assert r["best"]["dpmo"] <= 1e6
    assert r["objective"] == "minimize_dpmo"


def test_hit_target_with_cpk_constraint():
    fit = _linear_fit()
    result = run_optquest(fit, _df(), objective="hit_target",
                          lsl=None, usl=None, target_value=10.0,
                          cpk_min=1.0, n_candidates=60,
                          n_eval_samples=200, seed=42)
    assert "best_point" in result and "feasible" in result
    assert result["best"]["predicted_mean"] == pytest.approx(
        2.0 * result["best_point"]["x1"] - 1.0 * result["best_point"]["x2"], abs=2.0)


def test_missing_spec_raises_for_yield_objectives():
    fit = _linear_fit()
    with pytest.raises(ValueError, match="LSL/USL"):
        run_optquest(fit, _df(), objective="maximize_yield",
                     lsl=None, usl=None, n_candidates=10, seed=42)


def test_inverted_bounds_raise():
    fit = _linear_fit()
    with pytest.raises(ValueError, match="bounds"):
        run_optquest(fit, _df(), objective="hit_target", lsl=None, usl=None,
                     target_value=5.0,
                     bounds={"x1": (10.0, 0.0), "x2": (0.0, 10.0)},
                     n_candidates=10, seed=42)


def test_constant_column_fixed():
    fit = _linear_fit()
    result = run_optquest(fit, _df(), objective="hit_target", lsl=None, usl=None,
                          target_value=5.0,
                          bounds={"x1": (0.0, 10.0), "x2": (3.0, 3.0)},
                          n_candidates=20, n_eval_samples=100, seed=42)
    assert result["best_point"]["x2"] == pytest.approx(3.0)


def test_target_out_of_range_feasible_false():
    # y = 2*x1 - x2 在 x1,x2 ∈ [0,10] 的最大值 20；target 1000 不可達
    fit = _linear_fit()
    result = run_optquest(fit, _df(), objective="hit_target", lsl=None, usl=None,
                          target_value=1000.0, n_candidates=30,
                          n_eval_samples=100, seed=42)
    assert result["feasible"] is False
    assert "best_point" in result  # 仍回最接近點


def test_seed_reproducibility():
    fit = _linear_fit()
    r1 = run_optquest(fit, _df(), objective="maximize_yield", lsl=15.0, usl=25.0,
                      n_candidates=30, n_eval_samples=100, seed=7)
    r2 = run_optquest(fit, _df(), objective="maximize_yield", lsl=15.0, usl=25.0,
                      n_candidates=30, n_eval_samples=100, seed=7)
    assert r1["best_point"] == r2["best_point"]
    assert r1["best"]["yield"] == r2["best"]["yield"]
