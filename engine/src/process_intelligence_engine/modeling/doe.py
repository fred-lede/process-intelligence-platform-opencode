"""DOE design generators (Full Factorial, Fractional Factorial, CCD, Box-Behnken,
D-optimal, Taguchi)."""
from __future__ import annotations

import itertools
from typing import Any


def generate_design(
    factors: list[dict[str, Any]],
    design_type: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate an experimental design matrix.

    Args:
        factors: [{"name": str, "low": float, "high": float}, ...]
        design_type: design type string
        params: design-specific parameters

    Returns:
        {"design_type": str, "n_runs": int, "runs": list[dict], "coded_runs": list[dict]}
    """
    params = params or {}
    if not factors:
        raise ValueError("factors must not be empty")

    dispatch = {
        "full_factorial": _full_factorial,
        "fractional_factorial": _fractional_factorial,
        "ccd": _ccd,
        "box_behnken": _box_behnken,
        "d_optimal": _d_optimal,
        "taguchi": _taguchi,
    }
    generator = dispatch.get(design_type)
    if generator is None:
        raise ValueError(f"Unknown design_type: {design_type}")
    return generator(factors, params)


def _full_factorial(factors: list[dict], params: dict) -> dict:
    levels = params.get("levels", 2)
    if levels < 2:
        raise ValueError("levels must be >= 2")
    n = len(factors)

    if levels == 2:
        coded_levels = [-1, 1]
    elif levels == 3:
        coded_levels = [-1, 0, 1]
    else:
        coded_levels = list(range(levels))

    all_coded = list(itertools.product(coded_levels, repeat=n))
    return _build_runs(factors, all_coded, "full_factorial")


def _fractional_factorial(factors: list[dict], params: dict) -> dict:
    """Half-fraction design (Resolution III). Factor order matters: the last
    factor is generated as the interaction of the first two (I = ABC).
    Pass factors in deliberate order to control aliasing structure."""
    levels = params.get("levels", 2)
    n = len(factors)

    if levels != 2:
        raise ValueError("Fractional factorial currently supports 2 levels only")
    if n < 3:
        raise ValueError("Fractional factorial requires at least 3 factors")

    # Half-fraction: generate 2^(n-1) runs using interaction as generator
    n_base = n - 1
    base = list(itertools.product([-1, 1], repeat=n_base))

    full_combos = []
    for combo in base:
        # Generator: last factor = product of first two (resolution III)
        interaction = combo[0] * combo[1]
        full_combos.append(combo + (interaction,))

    return _build_runs(factors, full_combos, "fractional_factorial")


def _build_runs(factors: list[dict], coded_combos: list[tuple], design_type: str) -> dict:
    """Convert coded combinations to actual runs. Maps coded=-1→low, 0→mid, 1→high."""
    runs = []
    coded_runs = []
    for combo in coded_combos:
        coded_row = {f["name"]: v for f, v in zip(factors, combo)}
        coded_runs.append(coded_row)
        actual_row = {}
        for f, v in zip(factors, combo):
            low, high = f["low"], f["high"]
            actual_row[f["name"]] = low + (v + 1) / 2 * (high - low)
        runs.append(actual_row)
    return {"design_type": design_type, "n_runs": len(runs), "runs": runs, "coded_runs": coded_runs}


def _ccd(factors: list[dict], params: dict) -> dict:
    alpha = params.get("alpha", 1.414)
    center_points = params.get("center_points", 1)
    n = len(factors)
    factorial = list(itertools.product([-1, 1], repeat=n))
    axial = []
    for i in range(n):
        lo = [0.0] * n; hi = [0.0] * n
        lo[i] = -alpha; hi[i] = alpha
        axial.append(tuple(lo)); axial.append(tuple(hi))
    center = [tuple([0.0] * n)] * center_points
    return _build_runs(factors, factorial + axial + center, "ccd")


def _box_behnken(factors: list[dict], params: dict) -> dict:
    center_points = params.get("center_points", 1)
    n = len(factors)
    if n < 3:
        raise ValueError("Box-Behnken requires at least 3 factors")
    edge_midpoints = []
    for i in range(n):
        for j in range(i + 1, n):
            for vi in (-1, 1):
                for vj in (-1, 1):
                    row = [0.0] * n
                    row[i] = vi; row[j] = vj
                    edge_midpoints.append(tuple(row))
    center = [tuple([0.0] * n)] * center_points
    return _build_runs(factors, edge_midpoints + center, "box_behnken")


def _d_optimal(factors: list[dict], params: dict) -> dict:
    """D-optimal design: coordinate exchange algorithm to maximize |X'X|."""
    import numpy as np
    n_runs = params.get("n_runs", 8)
    n_candidates = params.get("candidates", 50)
    n_factors = len(factors)

    if n_runs < n_factors + 1:
        raise ValueError(f"n_runs ({n_runs}) must be >= n_factors + 1 ({n_factors + 1})")

    # Generate candidate points (full factorial 2-level + center)
    candidates_coded = list(itertools.product([-1, 1], repeat=n_factors))
    candidates_coded.append(tuple([0.0] * n_factors))
    # Add more random candidates if requested
    rng = np.random.default_rng(42)
    while len(candidates_coded) < n_candidates:
        row = tuple(rng.choice([-1, 0, 1], size=n_factors).tolist())
        candidates_coded.append(row)

    candidates = np.array(candidates_coded[:n_candidates])

    # Start with first n_runs candidates
    selected_idx = list(range(min(n_runs, len(candidates))))
    X = candidates[selected_idx]

    # Coordinate exchange: try swapping each row with each candidate
    for _ in range(20):  # iterations
        improved = False
        for i in range(n_runs):
            det_current = np.linalg.det(X.T @ X) if X.shape[0] == X.shape[1] else 1.0
            for j in range(len(candidates)):
                if j in selected_idx:
                    continue
                X_trial = X.copy()
                X_trial[i] = candidates[j]
                try:
                    det_trial = np.linalg.det(X_trial.T @ X_trial)
                except np.linalg.LinAlgError:
                    continue
                if det_trial > det_current:
                    selected_idx[i] = j
                    X = X_trial
                    det_current = det_trial
                    improved = True
        if not improved:
            break

    coded_combos = [tuple(candidates[i]) for i in selected_idx]
    return _build_runs(factors, coded_combos, "d_optimal")


# Pre-defined Taguchi orthogonal arrays
_TAGUCHI_ARRAYS = {
    "L4": {  # 2-level, up to 3 factors, 4 runs
        "levels": 2, "factors": 3, "runs": [
            (-1, -1, -1), (-1, 1, 1), (1, -1, 1), (1, 1, -1),
        ]
    },
    "L8": {  # 2-level, up to 7 factors, 8 runs
        "levels": 2, "factors": 7, "runs": [
            (-1,-1,-1,-1,-1,-1,-1), (-1,-1,-1, 1, 1, 1, 1),
            (-1, 1, 1,-1,-1, 1, 1), (-1, 1, 1, 1, 1,-1,-1),
            ( 1,-1, 1,-1, 1,-1, 1), ( 1,-1, 1, 1,-1, 1,-1),
            ( 1, 1,-1,-1, 1, 1,-1), ( 1, 1,-1, 1,-1,-1, 1),
        ]
    },
    "L9": {  # 3-level, up to 4 factors, 9 runs
        "levels": 3, "factors": 4, "runs": [
            (-1,-1,-1,-1), (-1, 0, 0, 0), (-1, 1, 1, 1),
            ( 0,-1, 0, 1), ( 0, 0, 1,-1), ( 0, 1,-1, 0),
            ( 1,-1, 1, 0), ( 1, 0,-1, 1), ( 1, 1, 0,-1),
        ]
    },
    "L16": {  # 2-level, up to 15 factors, 16 runs
        "levels": 2, "factors": 15, "runs": [
            tuple(-1 if (j == 0) or ((j > 0) and ((i >> (j-1)) & 1) == 0) else 1
                  for j in range(16))
            for i in range(16)
        ]
    },
}


def _taguchi(factors: list[dict], params: dict) -> dict:
    """Taguchi orthogonal array design."""
    array_name = params.get("array", "L4")
    array = _TAGUCHI_ARRAYS.get(array_name)
    if array is None:
        raise ValueError(f"Unknown Taguchi array: {array_name}. Available: {list(_TAGUCHI_ARRAYS.keys())}")

    n = len(factors)
    if n > array["factors"]:
        raise ValueError(f"{array_name} supports at most {array['factors']} factors, got {n}")

    # Truncate columns to match number of factors
    coded_combos = [row[:n] for row in array["runs"]]
    return _build_runs(factors, coded_combos, "taguchi")
