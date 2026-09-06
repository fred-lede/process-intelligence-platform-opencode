"""Exercise the same IPC contracts used by the desktop, including restarts."""
import base64
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from process_intelligence_engine import main as app
from process_intelligence_engine.approval.workflow import ApprovalWorkflow
from process_intelligence_engine.reporting.registry import ReportRegistry
from process_intelligence_engine.project.manifest import ProjectEngine


@pytest.fixture
def project(tmp_path, monkeypatch):
    for name, value in {"REGISTRY": app.DatasetRegistry(), "MODEL_REGISTRY": app.ModelRegistry(),
                        "APPROVAL_WORKFLOW": ApprovalWorkflow(), "REPORT_REGISTRY": ReportRegistry(),
                        "PROJECT_ENGINE": ProjectEngine(), "EXPERIMENT_REGISTRY": app.ExperimentRegistry(),
                        "_VERSION_CHAIN": app._VERSION_CHAIN, "GATE_MANAGER": app.GATE_MANAGER}.items():
        monkeypatch.setattr(app, name, value)
    app.handle_request("project/create", {"root": str(tmp_path)})
    rng = np.random.default_rng(8)
    data = pd.DataFrame(rng.normal(size=(40, 3)), columns=["a", "b", "c"])
    data["y"] = 2 * data.a + data.b + rng.normal(size=40) * 0.1
    source = tmp_path / "source.csv"
    data.to_csv(source, index=False)
    imported = app.handle_request("data/import", {"file_path": str(source)})
    return tmp_path, imported


def test_governance_ipc_returns_and_fit_records_checks(project):
    _, data = project
    params = {"dataset_id": data["dataset_id"], "target": "y", "inputs": ["a", "b", "c"]}
    assert "warnings" in app.handle_request("modeling/governance/check", params)
    assert app.handle_request("modeling/governance/recommend", {"n_samples": 200, "is_binary_target": True})["recommendations"] == ["logistic_regression"]
    assert not app.handle_request("modeling/governance/doe_ai_compare", {"ai_pred": [1], "doe_pred": [1], "scale": 2})["needs_review"]
    fit = app.handle_request("modeling/governance/fit_with_check", {**params, "model_type": "doe_linear"})
    assert "governance_warnings" in fit


def test_report_review_export_and_reopen_golden_case(project):
    root, data = project
    fit = app.handle_request("modeling/fit", {"dataset_id": data["dataset_id"],
        "target": "y", "inputs": ["a", "b", "c"], "model_type": "doe_linear"})
    experiment = app.handle_request("experiment/record_with_verdict", {"model_id": fit["model_id"],
        "dataset_id": data["dataset_id"], "predicted_output": 2, "actual_output": 2.01, "tolerance": 0.2})
    assert experiment["verdict"] == "supports"
    claims = app._VERSION_CHAIN.get_claims(fit["chain_entity_id"])
    assert claims[0]["source_entity_ids"] == [experiment["chain_entity_id"]]
    result = app.handle_request("report/generate", {"dataset_id": data["dataset_id"],
        "model_ids": [fit["model_id"]], "n_simulations": 100, "format": "html"})
    report_id = app.handle_request("report/list", {})["reports"][0]["report_id"]
    assert report_id == result["chain_entity_id"]
    assert result["report_status"] == "draft"
    review = {"resource_type": "report", "resource_id": report_id, "reviewer": "qa", "reviewer_role": "reviewer"}
    app.handle_request("approval/submit", review)
    with pytest.raises(ValueError, match="confirmation"):
        app.handle_request("approval/approve", review)
    report = app._VERSION_CHAIN.get_entity(report_id)
    modules = {"dataset": "data_import", "model": "modeling", "simulation": "monte_carlo"}
    for eid in report.parent_ids:
        entity = app._VERSION_CHAIN.get_entity(eid)
        if entity.entity_type not in modules:
            continue
        app.handle_request("gates/confirm", {"module": modules[entity.entity_type], "entity_id": eid,
            "entity_version": entity.version, "confirmed_by": "engineer"})
    app.handle_request("approval/approve", review)
    exported = app.handle_request("report/export", {"report_id": report_id})
    assert "APPROVED" in exported["content"] and "Approved by qa" in exported["content"]
    binary = app.handle_request("report/export", {"report_id": report_id, "format": "excel"})
    assert base64.b64decode(binary["content_base64"]).startswith(b"PK")
    app.handle_request("project/open", {"root": str(root)})
    assert app.handle_request("report/export", {"report_id": report_id})["report_status"] == "approved"
    snapshot = root / "reports" / f"{report_id}.json"
    saved = json.loads(snapshot.read_text())
    saved["row_count"] = 999
    snapshot.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="checksum"):
        app.handle_request("report/export", {"report_id": report_id})


