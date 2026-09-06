"""Regression checks for project recovery and report-specific evidence."""
import pytest
from process_intelligence_engine import main as app
from process_intelligence_engine.versioning.chain import VersionChain
from process_intelligence_engine.gates.manager import GateManager
from process_intelligence_engine.approval.workflow import ApprovalWorkflow


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "_VERSION_CHAIN", VersionChain(str(tmp_path)))
    monkeypatch.setattr(app, "GATE_MANAGER", GateManager(str(tmp_path)))
    monkeypatch.setattr(app, "REGISTRY", app.DatasetRegistry())
    monkeypatch.setattr(app, "MODEL_REGISTRY", app.ModelRegistry())
    monkeypatch.setattr(app, "APPROVAL_WORKFLOW", ApprovalWorkflow())
    return tmp_path


def test_project_reload_recovers_chain_and_counter(isolated):
    chain = app._VERSION_CHAIN
    eid = chain.register_entity("dataset", "default", {"dataset_id": "a"})
    chain.add_claim(eid, "test", "evidence", [eid], "engineering_input")
    app._reload_chain_for_project(str(isolated))
    app._VERSION_CHAIN.load()  # Repeated load must not duplicate claims.
    assert len(app._VERSION_CHAIN.get_claims(eid)) == 1
    new = app._VERSION_CHAIN.register_entity("dataset", "default", {})
    assert app._VERSION_CHAIN.get_entity(new).version == 2


def test_legacy_counter_reconstructed_from_entities(isolated):
    chain = app._VERSION_CHAIN
    chain.register_entity("dataset", "default", {})
    (isolated / "registry/version_counters.json").write_text('{"dataset": 1}')
    chain.load()
    eid = chain.register_entity("dataset", "default", {})
    assert chain.get_entity(eid).version == 2


def test_same_version_different_entity_is_saved(isolated):
    gate = app.GATE_MANAGER
    gate.confirm("modeling", "a", 1, "reviewer")
    gate.confirm("modeling", "b", 1, "reviewer")
    assert gate.get_details("modeling")["entity_id"] == "b"
    assert GateManager(str(isolated)).get_details("modeling")["entity_id"] == "b"


def import_data(root, name):
    path = root / name
    path.write_text("x,y\n1,2\n2,4\n3,6\n")
    return app._handle_import({"file_path": str(path)})


def test_import_invalidates_previous_confirmations(isolated):
    app.GATE_MANAGER.confirm("modeling", "old", 1, "reviewer")
    import_data(isolated, "a.csv")
    assert app.GATE_MANAGER.get_status("modeling") == "pending_confirmation"


def test_report_excludes_other_dataset_claims_and_stays_draft(isolated):
    a = import_data(isolated, "a.csv")
    b = import_data(isolated, "b.csv")
    chain = app._VERSION_CHAIN
    for dto, text in ((a, "UNRELATED_EVIDENCE"), (b, "SELECTED_EVIDENCE")):
        chain.add_claim(dto["chain_entity_id"], "test", text, [], "engineering_input")
    for module in app.GATE_MANAGER.ALL_MODULES:
        app.GATE_MANAGER.confirm(module, b["chain_entity_id"], 2, "reviewer")
    result = app._handle_report_generate({"dataset_id": b["dataset_id"]})
    assert "SELECTED_EVIDENCE" in result["content"]
    assert "UNRELATED_EVIDENCE" not in result["content"]
    assert "DRAFT" in result["content"]
    assert "Approved by" not in result["content"]
    report = chain.get_entity(result["chain_entity_id"])
    assert report.parent_ids == [b["chain_entity_id"]]


def test_approval_requires_exact_version_and_explicit_review(isolated):
    dto = import_data(isolated, "a.csv")
    result = app._handle_report_generate({"dataset_id": dto["dataset_id"]})
    params = {"resource_type": "report", "resource_id": result["chain_entity_id"],
              "reviewer": "reviewer", "reviewer_role": "reviewer"}
    with pytest.raises(ValueError, match="confirmation"):
        app._handle_approval_approve(params)
    app.GATE_MANAGER.confirm("data_import", "wrong", 1, "reviewer")
    with pytest.raises(ValueError, match="confirmation"):
        app._handle_approval_approve(params)
    app.GATE_MANAGER.confirm("data_import", dto["chain_entity_id"], 1, "reviewer")
    with pytest.raises(ValueError, match="submitted"):
        app._handle_approval_approve(params)
    app._handle_approval_submit(params)
    assert app._handle_approval_approve(params)["new_status"] == "approved"


def test_open_another_project_does_not_include_previous_evidence(isolated):
    app._VERSION_CHAIN.register_entity("dataset", "default", {})
    app._reload_chain_for_project(str(isolated / "other"))
    assert app._VERSION_CHAIN.get_chain_summary() == []


def test_fit_and_simulation_invalidate_gates(isolated):
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(13)
    df = pd.DataFrame(rng.normal(size=(40, 3)), columns=["a", "b", "c"])
    df["y"] = df.a + df.b + rng.normal(size=40) * 0.1
    path = isolated / "model.csv"
    df.to_csv(path, index=False)
    dto = app._handle_import({"file_path": str(path)})
    app.GATE_MANAGER.confirm("modeling", "old", 1, "reviewer")
    fit = app._handle_modeling_fit({"dataset_id": dto["dataset_id"],
          "model_type": "doe_linear", "target": "y", "inputs": ["a", "b", "c"]})
    assert app.GATE_MANAGER.get_status("modeling") == "pending_confirmation"
    assert len(app._report_entities(dto["dataset_id"], [fit["model_id"]])) == 2
    app.GATE_MANAGER.confirm("monte_carlo", "old-sim", 1, "reviewer")
    app._handle_monte_carlo_run({"dataset_id": dto["dataset_id"],
                                "model_id": fit["model_id"], "n_simulations": 100})
    assert app.GATE_MANAGER.get_status("monte_carlo") == "pending_confirmation"
