"""Report generation data models."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# Canonical display names, matching the in-app model names (i18n modelType.*). The report
# renderers previously printed the raw id, so an exported report showed
# "doe_categorical_factorial" where the application shows a model name.
MODEL_TYPE_LABELS: dict[str, str] = {
    "doe_linear": "DOE 線性",
    "doe_quadratic": "DOE 二次",
    "doe_categorical_factorial": "DOE 三水準類別因子",
    "random_forest": "隨機樹",
    "residual_hybrid": "殘差混合",
    "logistic_regression": "Logistic 迴歸",
    "weibull_regression": "Weibull 迴歸",
    "xgboost": "XGBoost",
    "lightgbm": "LightGBM",
}


def model_type_label(model_type: Any) -> str:
    """Display name for a model type; keeps the raw id when it is not a known type."""
    key = str(model_type or "")
    return MODEL_TYPE_LABELS.get(key, key)


@dataclass
class ReportData:
    """Data required to generate a report."""
    project_name: str
    operator: str = "Unknown"
    created_at: datetime = field(default_factory=datetime.now)
    
    # Dataset info
    dataset_id: str = ""
    source_file: str = ""
    time_range: dict[str, str] = field(default_factory=dict)
    row_count: int = 0
    column_count: int = 0
    
    # Field roles
    fields: list[dict] = field(default_factory=list)
    spec: dict[str, Any] = field(default_factory=dict)
    
    # Quality report
    quality_summary: dict[str, Any] = field(default_factory=dict)
    
    # Normal & abnormal distributions
    distribution_fits: dict[str, list[dict]] = field(default_factory=dict)
    anomalies: list[dict] = field(default_factory=list)
    
    # Model comparison
    model_comparison: list[dict] = field(default_factory=list)
    best_model: dict[str, Any] = field(default_factory=dict)
    
    # Interactions
    interactions: dict[str, Any] = field(default_factory=dict)
    sensitivity_effects: dict[str, Any] = field(default_factory=dict)
    
    # Monte Carlo
    monte_carlo: dict[str, Any] = field(default_factory=dict)
    
    # Validation / credibility
    credibility: dict[str, Any] = field(default_factory=dict)

    # Designed-DOE validation: the categorical factorial design context (cells, observed
    # cells, replicates, model/residual df, small-design warning) and the recorded
    # confirmation experiments. Both were computed for validation/analyze but never
    # reached the report, so a designed-DOE report showed no ANOVA basis at all.
    design_context: dict[str, Any] = field(default_factory=dict)
    confirmation_evidence: dict[str, Any] = field(default_factory=dict)
    
    # Recommendations + proposed process window
    recommendations: list[dict] = field(default_factory=list)
    process_window: dict[str, Any] = field(default_factory=dict)

    # SPC analysis
    spc_results: list[dict] = field(default_factory=list)

    # Evidence chain (v0.4.0)
    chain_trace: dict = field(default_factory=dict)
    source_labels: dict = field(default_factory=dict)
    gate_summary: dict = field(default_factory=dict)
    approval_record: dict | None = None
    unconfirmed_items: list[str] = field(default_factory=list)
    extrapolation_summary: dict = field(default_factory=dict)
    version_chain_summary: list[dict] = field(default_factory=list)
    readiness_snapshot: dict[str, Any] = field(default_factory=dict)

    # Report status enforced by gate state (v0.4.1)
    report_status: str = "draft"  # "draft" | "approved"
    approved_by: str = ""
    approved_at: str = ""

    # Metadata
    version: str = "1.0.0"
    language: str = "en"
