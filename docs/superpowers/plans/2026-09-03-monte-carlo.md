# Phase 9 — 蒙地卡羅異常風險模擬 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Monte Carlo simulation engine that combines input distributions, anomaly scenarios, and trained DOE models to estimate NG probability and output distribution.

**Architecture:** Python engine samples from fitted distributions, applies anomaly scenarios probabilistically, predicts output using DOE model coefficients, and computes statistics. Frontend renders Plotly charts.

**Tech Stack:** Python 3.11 + NumPy + SciPy + Pandas, Tauri IPC, React 18 + Ant Design 5 + Plotly, TypeScript, pytest.

---

## Task 1: Monte Carlo 計算引擎核心

**Files:**
- Create: `engine/src/process_intelligence_engine/monte_carlo.py`
- Test: `engine/tests/test_monte_carlo.py`

- [ ] **Step 1: Write the failing test**

Create `engine/tests/test_monte_carlo.py`:

```python
"""Tests for Monte Carlo simulation engine."""
import numpy as np
import pytest

from process_intelligence_engine.monte_carlo import (
    run_monte_carlo,
    sample_from_distribution,
    apply_anomalies,
    predict_output,
)


def _make_simple_dataset(rng):
    """Create a simple dataset for testing."""
    import pandas as pd
    n = 100
    x1 = rng.normal(100, 5, n)
    x2 = rng.normal(50, 3, n)
    y = 10 + 2 * x1 - 1.5 * x2 + rng.normal(0, 1, n)
    return pd.DataFrame({"x1": x1, "x2": x2, "y": y})


def test_sample_from_normal():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    samples = sample_from_distribution(values, dist_name="normal", n=100, seed=42)
    assert len(samples) == 100
    assert all(isinstance(s, float) for s in samples)


def test_sample_from_histogram():
    values = list(range(100))
    samples = sample_from_distribution(values, dist_name="histogram", n=50, seed=42)
    assert len(samples) == 50


def test_predict_linear():
    coeffs = {"_intercept": 10.0, "x1": 2.0, "x2": -1.5}
    inputs = {"x1": 100.0, "x2": 50.0}
    result = predict_output("doe_linear", coeffs, inputs)
    expected = 10.0 + 2.0 * 100.0 - 1.5 * 50.0
    assert abs(result - expected) < 0.001


def test_predict_quadratic():
    coeffs = {
        "_intercept": 10.0,
        "x1": 2.0,
        "x2": -1.5,
        "x1_x1": 0.1,
        "x2_x2": -0.05,
        "x1_x2": 0.3,
    }
    inputs = {"x1": 100.0, "x2": 50.0}
    result = predict_output("doe_quadratic", coeffs, inputs)
    expected = 10.0 + 2.0 * 100.0 - 1.5 * 50.0 + 0.1 * 100.0**2 + (-0.05) * 50.0**2 + 0.3 * 100.0 * 50.0
    assert abs(result - expected) < 0.001


def test_apply_anomalies_no_anomaly():
    values = [100.0, 101.0, 99.0]
    anomalies = []
    rng = np.random.default_rng(42)
    result = apply_anomalies(values, anomalies, rng)
    assert result == values


def test_apply_anomalies_with_anomaly():
    # Anomaly that always occurs (probability=1.0) and adds +10
    anomalies = [{"target_input": "x1", "direction": "above", "magnitude": 10.0, "occurrence_probability": 1.0}]
    values = [100.0, 100.0, 100.0]
    rng = np.random.default_rng(42)
    result = apply_anomalies(values, anomalies, rng)
    # All values should have +10 added to x1
    assert all(v == 110.0 for v in result)


def test_apply_anomalies_probabilistic():
    # Anomaly with probability 0.0 (never occurs)
    anomalies = [{"target_input": "x1", "direction": "above", "magnitude": 10.0, "occurrence_probability": 0.0}]
    values = [100.0, 100.0, 100.0]
    rng = np.random.default_rng(42)
    result = apply_anomalies(values, anomalies, rng)
    assert all(v == 100.0 for v in result)


def test_run_monte_carlo_basic():
    """Test a full Monte Carlo simulation with simple data."""
    import pandas as pd
    rng = np.random.default_rng(42)
    df = _make_simple_dataset(rng)

    model_coeffs = {"_intercept": 10.0, "x1": 2.0, "x2": -1.5}
    model_type = "doe_linear"
    inputs = ["x1", "x2"]
    output_col = "y"
    lsl = 50.0
    usl = 200.0

    result = run_monte_carlo(
        df=df,
        model_type=model_type,
        coefficients=model_coeffs,
        input_columns=inputs,
        output_column=output_col,
        n_simulations=1000,
        seed=42,
        enable_anomalies=False,
        lsl=lsl,
        usl=usl,
    )

    assert result["n_simulations"] == 1000
    assert result["ng_count"] >= 0
    assert 0.0 <= result["ng_probability"] <= 1.0
    assert result["output_mean"] is not None
    assert result["percentiles"] is not None
    assert "histogram" in result
    assert "cdf_data" in result


def test_run_monte_carlo_with_anomalies():
    """Test with anomaly scenarios."""
    import pandas as pd
    rng = np.random.default_rng(42)
    df = _make_simple_dataset(rng)

    model_coeffs = {"_intercept": 10.0, "x1": 2.0, "x2": -1.5}
    anomalies = [
        {
            "anomaly_id": "an-1",
            "target_input": "x1",
            "direction": "above",
            "occurrence_probability": 0.1,
            "magnitude_distribution": {"type": "constant", "value": 20.0},
        }
    ]

    result = run_monte_carlo(
        df=df,
        model_type="doe_linear",
        coefficients=model_coeffs,
        input_columns=inputs := ["x1", "x2"],
        output_column="y",
        n_simulations=500,
        seed=42,
        enable_anomalies=True,
        anomalies=anomalies,
        lsl=50.0,
        usl=200.0,
    )

    assert result["n_simulations"] == 500
    assert result["ng_count"] >= 0
    # With anomalies, we should see some NG cases
    assert result["ng_probability"] >= 0


def test_run_monte_carlo_small_n():
    """Test with small simulation count."""
    import pandas as pd
    rng = np.random.default_rng(42)
    df = _make_simple_dataset(rng)

    result = run_monte_carlo(
        df=df,
        model_type="doe_linear",
        coefficients={"_intercept": 10.0, "x1": 2.0, "x2": -1.5},
        input_columns=["x1", "x2"],
        output_column="y",
        n_simulations=10,
        seed=42,
        enable_anomalies=False,
        lsl=None,
        usl=None,
    )
    assert result["n_simulations"] == 10


def test_run_monte_carlo_quadratic():
    """Test quadratic model prediction."""
    import pandas as pd
    rng = np.random.default_rng(42)
    df = _make_simple_dataset(rng)

    coeffs = {
        "_intercept": 10.0,
        "x1": 2.0,
        "x2": -1.5,
        "x1_x1": 0.01,
        "x2_x2": -0.005,
        "x1_x2": 0.02,
    }

    result = run_monte_carlo(
        df=df,
        model_type="doe_quadratic",
        coefficients=coeffs,
        input_columns=["x1", "x2"],
        output_column="y",
        n_simulations=100,
        seed=42,
        enable_anomalies=False,
        lsl=50.0,
        usl=200.0,
    )
    assert result["output_mean"] is not None
    assert len(result["output_values"]) == 100


def test_run_monte_carlo_no_bounds():
    """Test without LSL/USL — should have 0 NG."""
    import pandas as pd
    rng = np.random.default_rng(42)
    df = _make_simple_dataset(rng)

    result = run_monte_carlo(
        df=df,
        model_type="doe_linear",
        coefficients={"_intercept": 10.0, "x1": 2.0, "x2": -1.5},
        input_columns=["x1", "x2"],
        output_column="y",
        n_simulations=100,
        seed=42,
        enable_anomalies=False,
        lsl=None,
        usl=None,
    )
    assert result["ng_count"] == 0
    assert result["ng_probability"] == 0.0


def test_sample_distribution_unknown_type():
    """Test sampling with unknown distribution type uses histogram fallback."""
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    samples = sample_from_distribution(values, dist_name="unknown_type", n=10, seed=42)
    assert len(samples) == 10


def test_predict_output_missing_coefficient():
    """Test prediction with missing coefficient uses 0."""
    coeffs = {"_intercept": 10.0}
    inputs = {"x1": 5.0}
    result = predict_output("doe_linear", coeffs, inputs)
    assert result == 10.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && .venv/bin/pytest tests/test_monte_carlo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'process_intelligence_engine.monte_carlo'`

