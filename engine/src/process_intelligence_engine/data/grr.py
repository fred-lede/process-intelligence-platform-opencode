"""Gage R&R (Repeatability & Reproducibility) analysis.

Implements the AIEM (Average and Range) method for crossed GRR studies.

Reference: AIAG Manual, Measurement Systems Analysis (4th ed.)

Input requirements:
    - A DataFrame with columns: part_id, operator, measurement
    - Each part is measured by each operator (crossed design)
    - Typically 2–3 repetitions per operator-part combination

Output:
    - Repeatability (EV) — equipment variation
    - Reproducibility (AV) — operator variation
    - GRR = sqrt(EV² + AV²)
    - Part variation (PV)
    - Total variation (TV)
    - %GRR = GRR / TV * 100
    - %Part = PV / TV * 100
    - Acceptance verdict (AIAG criteria)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class GrrResult:
    """Result of a Gage R&R study."""

    method: str
    n_parts: int
    n_operators: int
    n_reps: int
    repeatability_std: float  # EV
    reproducibility_std: float  # AV
    grr_std: float  # sqrt(EV^2 + AV^2)
    part_variation_std: float  # PV
    total_variation_std: float  # TV
    pct_grr: float  # % of total variation
    pct_part: float  # % of total variation due to parts
    verdict: str  # "acceptable" | "marginal" | "unacceptable"
    verdict_reason: str
    operator_means: dict[str, list[float]] = field(default_factory=dict)
    part_means: dict[str, list[float]] = field(default_factory=dict)
    operator_part_means: dict[str, dict[str, float]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "n_parts": self.n_parts,
            "n_operators": self.n_operators,
            "n_reps": self.n_reps,
            "repeatability_std": round(self.repeatability_std, 6),
            "reproducibility_std": round(self.reproducibility_std, 6),
            "grr_std": round(self.grr_std, 6),
            "part_variation_std": round(self.part_variation_std, 6),
            "total_variation_std": round(self.total_variation_std, 6),
            "pct_grr": round(self.pct_grr, 2),
            "pct_part": round(self.pct_part, 2),
            "verdict": self.verdict,
            "verdict_reason": self.verdict_reason,
            "operator_means": self.operator_means,
            "part_means": self.part_means,
            "operator_part_means": self.operator_part_means,
            "warnings": self.warnings,
        }


def analyze_grr(
    df: pd.DataFrame,
    measurement_column: str,
    part_column: str,
    operator_column: str,
    xbar_chart: bool = False,
) -> GrrResult:
    """Perform a Gage R&R analysis using the AIEM (Average and Range) method.

    Args:
        df: DataFrame containing measurement data.
        measurement_column: Column name with the measurement values.
        part_column: Column name identifying each part (categorical).
        operator_column: Column name identifying each operator.
        xbar_chart: If True, also return X-bar chart control limits.

    Returns:
        GrrResult with all computed statistics.
    """
    cols = df[[measurement_column, part_column, operator_column]].copy()
    cols[measurement_column] = pd.to_numeric(cols[measurement_column], errors="coerce")
    cols = cols.dropna()

    if len(cols) < 3:
        raise ValueError("Need at least 3 measurements for GRR analysis.")

    operators = sorted(cols[operator_column].astype(str).unique())
    parts = sorted(cols[part_column].astype(str).unique())
    n_ops = len(operators)
    n_parts = len(parts)
    reps_per_cell = len(cols) / (n_ops * n_parts)

    if reps_per_cell < 1 or abs(reps_per_cell - round(reps_per_cell)) > 0.01:
        raise ValueError(
            f"Uneven design: expected integer reps per operator-part cell, "
            f"got {reps_per_cell:.2f}. Use balanced data."
        )
    n_reps = int(round(reps_per_cell))

    warnings: list[str] = []

    # --- Grand mean ---
    grand_mean = float(cols[measurement_column].mean())

    # --- Repeatability (EV): within-operator, within-part variation ---
    # Average range within each operator-part cell
    cell_ranges: list[float] = []
    operator_part_means: dict[str, dict[str, float]] = {}
    for op in operators:
        op_data = cols[cols[operator_column].astype(str) == op]
        op_part_means: dict[str, float] = {}
        for part in parts:
            part_vals = op_data[op_data[part_column].astype(str) == part][
                measurement_column
            ].to_numpy(dtype=float)
            if len(part_vals) >= 2:
                cell_ranges.append(float(part_vals.max() - part_vals.min()))
            op_part_means[part] = float(part_vals.mean())
        operator_part_means[op] = op_part_means

    d2_table = {1: 1.000, 2: 1.128, 3: 1.693, 4: 2.059, 5: 2.326, 6: 2.534}
    d2 = d2_table.get(n_reps, 2.326)

    avg_range = float(np.mean(cell_ranges)) if cell_ranges else 0.0
    ev_std = avg_range / d2 if d2 > 0 else 0.0

    # --- Reproducibility (AV): operator-to-operator variation ---
    operator_means: dict[str, list[float]] = {}
    for op in operators:
        op_vals = cols[cols[operator_column].astype(str) == op][
            measurement_column
        ].to_numpy(dtype=float)
        operator_means[op] = op_vals.tolist()

    op_avg_means = {op: float(np.mean(vals)) for op, vals in operator_means.items()}
    range_op_avgs = float(max(op_avg_means.values()) - min(op_avg_means.values()))

    k = n_ops  # number of operators
    kav = 1.0 / np.sqrt(k) if k > 0 else 1.0
    rv = range_op_avgs * kav  # range of operator averages
    av_std = np.sqrt(max(0.0, (rv / d2) ** 2 - (ev_std ** 2) / (n_parts * n_reps)))

    # --- GRR ---
    grr_std = float(np.sqrt(ev_std ** 2 + av_std ** 2))

    # --- Part variation (PV) ---
    part_means_dict: dict[str, list[float]] = {}
    for part in parts:
        p_vals = cols[cols[part_column].astype(str) == part][
            measurement_column
        ].to_numpy(dtype=float)
        part_means_dict[part] = p_vals.tolist()

    part_averages = np.array([float(np.mean(vals)) for vals in part_means_dict.values()])
    range_parts = float(max(part_averages) - min(part_averages))
    d3_table = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0, 6: 0.0}
    d3 = d3_table.get(n_parts, 0.0)
    u3 = 3.0  # control limit factor
    pv_std = range_parts / (u3 * d2) if d2 > 0 else 0.0

    # --- Total variation ---
    tv_std = float(np.sqrt(grr_std ** 2 + pv_std ** 2))

    # --- Percentages ---
    pct_grr = (grr_std / tv_std * 100) if tv_std > 0 else 0.0
    pct_part = (pv_std / tv_std * 100) if tv_std > 0 else 0.0

    # --- Verdict (AIAG criteria) ---
    if pct_grr < 10:
        verdict = "acceptable"
        verdict_reason = f"%GRR = {pct_grr:.1f}% (< 10%): Measurement system is acceptable."
    elif pct_grr < 30:
        verdict = "marginal"
        verdict_reason = (
            f"%GRR = {pct_grr:.1f}% (10–30%): Acceptable depending on application, "
            f"cost, and importance."
        )
    else:
        verdict = "unacceptable"
        verdict_reason = f"%GRR = {pct_grr:.1f}% (≥ 30%): Measurement system needs improvement."

    # Additional warnings
    if ev_std > av_std * 2:
        warnings.append(
            "Repeatability (equipment variation) dominates. "
            "Consider improving measurement fixture stability."
        )
    if av_std > ev_std:
        warnings.append(
            "Reproducibility (operator variation) is significant. "
            "Consider additional operator training."
        )
    if n_parts < 5:
        warnings.append(
            "Few parts used (< 5). GRR results may not be reliable. "
            "Use at least 10 parts for a robust study."
        )
    if n_ops < 2:
        warnings.append("Only one operator. Reproducibility cannot be estimated.")

    return GrrResult(
        method="AIEM (Average and Range)",
        n_parts=n_parts,
        n_operators=n_ops,
        n_reps=n_reps,
        repeatability_std=ev_std,
        reproducibility_std=av_std,
        grr_std=grr_std,
        part_variation_std=pv_std,
        total_variation_std=tv_std,
        pct_grr=pct_grr,
        pct_part=pct_part,
        verdict=verdict,
        verdict_reason=verdict_reason,
        operator_means=operator_means,
        part_means=part_means_dict,
        operator_part_means=operator_part_means,
        warnings=warnings,
    )
