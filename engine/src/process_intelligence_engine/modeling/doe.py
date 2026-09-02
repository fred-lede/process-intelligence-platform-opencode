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
    runs = []
    coded_runs = []
    for combo in all_coded:
        coded_row = {f["name"]: v for f, v in zip(factors, combo)}
        coded_runs.append(coded_row)
        actual_row = {}
        for f, v in zip(factors, combo):
            low, high = f["low"], f["high"]
            if levels == 2:
                actual_row[f["name"]] = low if v == -1 else high
            elif levels == 3:
                if v == -1:
                    actual_row[f["name"]] = low
                elif v == 0:
                    actual_row[f["name"]] = (low + high) / 2
                else:
                    actual_row[f["name"]] = high
            else:
                t = (v - coded_levels[0]) / (coded_levels[-1] - coded_levels[0])
                actual_row[f["name"]] = low + t * (high - low)
        runs.append(actual_row)

    return {
        "design_type": "full_factorial",
        "n_runs": len(runs),
        "runs": runs,
        "coded_runs": coded_runs,
    }


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

    runs = []
    coded_runs = []
    for combo in base:
        # Generator: last factor = product of first two (resolution III)
        interaction = combo[0] * combo[1]
        full_combo = combo + (interaction,)
        coded_row = {f["name"]: v for f, v in zip(factors, full_combo)}
        coded_runs.append(coded_row)
        actual_row = {}
        for f, v in zip(factors, full_combo):
            actual_row[f["name"]] = f["low"] if v == -1 else f["high"]
        runs.append(actual_row)

    return {
        "design_type": "fractional_factorial",
        "n_runs": len(runs),
        "runs": runs,
        "coded_runs": coded_runs,
    }
