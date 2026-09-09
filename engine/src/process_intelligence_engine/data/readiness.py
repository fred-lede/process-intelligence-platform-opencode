"""Pre-model data readiness diagnostics."""
from __future__ import annotations

import math
import pandas as pd

from process_intelligence_engine.data.distribution import fit_best_distribution


def analyze_readiness(df: pd.DataFrame, fields: list[dict]) -> dict:
    diagnostics = []
    for field in fields:
        column, role = str(field.get("name", "")), field.get("role", "")
        if role not in ("input", "output") or column not in df.columns:
            continue
        series = df[column]
        numeric = pd.to_numeric(series, errors="coerce")
        valid = numeric.dropna()
        missing = int(numeric.isna().sum())
        issues = []
        if valid.empty:
            issues.append({"severity": "critical", "code": "no_numeric_values", "message": "No valid numeric values."})
        elif valid.nunique() <= 1:
            issues.append({"severity": "warning", "code": "constant_column", "message": "Column has no variation."})
        if missing:
            rate = missing / max(len(series), 1)
            issues.append({"severity": "critical" if rate > 0.5 else "warning", "code": "missing_values", "message": f"{missing} missing values ({rate:.1%})."})
        fits = fit_best_distribution(valid.tolist(), top_n=3) if not valid.empty else []
        best = fits[0] if fits else None
        diagnostics.append({
            "column": column, "role": role, "data_type": str(series.dtype),
            "row_count": int(len(series)), "valid_count": int(valid.size), "missing_count": missing,
            "unique_count": int(valid.nunique()),
            "summary": {"min": float(valid.min()) if not valid.empty else None, "max": float(valid.max()) if not valid.empty else None,
                        "mean": float(valid.mean()) if not valid.empty else None, "std": float(valid.std()) if valid.size > 1 else 0.0},
            "best_distribution": best.name if best else None,
            "distribution_fits": [{"name": f.name, "aic": f.aic, "bic": f.bic, "ks_p_value": f.ks_p_value} for f in fits],
            "issues": issues,
            "status": "critical" if any(i["severity"] == "critical" for i in issues) else "warning" if issues else "info",
        })
    status = "critical" if any(d["status"] == "critical" for d in diagnostics) else "warning" if any(d["status"] == "warning" for d in diagnostics) else "info"
    return {"status": status, "row_count": int(len(df)), "columns": diagnostics}
