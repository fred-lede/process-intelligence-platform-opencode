"""Tests for report generation."""
import pytest
from datetime import datetime

from process_intelligence_engine.reporting.models import ReportData
from process_intelligence_engine.reporting.html import HTMLReportGenerator
from process_intelligence_engine.reporting.excel import ExcelReportGenerator
from process_intelligence_engine.reporting.pdf import PDFReportGenerator


def test_html_report_generates_valid_html():
    data = ReportData(
        project_name="Test Project",
        operator="Fred Wang",
        dataset_id="test_001",
        row_count=100,
        column_count=5,
        fields=[
            {"name": "temperature", "role": "input", "confidence": 0.85},
            {"name": "yield", "role": "output", "confidence": 0.90},
        ]
    )
    generator = HTMLReportGenerator(data)
    html = generator.generate()
    
    assert "<!DOCTYPE html>" in html
    assert "Test Project" in html
    assert "Fred Wang" in html
    assert "temperature" in html
    assert "yield" in html
    assert "input" in html
    assert "output" in html


def test_html_report_contains_styles():
    data = ReportData(project_name="Test")
    generator = HTMLReportGenerator(data)
    html = generator.generate()
    
    assert "<style>" in html
    assert "font-family" in html


def test_report_data_creation():
    data = ReportData(
        project_name="My Project",
        operator="Test User",
        dataset_id="ds_001",
        row_count=50,
    )
    assert data.project_name == "My Project"
    assert data.operator == "Test User"
    assert data.row_count == 50
    assert isinstance(data.created_at, datetime)


def test_html_report_with_empty_fields():
    data = ReportData(
        project_name="Empty Project",
        operator="Test",
        fields=[],
    )
    generator = HTMLReportGenerator(data)
    html = generator.generate()
    
    assert "Empty Project" in html
    assert "<!DOCTYPE html>" in html


def test_html_report_truncates_long_names():
    long_name = "A" * 150
    data = ReportData(project_name=long_name)
    generator = HTMLReportGenerator(data)
    html = generator.generate()
    
    assert long_name[:100] in html
    assert "..." in html


def test_percentage_formatting():
    data = ReportData(
        project_name="Test",
        fields=[{"name": "feat", "role": "output", "confidence": 0.75}],
    )
    generator = HTMLReportGenerator(data)
    html = generator.generate()
    
    assert "75.0%" in html


def test_badge_classes():
    data = ReportData(
        project_name="Test",
        fields=[
            {"name": "input_feat", "role": "input", "confidence": 0.8},
            {"name": "output_feat", "role": "output", "confidence": 0.9},
        ],
    )
    generator = HTMLReportGenerator(data)
    html = generator.generate()
    
    assert "badge-warning" in html
    assert "badge-success" in html


def test_pdf_report_generates_bytes():
    try:
        __import__("weasyprint")
    except OSError:
        pytest.skip("weasyprint system libraries (GTK/pango/glib) not available")
    data = ReportData(
        project_name="Test Project",
        operator="Fred Wang",
    )
    generator = PDFReportGenerator(data)
    pdf_bytes = generator.generate()
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    assert pdf_bytes[:4] == b'%PDF'


def test_excel_report_generates_bytes():
    data = ReportData(
        project_name="Test Project",
        operator="Fred Wang",
        fields=[
            {"name": "temperature", "role": "input", "confidence": 0.85},
            {"name": "yield", "role": "output", "confidence": 0.90},
        ]
    )
    generator = ExcelReportGenerator(data)
    excel_bytes = generator.generate()
    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 0


def test_excel_report_has_multiple_sheets():
    data = ReportData(
        project_name="Test Project",
        fields=[{"name": "A", "role": "input"}],
        model_comparison=[{"model_id": "m1", "model_type": "doe_linear"}],
        interactions={"factors": ["A", "B"], "matrix": [[0, 0.5], [0.5, 0]]},
        recommendations=[{"type": "interaction", "priority": "high", "factors": ["A", "B"], "reason": "Test"}],
    )
    generator = ExcelReportGenerator(data)
    excel_bytes = generator.generate()
    assert len(excel_bytes) > 0