- [ ] **Step 3: Write minimal implementation**

Create `engine/src/process_intelligence_engine/monte_carlo.py`:

```python
"""Monte Carlo simulation engine for process risk analysis."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class _AnomalyEvent:
    """A single anomaly that may occur during simulation."""
    target_input: str
    direction: str  # "above" or "below"
    magnitude: float
    occurrence_probability: float


def sample_from_distribution(
    values: list[float],
    dist_name: str = "normal",
    n: int = 1000,
    seed: int | None = None,
) -> list[float]:
    """Sample values from a fitted distribution or histogram."""
    rng = np.random.default_rng(seed)
    clean = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not clean:
        return [0.0] * n

    if dist_name in ("normal", "norm"):
        mean = sum(clean) / len(clean)
        std = (sum((x - mean) ** 2 for x in clean) / max(len(clean) - 1, 1)) ** 0.5
        if std <= 0:
            std = 1e-10
        return rng.normal(mean, std, n).tolist()
    elif dist_name in ("gamma",):
        mean = sum(clean) / len(clean)
        std = (sum((x - mean) ** 2 for x in clean) / max(len(clean) - 1, 1)) ** 0.5
        if std <= 0 or mean <= 0:
            return [mean] * n
        shape = (mean / std) ** 2
        scale = std ** 2 / mean
        return rng.gamma(shape, scale, n).tolist()
    elif dist_name in ("lognormal",):
        log_vals = [math.log(max(v, 1e-10)) for v in clean]
        mean_log = sum(log_vals) / len(log_vals)
        std_log = (sum((v - mean_log) ** 2 for v in log_vals) / max(len(log_vals) - 1, 1)) ** 0.5
        return rng.lognormal(mean_log, std_log, n).tolist()
    else:
        # Histogram fallback: random sampling from empirical distribution
        return rng.choice(clean, size=n).tolist()


def apply_anomalies(
    values: list[float],
    anomalies: list[dict],
    rng: np.random.Generator,
) -> list[float]:
    """Apply anomaly events to input values based on occurrence probability."""
    result = list(values)
    for anom in anomalies:
        target = anom.get("target_input", "")
        if target not in result:
            continue
        prob = anom.get("occurrence_probability", 0.0)
        direction = anom.get("direction", "above")
        mag_dist = anom.get("magnitude_distribution") or {}

        # Determine magnitude
        if mag_dist.get("type") == "constant":
            magnitude = mag_dist.get("value", 0.0)
        elif mag_dist.get("type") == "normal":
            loc = mag_dist.get("loc", 0.0)
            scale = max(mag_dist.get("scale", 1.0), 1e-10)
            magnitude = rng.normal(loc, scale)
        else:
            # Default: use a fixed value from magnitude_distribution
            magnitude = mag_dist.get("mean", mag_dist.get("value", 0.0))

        # Apply direction
        if direction == "below":
            magnitude = -magnitude

        # Decide if anomaly occurs
        if rng.random() < prob:
            idx = result.index(target) if target in result else 0
            if 0 <= idx < len(result):
                result[idx] = result[idx] + magnitude

    return result


def predict_output(
    model_type: str,
    coefficients: dict[str, float],
    inputs: dict[str, float],
) -> float:
    """Predict output using DOE model coefficients."""
    intercept = coefficients.get("_intercept", 0.0)
    result = intercept

    # Main effects
    for key, val in inputs.items():
        coef = coefficients.get(key, 0.0)
        result += coef * val

    # Interaction effects (x1_x2 format)
    input_keys = list(inputs.keys())
    for i in range(len(input_keys)):
        for j in range(i + 1, len(input_keys)):
            pair_key = f"{input_keys[i]}_x_{input_keys[j]}"
            coef = coefficients.get(pair_key, 0.0)
            result += coef * inputs[input_keys[i]] * inputs[input_keys[j]]
            # Also try x1_x2 format
            pair_key2 = f"{input_keys[i]}x{input_keys[j]}"
            coef2 = coefficients.get(pair_key2, 0.0)
            result += coef2 * inputs[input_keys[i]] * inputs[input_keys[j]]

    # Quadratic effects (x1_x1 format)
    for key in input_keys:
        sq_key = f"{key}_x_{key}"
        coef = coefficients.get(sq_key, 0.0)
        result += coef * inputs[key] ** 2
        # Also try x1x1 format
        sq_key2 = f"{key}{key}"
        coef2 = coefficients.get(sq_key2, 0.0)
        result += coef2 * inputs[key] ** 2

    return float(result)


def run_monte_carlo(
    df: pd.DataFrame,
    model_type: str,
    coefficients: dict[str, float],
    input_columns: list[str],
    output_column: str,
    n_simulations: int = 10000,
    seed: int = 42,
    enable_anomalies: bool = False,
    anomalies: list[dict] | None = None,
    lsl: float | None = None,
    usl: float | None = None,
) -> dict:
    """Run Monte Carlo simulation and return results."""
    rng = np.random.default_rng(seed)
    anomalies = anomalies or []

    # Sample inputs
    sampled_inputs: dict[str, list[float]] = {}
    for col in input_columns:
        if col not in df.columns:
            continue
        values = df[col].dropna().astype(float).tolist()
        if not values:
            continue
        sampled_inputs[col] = sample_from_distribution(values, n=n_simulations, seed=int(rng.integers(0, 2**31)))

    # Ensure all input columns have same length
    if sampled_inputs:
        n = len(next(iter(sampled_inputs.values())))
        for col in input_columns:
            if col in sampled_inputs and len(sampled_inputs[col]) < n:
                sampled_inputs[col] = sampled_inputs[col] + [0.0] * (n - len(sampled_inputs[col]))

    # Run simulations
    output_values: list[float] = []
    ng_count = 0
    anomaly_ng_counts: dict[str, int] = {a.get("anomaly_id", "unknown"): 0 for a in anomalies}
    multi_anomaly_ng = 0
    violation_records: list[dict] = []

    for i in range(n):
        inputs = {}
        for col in input_columns:
            if col in sampled_inputs:
                inputs[col] = sampled_inputs[col][i] if i < len(sampled_inputs[col]) else 0.0
            else:
                inputs[col] = 0.0

        # Apply anomalies
        current_anomalies = []
        if enable_anomalies:
            applied_values = apply_anomalies(
                [inputs.get(col, 0.0) for col in input_columns],
                anomalies,
                rng,
            )
            for j, col in enumerate(input_columns):
                inputs[col] = applied_values[j] if j < len(applied_values) else inputs.get(col, 0.0)

            # Track which anomalies occurred
            for anom in anomalies:
                if rng.random() < anom.get("occurrence_probability", 0.0):
                    current_anomalies.append(anom.get("anomaly_id", "unknown"))

        # Predict output
        output = predict_output(model_type, coefficients, inputs)
        output_values.append(output)

        # Check NG
        is_ng = False
        if lsl is not None and output < lsl:
            is_ng = True
        if usl is not None and output > usl:
            is_ng = True

        if is_ng:
            ng_count += 1
            for aid in current_anomalies:
                if aid in anomaly_ng_counts:
                    anomaly_ng_counts[aid] += 1
            if len(current_anomalies) >= 2:
                multi_anomaly_ng += 1

        violation_records.append({
            "simulation_idx": i,
            "output": output,
            "is_ng": is_ng,
            "anomalies": current_anomalies,
        })

    # Compute statistics
    arr = np.array(output_values)
    mean_val = float(np.mean(arr))
    std_val = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
    median_val = float(np.median(arr))

    percentiles = {}
    if len(arr) > 0:
        percentiles = {
            "p1": float(np.percentile(arr, 1)),
            "p5": float(np.percentile(arr, 5)),
            "p50": float(np.percentile(arr, 50)),
            "p95": float(np.percentile(arr, 95)),
            "p99": float(np.percentile(arr, 99)),
        }

    ng_probability = ng_count / n_simulations if n_simulations > 0 else 0.0

    # Build histogram
    hist_counts, hist_edges = np.histogram(arr, bins=30)
    histogram = {
        "bins": [float(e) for e in hist_edges],
        "counts": [int(c) for c in hist_counts],
    }

    # Build CDF data
    sorted_vals = np.sort(arr)
    cdf_x = [float(v) for v in sorted_vals]
    cdf_y = [float((i + 1) / len(sorted_vals)) for i in range(len(sorted_vals))]

    # Build boxplot data
    normal_outputs = [v for v, rec in zip(output_values, violation_records) if not rec["is_ng"]]
    ng_outputs = [v for v, rec in zip(output_values, violation_records) if rec["is_ng"]]
    single_anomaly_ng = [
        v for v, rec in zip(output_values, violation_records)
        if rec["is_ng"] and len(rec["anomalies"]) == 1
    ]
    multi_anomaly_outputs = [
        v for v, rec in zip(output_values, violation_records)
        if rec["is_ng"] and len(rec["anomalies"]) >= 2
    ]

    boxplot_data = {
        "normal": [float(v) for v in normal_outputs],
        "single_anomaly": [float(v) for v in single_anomaly_ng],
        "multi_anomaly": [float(v) for v in multi_anomaly_outputs],
    }

    # Build anomaly rankings
    anomaly_rankings = []
    for anom in anomalies:
        aid = anom.get("anomaly_id", "unknown")
        contrib = anomaly_ng_counts.get(aid, 0)
        anomaly_rankings.append({
            "anomaly_id": aid,
            "name": anom.get("name", aid),
            "ng_contribution": contrib,
            "probability": anom.get("occurrence_probability", 0.0),
        })
    anomaly_rankings.sort(key=lambda x: x["ng_contribution"], reverse=True)

    return {
        "n_simulations": n_simulations,
        "seed": seed,
        "ng_count": ng_count,
        "ng_probability": ng_probability,
        "output_mean": mean_val,
        "output_std": std_val,
        "output_median": median_val,
        "percentiles": percentiles,
        "histogram": histogram,
        "cdf_data": {"x": cdf_x, "y": cdf_y},
        "boxplot_data": boxplot_data,
        "anomaly_rankings": anomaly_rankings,
        "multi_anomaly_ng": multi_anomaly_ng,
        "violations": violation_records[:100],  # Limit for IPC size
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd engine && .venv/bin/pytest tests/test_monte_carlo.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run full test suite**

Run: `cd engine && .venv/bin/pytest -q`
Expected: All tests pass (no regressions)

- [ ] **Step 6: Commit**

```bash
git add engine/src/process_intelligence_engine/monte_carlo.py engine/tests/test_monte_carlo.py
git commit -m "feat(monte_carlo): add Monte Carlo simulation engine with DOE prediction"
```

---

## Task 2: IPC handlers

**Files:**
- Modify: `engine/src/process_intelligence_engine/main.py`
- Test: `engine/tests/test_main_monte_carlo.py`

- [ ] **Step 1: Write the failing test**

Create `engine/tests/test_main_monte_carlo.py`:

```python
"""Tests for Monte Carlo IPC handlers."""
import pytest
from process_intelligence_engine.main import handle_request


