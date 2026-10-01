"""Base report generator."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

from .models import ReportData


def cell_value(value: Any) -> Any:
    """Coerce a report value into something a renderer can display as one cell.

    openpyxl accepts scalars only and raises "Cannot convert {0!r} to Excel" for
    anything else, which is how an empty ``input_ranges`` dict from the
    process-definition contract took down the whole Excel export. Rendering the
    same dict with str() in HTML produced "{'t': [170.0, 190.0]}" -- no crash, but
    unreadable. Both renderers share this conversion so they cannot drift apart.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return " – ".join("" if v is None else str(v) for v in value)
    if isinstance(value, dict):
        if not value:
            return ""
        return ", ".join(f"{k}={cell_value(v)}" for k, v in value.items())
    return str(value)


def flatten_rows(label: str, value: Any) -> list[tuple[str, Any]]:
    """Expand nested structures into (label, scalar) rows so content is kept, not dropped.

    ``input_ranges`` is a column -> [low, high] map, so it becomes one row per
    column instead of a single unreadable cell.
    """
    if isinstance(value, dict):
        rows: list[tuple[str, Any]] = []
        for key, sub in value.items():
            rows += flatten_rows(f"{label}.{key}" if label else str(key), sub)
        return rows
    return [(label, cell_value(value))]


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
