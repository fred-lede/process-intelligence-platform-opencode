"""SPC calculation engine — I-MR, X-bar/R, X-bar/S, Western Electric rules, capability indices.

All functions return plain Python dicts/lists (JSON-serializable). No dataclasses
are used in return types to keep the IPC payload lightweight.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

# ── SPC constants (Subgroup size 2–10) ──────────────────────────────────────
_A2: dict[int, float] = {2: 1.880, 3: 1.023, 4: 0.729, 5: 0.577, 6: 0.483, 7: 0.419,
                         8: 0.373, 9: 0.337, 10: 0.308}
_D3: dict[int, float] = {2: 0, 3: 0, 4: 0, 5: 0, 6: 0.076, 7: 0.136, 8: 0.184,
                         9: 0.223, 10: 0.256}
_D4: dict[int, float] = {2: 3.267, 3: 2.574, 4: 2.282, 5: 2.114, 6: 2.004, 7: 1.924,
                         8: 1.864, 9: 1.816, 10: 1.777}
_d2: dict[int, float] = {2: 1.128, 3: 1.693, 4: 2.059, 5: 2.326, 6: 2.534, 7: 2.704,
                         8: 2.847, 9: 2.970, 10: 3.078}
_B3: dict[int, float] = {2: 0, 3: 0, 4: 0, 5: 0, 6: 0.030, 7: 0.118, 8: 0.185,
                         9: 0.239, 10: 0.284}
_B4: dict[int, float] = {2: 3.267, 3: 2.568, 4: 2.266, 5: 2.089, 6: 1.970, 7: 1.882,
                         8: 1.815, 9: 1.761, 10: 1.716}
# A3 = 3/(d2 * sqrt(n)) — computed on demand


def _safe_div(a: float, b: float) -> float:
    return a / b if b != 0 else float("nan")


# ── Capability ───────────────────────────────────────────────────────────────

def compute_capability(
    values: list[float] | np.ndarray,
    lsl: float | None = None,
    usl: float | None = None,
    subgroup_size: int = 1,
) -> dict[str, Any]:
    """Compute process capability indices Cp, Cpk, Pp, Ppk.

    σ_within is estimated from moving-range when subgroup_size == 1,
    otherwise from within-subgroup variation.
    """
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        raise ValueError("values must not be empty")

    mean = float(np.mean(arr))
    overall_std = float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0

    if subgroup_size <= 1 or arr.size < 2:
        # Use overall std as the within estimate
        sigma_within = overall_std
        n_subgroups = int(arr.size)
    else:
        n = arr.size
        n_subgroups = n // subgroup_size
        if n_subgroups == 0:
            sigma_within = overall_std
            n_subgroups = 1
        else:
            subgroups = [arr[i * subgroup_size:(i + 1) * subgroup_size]
                         for i in range(n_subgroups)]
            ranges = [float(np.max(s) - np.min(s)) for s in subgroups]
            r_bar = float(np.mean(ranges)) if ranges else 0.0
            d2 = _d2.get(subgroup_size)
            sigma_within = _safe_div(r_bar, d2) if d2 else 0.0

    if lsl is not None and usl is not None and sigma_within > 0:
        cp = _safe_div(usl - lsl, 6 * sigma_within)
        cpk = min(_safe_div(usl - mean, 3 * sigma_within),
                  _safe_div(mean - lsl, 3 * sigma_within))
    else:
        cp = None
        cpk = None

    if lsl is not None and usl is not None and overall_std > 0:
        pp = _safe_div(usl - lsl, 6 * overall_std)
        ppk = min(_safe_div(usl - mean, 3 * overall_std),
                  _safe_div(mean - lsl, 3 * overall_std))
    else:
        pp = None
        ppk = None

    return {
        "cp": round(cp, 6) if cp is not None else None,
        "cpk": round(cpk, 6) if cpk is not None else None,
        "pp": round(pp, 6) if pp is not None else None,
        "ppk": round(ppk, 6) if ppk is not None else None,
        "sigma_within": round(sigma_within, 6),
        "sigma_overall": round(overall_std, 6),
        "mean": round(mean, 6),
        "n_subgroups": n_subgroups,
        "total_observations": int(arr.size),
    }


# ── I-MR Chart ───────────────────────────────────────────────────────────────

def compute_i_mr(
    values: list[float] | np.ndarray,
    lsl: float | None = None,
    usl: float | None = None,
) -> dict[str, Any]:
    """Compute an Individuals and Moving Range (I-MR) control chart."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        raise ValueError("values must not be empty")

    x_values = [round(float(v), 6) for v in arr]
    mr_values = [round(float(abs(arr[i] - arr[i - 1])), 6) for i in range(1, arr.size)]
    # Pad to same length as x_values for the output; missing MR for first point is None
    mr_padded = [None] + mr_values

    x_bar = float(np.mean(arr))
    mr_bar = float(np.mean(mr_values)) if mr_values else 0.0
    d2_i = _d2.get(2)  # 1.128 for n=2 moving range
    sigma_est = _safe_div(mr_bar, d2_i) if d2_i else 0.0

    ucl_x = x_bar + 3 * sigma_est
    lcl_x = x_bar - 3 * sigma_est

    x_limits = {
        "ucl": round(ucl_x, 6),
        "lcl": round(lcl_x, 6),
        "cl": round(x_bar, 6),
    }
    mr_ucl = 3.267 * mr_bar  # D4 for n=2
    mr_limits = {
        "ucl": round(mr_ucl, 6),
        "lcl": 0.0,
        "cl": round(mr_bar, 6),
    }

    violations = detect_we_violations(arr, x_bar, sigma_est)

    cap = compute_capability(arr.tolist(), lsl=lsl, usl=usl, subgroup_size=1)

    return {
        "chart_type": "I-MR",
        "x_values": x_values,
        "control_limits": {"x": x_limits, "mr": mr_limits},
        "mr_values": mr_padded,
        "subgroup_stats": {
            "x_mean": round(x_bar, 6),
            "mr_mean": round(mr_bar, 6),
            "sigma_estimate": round(sigma_est, 6),
        },
        "violations": violations,
        "capability": cap,
    }


