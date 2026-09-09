"""Report generation data models."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


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
