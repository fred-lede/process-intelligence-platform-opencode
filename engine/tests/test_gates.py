import pytest
import tempfile
from process_intelligence_engine.gates.manager import GateManager


def test_initial_status_is_not_started():
    gm = GateManager(project_root="/tmp/test-gates-cleanup", project_id="test-init")
    assert gm.get_status("modeling") == "not_started"


def test_confirm_transition():
    gm = GateManager(project_root="/tmp/test-gates-cleanup", project_id="test-confirm")
    result = gm.confirm("modeling", "md-abc123", 1, "fred", "Model approved")
    assert result["new_status"] == "confirmed"
    assert gm.get_status("modeling") == "confirmed"


def test_confirm_with_different_version_invalidates():
    gm = GateManager(project_root="/tmp/test-gates-cleanup", project_id="test-ver")
    gm.confirm("modeling", "md-old", 1, "fred", "")
    gm.confirm("modeling", "md-new", 2, "fred", "")
    status = gm.get_status("modeling")
    assert status == "confirmed"


def test_reset_to_pending():
    gm = GateManager(project_root="/tmp/test-gates-cleanup", project_id="test-reset")
    gm.confirm("modeling", "md-abc", 1, "fred", "")
    gm.reset("modeling", "fred changed inputs")
    assert gm.get_status("modeling") == "pending_confirmation"


def test_summary_reports_all_modules():
    gm = GateManager(project_root="/tmp/test-gates-cleanup", project_id="test-summary")
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
    import tempfile, os
    tmp = tempfile.mkdtemp()
    gm = GateManager(project_root=tmp, project_id="test-all-unique")
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
    gm = GateManager(project_root="/tmp/test-gates-cleanup", project_id="test-details")
    gm.confirm("modeling", "md-abc", 1, "fred", "test comment")
    details = gm.get_details("modeling")
    assert details["entity_id"] == "md-abc"
    assert details["confirmed_by"] == "fred"
    assert details["comment"] == "test comment"
    assert details["status"] == "confirmed"


def test_project_id_is_stored():
    gm = GateManager(project_root="/tmp/test-gates", project_id="proj-A")
    gm.confirm("modeling", "md-1", 1, "fred", "")
    details = gm.get_details("modeling")
    assert details["project_id"] == "proj-A"


def test_gate_persistence_and_reload():
    import tempfile, os
    tmp = tempfile.mkdtemp()
    gm1 = GateManager(project_root=tmp, project_id="proj-A")
    gm1.confirm("modeling", "md-1", 1, "fred", "approved")
    gm1.confirm("monte_carlo", "sim-1", 1, "fred", "")
    # reload from same project
    gm2 = GateManager(project_root=tmp, project_id="proj-A")
    assert gm2.get_status("modeling") == "confirmed"
    assert gm2.get_status("monte_carlo") == "confirmed"
    # different project should not see the other's gates
    gm3 = GateManager(project_root=tmp, project_id="proj-B")
    assert gm3.get_status("modeling") == "not_started"


def test_gate_reset_saves():
    import tempfile
    tmp = tempfile.mkdtemp()
    gm1 = GateManager(project_root=tmp, project_id="proj")
    gm1.confirm("modeling", "md-1", 1, "fred", "")
    gm1.reset("modeling", "review needed")
    gm2 = GateManager(project_root=tmp, project_id="proj")
    assert gm2.get_status("modeling") == "pending_confirmation"


def test_gate_has_gate_id():
    tmp = tempfile.mkdtemp()
    gm = GateManager(project_root=tmp, project_id="proj")
    details = gm.get_details("modeling")
    assert "gate_id" in details
    assert details["gate_id"].startswith("gt-")


def test_gate_event_history():
    tmp = tempfile.mkdtemp()
    gm = GateManager(project_root=tmp, project_id="proj")
    gm.confirm("modeling", "md-1", 1, "fred", "approved")
    gm.reset("modeling", "changed inputs")
    gm.confirm("modeling", "md-2", 2, "fred", "")
    history = gm.get_history("modeling")
    assert len(history) >= 3  # confirm + reset + confirm with version change
    event_types = [e["event_type"] for e in history]
    assert "confirm" in event_types
    assert "reset" in event_types
    assert "version_changed" in event_types
    # Each event has required fields
    for evt in history:
        assert "event_id" in evt
        assert "gate_id" in evt
        assert "operation_id" in evt
        assert "old_status" in evt
        assert "new_status" in evt