# ── X-bar / R Chart ──────────────────────────────────────────────────────────

def compute_xbar_r(
    data: list[list[float]],
    subgroup_size: int = 5,
    lsl: float | None = None,
    usl: float | None = None,
) -> dict[str, Any]:
    """Compute X-bar and R control charts from subgroups."""
    if subgroup_size < 2:
        raise ValueError("subgroup_size must be >= 2 for X-bar/R")
    if subgroup_size not in _A2:
        raise ValueError(f"subgroup_size {subgroup_size} not supported; use 2–10")

    subgroups = []
    xbars = []
    rs = []
    for sg in data:
        arr = np.asarray(sg, dtype=float)
        if arr.size != subgroup_size:
            continue
        subgroups.append([round(float(v), 6) for v in arr])
        xbars.append(round(float(np.mean(arr)), 6))
        rs.append(round(float(np.max(arr) - np.min(arr)), 6))

    if not xbars:
        raise ValueError("no valid subgroups found")

    x_double_bar = float(np.mean(xbars))
    r_bar = float(np.mean(rs))

    a2 = _A2[subgroup_size]
    d3 = _D3[subgroup_size]
    d4 = _D4[subgroup_size]
    d2 = _d2[subgroup_size]

    xcl_ucl = x_double_bar + a2 * r_bar
    xcl_lcl = x_double_bar - a2 * r_bar
    rcl_ucl = d4 * r_bar
    rcl_lcl = d3 * r_bar
    sigma_est = _safe_div(r_bar, d2)

    violations = detect_we_violations(np.array(xbars), x_double_bar, sigma_est)

    cap = compute_capability(
        np.concatenate([np.asarray(s, dtype=float) for s in data]).tolist(),
        lsl=lsl, usl=usl, subgroup_size=subgroup_size,
    )

    return {
        "chart_type": "X-bar/R",
        "xbar_values": xbars,
        "r_values": rs,
        "subgroups": subgroups,
        "control_limits": {
            "x": {
                "ucl": round(xcl_ucl, 6),
                "lcl": round(xcl_lcl, 6),
                "cl": round(x_double_bar, 6),
            },
            "r": {
                "ucl": round(rcl_ucl, 6),
                "lcl": round(rcl_lcl, 6),
                "cl": round(r_bar, 6),
            },
        },
        "violations": violations,
        "capability": cap,
    }


