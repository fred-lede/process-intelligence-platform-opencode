"""Report generation package."""
from .models import ReportData
from .html import HTMLReportGenerator

__all__ = ["ReportData", "HTMLReportGenerator"]