def _import_csv_for_mc(tmp_path):
    import numpy as np
    rng = np.random.default_rng(42)
    rows = ["x1,x2,y"]
    for _ in range(100):
        x1 = rng.normal(100, 5)
        x2 = rng.normal(50, 3)
        y = 10 + 2 * x1 - 1.5 * x2 + rng.normal(0, 1)
        rows.append(f"{x1:.4f},{x2:.4f},{y:.4f}")
    path = tmp_path / "mc.csv"
    path.write_text("\n".join(rows), encoding="utf-8")
    return handle_request("data/import", {"file_path": str(path)})["dataset_id"]


def _fit_model(tmp_path, did):
    return handle_request("modeling/fit", {
        "dataset_id": did,
        "model_type": "doe_linear",
        "target": "y",
        "inputs": ["x1", "x2"],
    })


def test_monte_carlo_run_basic(tmp_path):
    did = _import_csv_for_mc(tmp_path)
    fit = _fit_model(tmp_path, did)
    model_id = fit["model_id"]

    result = handle_request("monte_carlo/run", {
        "dataset_id": did,
        "model_id": model_id,
        "n_simulations": 500,
        "seed": 42,
        "enable_anomalies": False,
        "lsl": 50.0,
        "usl": 200.0,
    })
    assert result["success"]
    assert result["result"]["n_simulations"] == 500
    assert result["result"]["ng_count"] >= 0
    assert 0 <= result["result"]["ng_probability"] <= 1
    assert result["result"]["output_mean"] is not None
    assert "histogram" in result["result"]
    assert "cdf_data" in result["result"]
    assert "percentiles" in result["result"]