def test_anomaly_runtime_id_maps_to_chain_and_validates(project):
    _, data = project
    args = {"dataset_id": data["dataset_id"], "anomaly_id": "temperature", "source": "engineering_input",
            "confidence": 0.5, "user_confirmed": True, "operator": "engineer"}
    result = app.handle_request("analysis/anomaly/register", args)
    assert app._VERSION_CHAIN.get_entity(result["entity_id"]).parent_ids == [data["chain_entity_id"]]
    with pytest.raises(ValueError, match="Confidence"):
        app.handle_request("analysis/anomaly/register", {**args, "confidence": 2})


def test_gate_rejects_forged_version(project):
    _, data = project
    with pytest.raises(ValueError, match="version"):
        app.handle_request("gates/confirm", {"module": "data_import", "entity_id": data["chain_entity_id"],
            "entity_version": 999, "confirmed_by": "qa"})


def test_saved_session_reopens_without_original_source(project):
    root, data = project
    fit = app.handle_request("modeling/fit", {"dataset_id": data["dataset_id"],
        "target": "y", "inputs": ["a", "b", "c"], "model_type": "doe_linear"})
    destination = root.parent / f"{root.name}-saved"
    state = {"app": "process-intelligence-platform", "version": 2}
    app.handle_request("project/save_session", {"root": str(destination), "project_file": state})
    (root / "source.csv").unlink()
    reopened = app.handle_request("project/open", {"root": str(destination)})
    assert reopened["import_result"]["dataset_id"] == data["dataset_id"]
    assert reopened["project_file"] == state
    assert reopened["models_rebuilt"] == 1
    assert app.MODEL_REGISTRY.get(fit["model_id"]).version == fit["version"]
    assert len(app.REGISTRY.get(data["dataset_id"])) == 40


def test_failed_open_preserves_active_project(project):
    root, data = project
    destination = root.parent / f"{root.name}-corrupt"
    app.handle_request("project/save_session", {"root": str(destination), "project_file": {}})
    (destination / "registry" / "ui_state.json").write_text("invalid json")
    previous = (app.PROJECT_ENGINE, app.REGISTRY, app._VERSION_CHAIN, app.GATE_MANAGER)
    with pytest.raises(ValueError):
        app.handle_request("project/open", {"root": str(destination)})
    assert (app.PROJECT_ENGINE, app.REGISTRY, app._VERSION_CHAIN, app.GATE_MANAGER) == previous
    assert app.PROJECT_ENGINE._root == root
    assert len(app.REGISTRY.get(data["dataset_id"])) == 40


def test_failed_portable_import_preserves_review_state(project):
    root, _ = project
    source = root / "empty.xlsx"
    source.write_text("")
    portable = root / "broken.piproj.json"
    portable.write_text(json.dumps({"app": "process-intelligence-platform", "version": 2,
                                     "import": {"file_path": str(source)}}))
    previous = (app.EXPERIMENT_REGISTRY, app.APPROVAL_WORKFLOW, app.REPORT_REGISTRY)
    with pytest.raises(Exception):
        app.handle_request("project/open", {"root": str(portable)})
    assert (app.EXPERIMENT_REGISTRY, app.APPROVAL_WORKFLOW, app.REPORT_REGISTRY) == previous
