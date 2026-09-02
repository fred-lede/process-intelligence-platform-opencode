"""Base report generator."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

from .models import ReportData


class ReportGenerator(ABC):
    """Abstract base class for report generators."""
    
    def __init__(self, data: ReportData):
        self.data = data
    
    @abstractmethod
    def generate(self) -> str:
        """Generate the report content."""
        pass
    
    def _format_number(self, value: float, decimals: int = 4) -> str:
        if value is None:
            return "N/A"
        return f"{value:.{decimals}f}"
    
    def _format_percentage(self, value: float) -> str:
        return f"{value * 100:.1f}%"
    
    def _truncate(self, text: str, max_len: int = 100) -> str:
        if len(text) <= max_len:
            return text
        return text[:max_len-3] + "..."