def test_monte_carlo_run_unknown_model_raises(tmp_path):
    did = _import_csv_for_mc(tmp_path)
    with pytest.raises(KeyError):
        handle_request("monte_carlo/run", {
            "dataset_id": did,
            "model_id": "nonexistent",
            "n_simulations": 100,
            "seed": 42,
            "enable_anomalies": False,
        })


def test_monte_carlo_run_with_anomalies(tmp_path):
    did = _import_csv_for_mc(tmp_path)
    fit = _fit_model(tmp_path, did)
    model_id = fit["model_id"]

    result = handle_request("monte_carlo/run", {
        "dataset_id": did,
        "model_id": model_id,
        "n_simulations": 200,
        "seed": 42,
        "enable_anomalies": True,
        "anomalies": [
            {
                "anomaly_id": "an-1",
                "name": "High x1",
                "target_input": "x1",
                "direction": "above",
                "occurrence_probability": 0.1,
                "magnitude_distribution": {"type": "constant", "value": 20.0},
            }
        ],
        "lsl": 50.0,
        "usl": 200.0,
    })
    assert result["success"]
    assert result["result"]["n_simulations"] == 200


def test_monte_carlo_run_no_bounds(tmp_path):
    did = _import_csv_for_mc(tmp_path)
    fit = _fit_model(tmp_path, did)
    model_id = fit["model_id"]

    result = handle_request("monte_carlo/run", {
        "dataset_id": did,
        "model_id": model_id,
        "n_simulations": 100,
        "seed": 42,
        "enable_anomalies": False,
    })
    assert result["success"]
    assert result["result"]["ng_count"] == 0
    assert result["result"]["ng_probability"] == 0.0


