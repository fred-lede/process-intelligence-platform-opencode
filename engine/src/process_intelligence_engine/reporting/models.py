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
    row_count: int = 0
    column_count: int = 0
    
    # Field roles
    fields: list[dict] = field(default_factory=list)
    
    # Quality report
    quality_summary: dict[str, Any] = field(default_factory=dict)
    
    # Model comparison
    model_comparison: list[dict] = field(default_factory=list)
    best_model: dict[str, Any] = field(default_factory=dict)
    
    # Interactions
    interactions: dict[str, Any] = field(default_factory=dict)
    
    # Recommendations
    recommendations: list[dict] = field(default_factory=list)
    
    # Metadata
    version: str = "1.0.0"
    language: str = "en"
