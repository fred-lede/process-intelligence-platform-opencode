"""PDF report generator."""
from __future__ import annotations
from typing import Any

from .base import ReportGenerator
from .models import ReportData


class PDFReportGenerator(ReportGenerator):
    """Generate PDF report from HTML."""

    def generate(self) -> bytes:
        """Generate PDF report as bytes."""
        try:
            from weasyprint import HTML
        except ImportError:
            raise ImportError(
                "weasyprint is required for PDF generation. "
                "Install with: pip install weasyprint"
            )

        try:
            html_content = self._generate_html()
            pdf_bytes = HTML(string=html_content).write_pdf()
            return pdf_bytes
        except OSError as exc:
            raise ImportError(
                f"PDF generation failed (system libraries missing): {exc}. "
                "Install required system libraries per https://doc.courtbouillon.org/"
            ) from exc

    def _generate_html(self) -> str:
        """Generate HTML content for PDF."""
        from .html import HTMLReportGenerator
        html_gen = HTMLReportGenerator(self.data)
        return html_gen.generate()