def test_monte_carlo_run_unknown_dataset_raises():
    with pytest.raises(KeyError):
        handle_request("monte_carlo/run", {
            "dataset_id": "nonexistent",
            "model_id": "some-model",
            "n_simulations": 100,
            "seed": 42,
            "enable_anomalies": False,
        })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && .venv/bin/pytest tests/test_main_monte_carlo.py -v`
Expected: FAIL — `ValueError: Unknown method: monte_carlo/run`

- [ ] **Step 3: Add IPC handler to main.py**

In `engine/src/process_intelligence_engine/main.py`, add import:

```python
from process_intelligence_engine.monte_carlo import run_monte_carlo
```

Add handler before `handle_request`:

```python
def _handle_monte_carlo_run(params: dict) -> dict:
    """Run Monte Carlo simulation."""
    did = params["dataset_id"]
    model_id = params["model_id"]
    df = REGISTRY.get(did)
    fit = MODEL_REGISTRY.get(model_id)

    if fit.model_type not in ("doe_linear", "doe_quadratic"):
        raise ValueError(f"Monte Carlo only supports doe_linear and doe_quadratic models, got {fit.model_type}")

    n_simulations = params.get("n_simulations", 10000)
    seed = params.get("seed", 42)
    enable_anomalies = params.get("enable_anomalies", False)
    anomalies = params.get("anomalies", [])
    lsl = params.get("lsl")
    usl = params.get("usl")

    result = run_monte_carlo(
        df=df,
        model_type=fit.model_type,
        coefficients=fit.coefficients or {},
        input_columns=fit.inputs,
        output_column=fit.target,
        n_simulations=n_simulations,
        seed=seed,
        enable_anomalies=enable_anomalies,
        anomalies=anomalies,
        lsl=lsl,
        usl=usl,
    )
    return {"success": True, "result": result}
```

Add dispatch in `handle_request`:

```python
    if method == "monte_carlo/run":
        return _handle_monte_carlo_run(params)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd engine && .venv/bin/pytest tests/test_main_monte_carlo.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run full test suite**

Run: `cd engine && .venv/bin/pytest -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add engine/src/process_intelligence_engine/main.py engine/tests/test_main_monte_carlo.py
git commit -m "feat(monte_carlo): add monte_carlo/run IPC handler"
```

---

## Task 3: Frontend API

**Files:**
- Modify: `src/lib/engine.ts`

- [ ] **Step 1: Add SPC types and functions**

Append to `src/lib/engine.ts`:

