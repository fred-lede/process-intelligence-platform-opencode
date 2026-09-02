"""DOE design generators (Full Factorial, Fractional Factorial)."""
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