# ── X-bar / S Chart ──────────────────────────────────────────────────────────

def compute_xbar_s(
    data: list[list[float]],
    subgroup_size: int = 6,
    lsl: float | None = None,
    usl: float | None = None,
) -> dict[str, Any]:
    """Compute X-bar and S control charts from subgroups."""
    if subgroup_size < 2:
        raise ValueError("subgroup_size must be >= 2 for X-bar/S")
    if subgroup_size not in _A2:
        raise ValueError(f"subgroup_size {subgroup_size} not supported; use 2–10")

    # A3 = 3/(d2 * sqrt(n))
    d2_n = _d2[subgroup_size]
    a3 = 3.0 / (d2_n * math.sqrt(subgroup_size))
    b3 = _B3[subgroup_size]
    b4 = _B4[subgroup_size]

    subgroups = []
    xbars = []
    ss = []
    for sg in data:
        arr = np.asarray(sg, dtype=float)
        if arr.size != subgroup_size:
            continue
        subgroups.append([round(float(v), 6) for v in arr])
        xbars.append(round(float(np.mean(arr)), 6))
        ss.append(round(float(np.std(arr, ddof=1)), 6))

    if not xbars:
        raise ValueError("no valid subgroups found")

    x_double_bar = float(np.mean(xbars))
    s_bar = float(np.mean(ss))
    sigma_est = _safe_div(s_bar, d2_n)

    xcl_ucl = x_double_bar + a3 * s_bar
    xcl_lcl = x_double_bar - a3 * s_bar
    scl_ucl = b4 * s_bar
    scl_lcl = b3 * s_bar

    violations = detect_we_violations(np.array(xbars), x_double_bar, sigma_est)

    cap = compute_capability(
        np.concatenate([np.asarray(s, dtype=float) for s in data]).tolist(),
        lsl=lsl, usl=usl, subgroup_size=subgroup_size,
    )

    return {
        "chart_type": "X-bar/S",
        "xbar_values": xbars,
        "s_values": ss,
        "subgroups": subgroups,
        "control_limits": {
            "x": {
                "ucl": round(xcl_ucl, 6),
                "lcl": round(xcl_lcl, 6),
                "cl": round(x_double_bar, 6),
            },
            "s": {
                "ucl": round(scl_ucl, 6),
                "lcl": round(scl_lcl, 6),
                "cl": round(s_bar, 6),
            },
        },
        "violations": violations,
        "capability": cap,
    }


# ── Western Electric Rules ───────────────────────────────────────────────────

_RULE_NAMES = {
    1: "beyond_3sigma",
    2: "2_of_3_beyond_2sigma",
    3: "4_of_5_beyond_1sigma",
    4: "8_consecutive_same_side",
    5: "6_consecutive_trend",
    6: "15_consecutive_within_1sigma",
    7: "14_consecutive_alternating",
}