```typescript
// --- Phase 9: Monte Carlo Simulation ----------------------------------------

export interface MonteCarloHistogram {
  bins: number[]
  counts: number[]
}

export interface MonteCarloCDFData {
  x: number[]
  y: number[]
}

export interface MonteCarloBoxplotData {
  normal: number[]
  single_anomaly: number[]
  multi_anomaly: number[]
}

export interface MonteCarloAnomalyRanking {
  anomaly_id: string
  name: string
  ng_contribution: number
  probability: number
}

export interface MonteCarloPercentiles {
  p1: number
  p5: number
  p50: number
  p95: number
  p99: number
}

export interface MonteCarloResult {
  n_simulations: number
  seed: number
  ng_count: number
  ng_probability: number
  output_mean: number
  output_std: number
  output_median: number
  percentiles: MonteCarloPercentiles
  histogram: MonteCarloHistogram
  cdf_data: MonteCarloCDFData
  boxplot_data: MonteCarloBoxplotData
  anomaly_rankings: MonteCarloAnomalyRanking[]
  multi_anomaly_ng: number
}

export interface MonteCarloAnalysisResult {
  success: boolean
  result: MonteCarloResult
}

export interface MonteCarloParams {
  dataset_id: string
  model_id: string
  n_simulations?: number
  seed?: number
  enable_anomalies?: boolean
  anomalies?: Array<{
    anomaly_id: string
    name: string
    target_input: string
    direction: 'above' | 'below'
    occurrence_probability: number
    magnitude_distribution: Record<string, unknown>
  }>
  lsl?: number
  usl?: number
}

export async function analyzeMonteCarlo(params: MonteCarloParams): Promise<MonteCarloAnalysisResult> {
  return engineCall<MonteCarloAnalysisResult>('monte_carlo/run', params)
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add src/lib/engine.ts
git commit -m "feat(monte_carlo): add Monte Carlo frontend API types and functions"
```

---

## Task 4: Monte Carlo 前端頁面

**Files:**
- Create: `src/features/monte-carlo/MonteCarlo.tsx`
- Modify: `src/App.tsx`
- Modify: `src/components/layout/Sidebar.tsx`
- Modify: `src/i18n/en.json`, `src/i18n/zh-TW.json`

- [ ] **Step 1: Add i18n strings**

In `src/i18n/en.json`, add to `nav`:
```json
"monteCarlo": "Monte Carlo",
```

Add new section:
```json
"monteCarlo": {
  "title": "Monte Carlo Risk Simulation",
  "selectModel": "Select Model",
  "noModels": "No trained models yet. Go to Model Center to train one first.",
  "nSimulations": "Simulation Count",
  "seed": "Random Seed",
  "enableAnomalies": "Enable Anomaly Scenarios",
  "runSimulation": "Run Simulation",
  "running": "Simulating...",
  "ngProbability": "NG Probability",
  "outputDistribution": "Output Distribution",
  "percentiles": "Percentiles",
  "p1": "P1",
  "p5": "P5",
  "p50": "P50 (Median)",
  "p95": "P95",
  "p99": "P99",
  "anomalyRankings": "Anomaly Risk Rankings",
  "noAnomalies": "No anomaly scenarios configured",
  "mean": "Mean",
  "std": "Std Dev",
  "median": "Median",
  "ngCount": "NG Count",
  "totalSimulations": "Total Simulations",
  "multiAnomalyNG": "Multi-Anomaly NG",
  "selectModelFirst": "Please select a model and click Run Simulation.",
  "noData": "Please import data first."
}
```

Same for `src/i18n/zh-TW.json`:
```json
"monteCarlo": {
  "title": "蒙地卡羅風險模擬",
  "selectModel": "選擇模型",
  "noModels": "尚未訓練模型。請先到模型中心訓練。",
  "nSimulations": "模擬次數",
  "seed": "隨機種子",
  "enableAnomalies": "啟用異常場景",
  "runSimulation": "執行模擬",
  "running": "模擬中...",
  "ngProbability": "NG 機率",
  "outputDistribution": "輸出分布",
  "percentiles": "百分位數",
  "p1": "P1",
  "p5": "P5",
  "p50": "P50 (中位數)",
  "p95": "P95",
  "p99": "P99",
  "anomalyRankings": "異常風險排名",
  "noAnomalies": "尚未配置異常場景",
  "mean": "平均",
  "std": "標準差",
  "median": "中位數",
  "ngCount": "NG 次數",
  "totalSimulations": "總模擬次數",
  "multiAnomalyNG": "多重異常 NG",
  "selectModelFirst": "請選擇模型並按「執行模擬」。",
  "noData": "請先匯入資料。"
}
```

- [ ] **Step 2: Create MonteCarlo.tsx**

Create `src/features/monte-carlo/MonteCarlo.tsx`:

