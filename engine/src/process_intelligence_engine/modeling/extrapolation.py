"""Extrapolation risk scoring for model predictions."""
from __future__ import annotations

from typing import Any

import pandas as pd


def compute_extrapolation_risk(
    df: pd.DataFrame,
    prediction_points: list[dict[str, float]] | dict[str, float],
) -> dict[str, Any]:
    """Compute extrapolation risk for prediction points.

    Args:
        df: The training dataset
        prediction_points: Single point or list of points to evaluate

    Returns:
        {
            "risk_scores": list[float],
            "factor_risks": {factor_name: {min, max, risk}},
            "max_risk": float,
            "is_extrapolation": bool
        }
    """
    if isinstance(prediction_points, dict):
        prediction_points = [prediction_points]

    # Compute training ranges
    factor_ranges = {}
    for col in df.columns:
        factor_ranges[col] = {
            "min": float(df[col].min()),
            "max": float(df[col].max()),
            "range": float(df[col].max() - df[col].min()),
        }

    risk_scores = []
    factor_risks = {}

    for point in prediction_points:
        max_risk = 0.0
        point_risks = {}

        for col, ranges in factor_ranges.items():
            value = point.get(col, ranges["min"])
            risk = 0.0

            if ranges["range"] > 0:
                if value < ranges["min"]:
                    risk = (ranges["min"] - value) / ranges["range"]
                elif value > ranges["max"]:
                    risk = (value - ranges["max"]) / ranges["range"]

            max_risk = max(max_risk, risk)
            point_risks[col] = {"min": ranges["min"], "max": ranges["max"], "risk": risk}

        risk_scores.append(max_risk)

        # Aggregate factor risks (use max across all points)
        for col, pr in point_risks.items():
            if col not in factor_risks:
                factor_risks[col] = {"min": pr["min"], "max": pr["max"], "risk": pr["risk"]}
            else:
                factor_risks[col]["risk"] = max(factor_risks[col]["risk"], pr["risk"])

    return {
        "risk_scores": risk_scores,
        "factor_risks": factor_risks,
        "max_risk": max(risk_scores) if risk_scores else 0.0,
        "is_extrapolation": any(r > 0 for r in risk_scores),
    }