def detect_we_violations(
    values: list[float] | np.ndarray,
    center: float,
    sigma: float,
) -> list[dict[str, Any]]:
    """Detect Western Electric rule violations.

    Returns a list of dicts, each with keys: rule, point_idx, description.
    """
    arr = np.asarray(values, dtype=float)
    if sigma <= 0:
        return []

    violations: list[dict[str, Any]] = []
    n = arr.size
    z = (arr - center) / sigma  # standardised scores

    # Rule 1: 1 point beyond 3σ
    for i in range(n):
        if abs(z[i]) > 3:
            side = "above" if z[i] > 0 else "below"
            violations.append({
                "rule": "beyond_3sigma",
                "point_idx": int(i),
                "description": f"Point {i} is beyond 3σ ({side}) — z={z[i]:.2f}",
            })

    # Rule 2: 2 of 3 points beyond 2σ (same side)
    for i in range(2, n):
        for start in range(i - 2, max(i - 3, -1), -1):
            if start < 0:
                continue
            window = z[start:i + 1]
            above = int((window > 2).sum())
            below = int((window < -2).sum())
            if above >= 2:
                violations.append({
                    "rule": "2_of_3_beyond_2sigma",
                    "point_idx": int(i),
                    "description": f"2 of 3 points beyond +2σ around index {i}",
                })
                break
            if below >= 2:
                violations.append({
                    "rule": "2_of_3_beyond_2sigma",
                    "point_idx": int(i),
                    "description": f"2 of 3 points beyond -2σ around index {i}",
                })
                break

    # Rule 3: 4 of 5 points beyond 1σ (same side)
    for i in range(4, n):
        window = z[i - 4:i + 1]
        above = int((window > 1).sum())
        below = int((window < -1).sum())
        if above >= 4:
            violations.append({
                "rule": "4_of_5_beyond_1sigma",
                "point_idx": int(i),
                "description": f"4 of 5 points beyond +1σ around index {i}",
            })
        elif below >= 4:
            violations.append({
                "rule": "4_of_5_beyond_1sigma",
                "point_idx": int(i),
                "description": f"4 of 5 points beyond -1σ around index {i}",
            })

    # Rule 4: 8 consecutive points on same side of center
    if n >= 8:
        same_side_runs: list[bool] = (z > 0).tolist()
        run_len = 0
        for i in range(n):
            if same_side_runs[i]:
                run_len += 1
                if run_len == 8:
                    violations.append({
                        "rule": "8_consecutive_same_side",
                        "point_idx": int(i),
                        "description": f"8 consecutive points above center ending at {i}",
                    })
            else:
                run_len = 0
        run_len = 0
        same_side_runs = (z < 0).tolist()
        for i in range(n):
            if same_side_runs[i]:
                run_len += 1
                if run_len == 8:
                    violations.append({
                        "rule": "8_consecutive_same_side",
                        "point_idx": int(i),
                        "description": f"8 consecutive points below center ending at {i}",
                    })
            else:
                run_len = 0

    # Rule 5: 6 consecutive points trending up or down
    if n >= 6:
        diffs = np.diff(arr)
        # Up trend: 5 consecutive positive diffs
        up_run = 0
        for i in range(1, n):
            if diffs[i - 1] > 0:
                up_run += 1
                if up_run == 5:
                    violations.append({
                        "rule": "6_consecutive_trend",
                        "point_idx": int(i),
                        "description": f"6 consecutive points trending up ending at {i}",
                    })
            else:
                up_run = 0
        # Down trend: 5 consecutive negative diffs
        down_run = 0
        for i in range(1, n):
            if diffs[i - 1] < 0:
                down_run += 1
                if down_run == 5:
                    violations.append({
                        "rule": "6_consecutive_trend",
                        "point_idx": int(i),
                        "description": f"6 consecutive points trending down ending at {i}",
                    })
            else:
                down_run = 0

    # Rule 6: 15 consecutive points within ±1σ
    if n >= 15:
        within = ((z > -1) & (z < 1)).tolist()
        run_len = 0
        for i in range(n):
            if within[i]:
                run_len += 1
                if run_len == 15:
                    violations.append({
                        "rule": "15_consecutive_within_1sigma",
                        "point_idx": int(i),
                        "description": f"15 consecutive points within ±1σ ending at {i}",
                    })
            else:
                run_len = 0

    # Rule 7: 14 consecutive points alternating up/down
    if n >= 14:
        alt_run = 0
        for i in range(2, n):
            if (diffs[i - 1] > 0 and diffs[i - 2] < 0) or (diffs[i - 1] < 0 and diffs[i - 2] > 0):
                alt_run += 1
                if alt_run == 12:  # 14 points = 13 alternating diffs, but we track consecutive
                    violations.append({
                        "rule": "14_consecutive_alternating",
                        "point_idx": int(i),
                        "description": f"14 consecutive points alternating ending at {i}",
                    })
            else:
                alt_run = 0

    return violations