```typescript
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, Select, Space, Button, Alert, Form, Input, Switch, Typography, Table, Tag, Row, Col } from 'antd'
import Plot from 'react-plotly.js'
import { useDataPipelineStore } from '../../stores/dataPipelineStore'
import { analyzeMonteCarlo, listModels, type MonteCarloResult, type MonteCarloAnomalyRanking } from '../../lib/engine'

export default function MonteCarlo() {
  const { t } = useTranslation()
  const { importResult } = useDataPipelineStore()

  const [models, setModels] = useState<Array<{ model_id: string; model_type: string; equation: string }>>([])
  const [selectedModel, setSelectedModel] = useState<string | undefined>()
  const [nSimulations, setNSimulations] = useState<number>(10000)
  const [seed, setSeed] = useState<number>(42)
  const [enableAnomalies, setEnableAnomalies] = useState<boolean>(false)
  const [result, setResult] = useState<MonteCarloResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listModels().then(r => {
      if (r.models) {
        setModels(r.models.map(m => ({ model_id: m.model_id, model_type: m.model_type, equation: m.equation })))
      }
    }).catch(() => {})
  }, [])

  const handleRun = async () => {
    if (!importResult || !selectedModel) return
    setLoading(true)
    setError(null)
    try {
      const res = await analyzeMonteCarlo({
        dataset_id: importResult.dataset_id,
        model_id: selectedModel,
        n_simulations: nSimulations,
        seed,
        enable_anomalies: enableAnomalies,
      })
      setResult(res.result)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  const ngColor = (p: number) => {
    if (p === 0) return 'default'
    if (p < 0.01) return 'success'
    if (p < 0.05) return 'warning'
    return 'error'
  }

  const histogramTrace = result ? {
    x: result.histogram.bins.slice(0, -1),
    y: result.histogram.counts,
    type: 'bar',
    marker: { color: '#1677ff' },
    name: 'Histogram',
  } : undefined

  const cdfTrace = result ? {
    x: result.cdf_data.x,
    y: result.cdf_data.y,
    type: 'scatter',
    mode: 'lines',
    line: { color: '#722ed1' },
    name: 'CDF',
  } : undefined

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card title={t('monteCarlo.title')}>
        <Space wrap style={{ marginBottom: 12 }}>
          <Form.Item label={t('monteCarlo.selectModel')} style={{ margin: 0 }}>
            <Select
              value={selectedModel}
              onChange={setSelectedModel}
              options={models.map(m => ({
                value: m.model_id,
                label: `${m.model_type} — ${m.equation.slice(0, 50)}...`,
              }))}
              disabled={models.length === 0}
              style={{ width: 320 }}
              placeholder={t('monteCarlo.noModels')}
            />
          </Form.Item>
          <Form.Item label={t('monteCarlo.nSimulations')} style={{ margin: 0 }}>
            <Input
              type="number"
              min={100}
              max={100000}
              value={nSimulations}
              onChange={e => setNSimulations(Number(e.target.value))}
              style={{ width: 100 }}
            />
          </Form.Item>
          <Form.Item label={t('monteCarlo.seed')} style={{ margin: 0 }}>
            <Input
              type="number"
              value={seed}
              onChange={e => setSeed(Number(e.target.value))}
              style={{ width: 80 }}
            />
          </Form.Item>
          <Form.Item label={t('monteCarlo.enableAnomalies')} style={{ margin: 0 }}>
            <Switch checked={enableAnomalies} onChange={setEnableAnomalies} />
          </Form.Item>
          <Button type="primary" onClick={handleRun} loading={loading} disabled={!importResult || !selectedModel}>
            {t('monteCarlo.runSimulation')}
          </Button>
        </Space>
        {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 12 }} />}
      </Card>

      {result && (
        <>
          <Row gutter={16}>
            <Col span={6}>
              <Card size="small" style={{ textAlign: 'center' }}>
                <Typography.Text type="secondary">{t('monteCarlo.ngProbability')}</Typography.Text>
                <Typography.Title level={3} style={{ margin: '8px 0', color: ngColor(result.ng_probability) >= 0 ? '#ff4d4f' : '#52c41a' }}>
                  {(result.ng_probability * 100).toFixed(2)}%
                </Typography.Title>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {t('monteCarlo.ngCount')}: {result.ng_count} / {result.n_simulations}
                </Typography.Text>
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" style={{ textAlign: 'center' }}>
                <Typography.Text type="secondary">{t('monteCarlo.mean')}</Typography.Text>
                <Typography.Title level={4} style={{ margin: '8px 0' }}>{result.output_mean.toFixed(2)}</Typography.Title>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>σ = {result.output_std.toFixed(2)}</Typography.Text>
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" style={{ textAlign: 'center' }}>
                <Typography.Text type="secondary">{t('monteCarlo.median')}</Typography.Text>
                <Typography.Title level={4} style={{ margin: '8px 0' }}>{result.output_median.toFixed(2)}</Typography.Title>
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" style={{ textAlign: 'center' }}>
                <Typography.Text type="secondary">{t('monteCarlo.multiAnomalyNG')}</Typography.Text>
                <Typography.Title level={4} style={{ margin: '8px 0' }}>{result.multi_anomaly_ng}</Typography.Title>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {t('monteCarlo.totalSimulations')}: {result.n_simulations}
                </Typography.Text>
              </Card>
            </Col>
          </Row>

          <Row gutter={16}>
            {[
              { label: t('monteCarlo.p1'), value: result.percentiles.p1 },
              { label: t('monteCarlo.p5'), value: result.percentiles.p5 },
              { label: t('monteCarlo.p50'), value: result.percentiles.p50 },
              { label: t('monteCarlo.p95'), value: result.percentiles.p95 },
              { label: t('monteCarlo.p99'), value: result.percentiles.p99 },
            ].map(p => (
              <Col key={p.label} span={4}>
                <Card size="small" style={{ textAlign: 'center' }}>
                  <Typography.Text type="secondary" style={{ fontSize: 11 }}>{p.label}</Typography.Text>
                  <Typography.Text strong style={{ display: 'block' }}>{p.value.toFixed(2)}</Typography.Text>
                </Card>
              </Col>
            ))}
          </Row>

          <Card title={t('monteCarlo.outputDistribution')} size="small">
            <Space direction="horizontal" style={{ width: '100%' }}>
              <Plot
                data={[histogramTrace].filter(Boolean)}
                layout={{
                  title: 'Output Histogram',
                  margin: { t: 30, b: 40, l: 50, r: 30 },
                  height: 280,
                  xaxis: { title: 'Output Value' },
                  yaxis: { title: 'Count' },
                }}
                config={{ responsive: true, displayModeBar: false }}
                style={{ flex: 1 }}
              />
              <Plot
                data={[cdfTrace].filter(Boolean)}
                layout={{
                  title: 'CDF',
                  margin: { t: 30, b: 40, l: 50, r: 30 },
                  height: 280,
                  xaxis: { title: 'Output Value' },
                  yaxis: { title: 'Cumulative Probability' },
                }}
                config={{ responsive: true, displayModeBar: false }}
                style={{ flex: 1 }}
              />
            </Space>
          </Card>

          {result.anomaly_rankings.length > 0 && (
            <Card title={`${t('monteCarlo.anomalyRankings')} (${result.anomaly_rankings.length})`} size="small">
              <Table
                dataSource={result.anomaly_rankings}
                columns={[
                  { title: 'ID', dataIndex: 'anomaly_id', key: 'anomaly_id', width: 100 },
                  { title: 'Name', dataIndex: 'name', key: 'name' },
                  { title: 'NG Contribution', dataIndex: 'ng_contribution', key: 'ng_contribution', width: 120,
                    render: (v: number) => <Tag color="error">{v}</Tag> },
                  { title: 'Probability', dataIndex: 'probability', key: 'probability', width: 100,
                    render: (v: number) => `${(v * 100).toFixed(1)}%` },
                ]}
                rowKey="anomaly_id"
                size="small"
                pagination={false}
              />
            </Card>
          )}
        </>
      )}

      {!result && importResult && (
        <Alert type="info" message={t('monteCarlo.selectModelFirst')} showIcon />
      )}
      {!importResult && (
        <Alert type="warning" message={t('monteCarlo.noData')} showIcon />
      )}
    </div>
  )
}
```

