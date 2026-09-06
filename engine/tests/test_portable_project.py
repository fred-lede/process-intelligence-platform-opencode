"""Portable exports must not be treated as manifest directories."""
import json
from pathlib import Path

import pytest
from process_intelligence_engine import main as app
from process_intelligence_engine.project.manifest import ProjectEngine


@pytest.fixture(autouse=True)
def restore_session(monkeypatch):
    for name in ("PROJECT_ENGINE", "_VERSION_CHAIN", "GATE_MANAGER", "REGISTRY", "MODEL_REGISTRY"):
        monkeypatch.setattr(app, name, getattr(app, name))


def export_file(tmp_path, version=2, source="data.csv"):
    data = {"app": "process-intelligence-platform", "version": version,
            "import": {"file_path": source}, "fields": [],
            "spec": {"lsl": 0, "usl": 10}, "controlLimits": {"x": {"ucl": 3}},
            "anomalyScenarios": [], "quality": None, "analysisPackage": None}
    path = tmp_path / "process-project.piproj.json"
    path.write_text(json.dumps(data))
    return path, data


@pytest.mark.parametrize("version", [1, 2])
def test_open_export_without_manifest(tmp_path, version):
    (tmp_path / "data.csv").write_text("x,y\n1,2\n2,4\n")
    path, data = export_file(tmp_path, version)
    original = path.read_bytes()
    result = app.handle_request("project/open", {"root": str(path)})
    assert result["kind"] == "portable"
    assert result["project_file"] == data
    assert len(app.REGISTRY.get(result["import_result"]["dataset_id"])) == 2
    assert not (tmp_path / "project_manifest.json").exists()
    assert Path(result["project_root"]).is_dir()
    assert path.read_bytes() == original
    assert app.GATE_MANAGER.get_status("modeling") == "pending_confirmation"


def test_missing_source_keeps_current_session(tmp_path):
    path, _ = export_file(tmp_path)
    previous = app._VERSION_CHAIN
    with pytest.raises(FileNotFoundError, match="Original Excel/CSV not found"):
        app.handle_request("project/open", {"root": str(path)})
    assert app._VERSION_CHAIN is previous


def test_future_version_rejected(tmp_path):
    path, _ = export_file(tmp_path, 999)
    with pytest.raises(ValueError, match="Unsupported portable project version"):
        app.handle_request("project/open", {"root": str(path)})


def test_invalid_json_rejected(tmp_path):
    path, _ = export_file(tmp_path)
    path.write_text("not json")
    with pytest.raises(ValueError):
        app.handle_request("project/open", {"root": str(path)})


def test_manifest_file_and_directory_still_open(tmp_path, monkeypatch):
    engine = ProjectEngine()
    engine.create_project(str(tmp_path), "Directory project")
    monkeypatch.setattr(app, "PROJECT_ENGINE", engine)
    for path in (tmp_path, tmp_path / "project_manifest.json"):
        result = app.handle_request("project/open", {"root": str(path)})
        assert result["project_name"] == "Directory project"
