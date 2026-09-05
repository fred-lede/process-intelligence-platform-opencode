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


def test_control_chart_svg():
    """Test I-MR control chart SVG generation."""
    from process_intelligence_engine.reporting.charting import control_chart_svg
    svg = control_chart_svg(
        x_values=[10.0, 11.0, 9.0, 10.5, 11.2],
        mr_values=[None, 1.0, 2.0, 1.5, 0.7],
        x_ucl=12.0, x_lcl=8.0, x_cl=10.0,
        mr_ucl=3.0, mr_cl=1.2,
    )
    assert "<svg" in svg
    assert "I-MR" in svg
    assert "UCL" in svg
    assert "LCL" in svg


def test_render_spc_section():
    """Test SPC section rendering in HTML report."""
    from process_intelligence_engine.reporting.html import HTMLReportGenerator
    from process_intelligence_engine.reporting.models import ReportData
    from datetime import datetime

    data = ReportData(
        project_name="Test",
        operator="Test",
        created_at=datetime.now(),
        row_count=100,
        column_count=3,
        spc_results=[{
            "column": "thickness",
            "x_values": [10.0, 11.0, 9.0, 10.5],
            "mr_values": [None, 1.0, 2.0, 1.5],
            "x_ucl": 12.0, "x_lcl": 8.0, "x_mean": 10.0,
            "mr_ucl": 3.0, "mr_mean": 1.2,
            "violations": 0,
            "capability": {"cp": 1.5, "cpk": 1.2, "pp": 1.4, "ppk": 1.1},
            "suggestions": [{"severity": "warning", "type": "marginal", "message": "Test suggestion"}],
        }],
    )
    gen = HTMLReportGenerator(data)
    html = gen.generate()
    assert "SPC: thickness" in html
    assert "<svg" in html
    assert "1.5" in html  # Cp value
