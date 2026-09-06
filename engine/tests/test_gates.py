import pytest
from process_intelligence_engine.gates.manager import GateManager


def test_initial_status_is_not_started():
    gm = GateManager()
    assert gm.get_status("modeling") == "not_started"


def test_confirm_transition():
    gm = GateManager()
    result = gm.confirm("modeling", "md-abc123", 1, "fred", "Model approved")
    assert result["new_status"] == "confirmed"
    assert gm.get_status("modeling") == "confirmed"


def test_confirm_with_different_version_invalidates():
    gm = GateManager()
    gm.confirm("modeling", "md-old", 1, "fred", "")
    gm.confirm("modeling", "md-new", 2, "fred", "")
    status = gm.get_status("modeling")
    assert status == "confirmed"


def test_reset_to_pending():
    gm = GateManager()
    gm.confirm("modeling", "md-abc", 1, "fred", "")
    gm.reset("modeling", "fred changed inputs")
    assert gm.get_status("modeling") == "pending_confirmation"


def test_summary_reports_all_modules():
    gm = GateManager()
    gm.confirm("modeling", "md-1", 1, "fred", "")
    gm.confirm("monte_carlo", "sim-1", 1, "fred", "")
    summary = gm.get_summary()
    assert summary["modeling"] == "confirmed"
    assert summary["monte_carlo"] == "confirmed"
    assert summary["data_import"] == "not_started"


def test_confirm_requires_entity_id():
    gm = GateManager()
    with pytest.raises(ValueError):
        gm.confirm("modeling", "", 1, "fred", "")


def test_are_all_confirmed():
    gm = GateManager()
    assert gm.are_all_confirmed() == False
    gm.confirm("data_import", "ds-1", 1, "fred", "")
    gm.confirm("process_define", "pd-1", 1, "fred", "")
    gm.confirm("modeling", "md-1", 1, "fred", "")
    gm.confirm("spc", "spc-1", 1, "fred", "")
    gm.confirm("monte_carlo", "sim-1", 1, "fred", "")
    gm.confirm("prediction", "pred-1", 1, "fred", "")
    gm.confirm("validation", "val-1", 1, "fred", "")
    assert gm.are_all_confirmed() == True


def test_get_details():
    gm = GateManager()
    gm.confirm("modeling", "md-abc", 1, "fred", "test comment")
    details = gm.get_details("modeling")
    assert details["entity_id"] == "md-abc"
    assert details["confirmed_by"] == "fred"
    assert details["comment"] == "test comment"
    assert details["status"] == "confirmed"
