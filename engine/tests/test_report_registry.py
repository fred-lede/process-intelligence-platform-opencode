"""Tests for the report registry used by the Approval tab."""
from process_intelligence_engine.reporting.registry import _REPORT_REGISTRY as reg


def test_register_and_list_report():
    reg._clear()
    rid = reg.register(
        project_name="Proj A",
        operator="qa",
        output_format="html",
    )
    reports = reg.list()
    assert len(reports) == 1
    assert reports[0]["report_id"] == rid
    assert reports[0]["project_name"] == "Proj A"
    assert reports[0]["operator"] == "qa"
    assert reports[0]["format"] == "html"
    assert reports[0]["timestamp"]


def test_list_empty():
    reg._clear()
    assert reg.list() == []