- [ ] **Step 3: Wire up in App.tsx**

In `src/App.tsx`, add import and route:
```typescript
import MonteCarlo from './features/monte-carlo/MonteCarlo'
// ...
if (activeTab === 'monteCarlo') return <MonteCarlo />
```

- [ ] **Step 4: Add Monte Carlo tab to Sidebar**

In `src/components/layout/Sidebar.tsx`, add to `tabItems`:
```typescript
{ key: 'monteCarlo', icon: <RobotOutlined /> },
```

- [ ] **Step 5: Verify TypeScript compiles**

Run: `npx tsc --noEmit`
Expected: No errors

- [ ] **Step 6: Build**

Run: `npm run build`
Expected: Build success

- [ ] **Step 7: Run tests**

Run: `cd engine && .venv/bin/pytest -q`
Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
git add engine/src/process_intelligence_engine/monte_carlo.py engine/tests/test_monte_carlo.py engine/src/process_intelligence_engine/main.py engine/tests/test_main_monte_carlo.py src/lib/engine.ts src/features/monte-carlo/MonteCarlo.tsx src/App.tsx src/components/layout/Sidebar.tsx src/i18n/en.json src/i18n/zh-TW.json
git commit -m "feat(monte_carlo): add Monte Carlo simulation with DOE model prediction and NG analysis"
```

---

## Self-Review

**Spec coverage:**
- [x] Monte Carlo simulation engine
- [x] Input distribution sampling (normal, histogram fallback)
- [x] Anomaly scenario integration
- [x] DOE linear/quadratic model prediction
- [x] NG probability calculation
- [x] Percentiles (P1/P5/P50/P95/P99)
- [x] Histogram + CDF charts
- [x] Anomaly risk rankings
- [x] IPC handlers (`monte_carlo/run`)
- [x] Frontend API (`analyzeMonteCarlo`)
- [x] Frontend UI with Plotly charts
- [x] i18n en/zh-TW
- [x] Tests for engine and IPC

**Scope check:**
- Random Forest / Hybrid NOT included (as specified)
- Copula NOT included (as specified)
- Result persistence NOT included (as specified)

**Type consistency:** All types (`MonteCarloResult`, `MonteCarloHistogram`, etc.) defined in `engine.ts` and used consistently in `MonteCarlo.tsx`.

---

## Verification Commands

```bash
# Backend tests
cd engine && .venv/bin/pytest tests/test_monte_carlo.py tests/test_main_monte_carlo.py -v

# Full test suite
cd engine && .venv/bin/pytest -q

# TypeScript check
npx tsc --noEmit

# Build
npm run build

# Run app
npm run tauri dev
```
