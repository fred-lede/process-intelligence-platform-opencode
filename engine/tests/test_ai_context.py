import pytest

from process_intelligence_engine.project.manifest import ProjectManifest
from process_intelligence_engine.ai.contracts import AssistantRequest
from process_intelligence_engine.ai.context import build_assistant_context
from process_intelligence_engine.versioning.chain import VersionChain


@pytest.fixture
def chain(tmp_path):
    version_chain = VersionChain(str(tmp_path), "test-user")
    version_chain.register_entity("model", "project-a", {"model_type": "doe"})
    version_chain.register_entity("model", "project-b", {"model_type": "random_forest"})
    return version_chain


def test_assistant_policy_round_trips_without_sensitive_values(tmp_path):
    manifest = ProjectManifest.create(tmp_path, "demo")
    manifest.assistant_policy = {
        "cloud_consent": True,
        "sanitization_rules": {"operator": "mask"},
        "consented_at": "2026-09-08T00:00:00+00:00",
    }
    manifest.save()
    assert ProjectManifest.load(tmp_path).assistant_policy["cloud_consent"] is True


def test_assistant_request_defaults_to_ollama_provider():
    request = AssistantRequest(message="Explain", project_id="demo", page="overview")
    assert request.provider == "ollama"


def test_context_excludes_another_project(chain):
    context = build_assistant_context(
        "project-a", "modelCenter", {"selected_model_id": "md-a"}, chain
    )
    assert context["page_summary"] == {"selected_model_id": "md-a"}
    assert all(item["project_id"] == "project-a" for item in context["evidence"])


def test_context_marks_missing_evidence_unverified(tmp_path):
    chain = VersionChain(str(tmp_path), "test-user")
    context = build_assistant_context("project-a", "report", {}, chain)
    assert context["evidence_status"] == "unverified"


def test_context_rejects_raw_rows_and_oversized_summaries(chain):
    with pytest.raises(ValueError, match="Assistant context exceeds the local summary limit"):
        build_assistant_context(
            "project-a", "dataImport", {"raw_rows": [[1, 2]]}, chain
        )

    with pytest.raises(ValueError, match="Assistant context exceeds the local summary limit"):
        build_assistant_context(
            "project-a",
            "modelCenter",
            {"selected_model_id": "x" * (33 * 1024)},
            chain,
        )


def test_context_rejects_dataframe_under_allowed_summary_key(chain):
    pandas = pytest.importorskip("pandas")
    with pytest.raises(ValueError, match="Assistant context exceeds the local summary limit"):
        build_assistant_context(
            "project-a",
            "dataImport",
            {"dataset_summary": pandas.DataFrame({"temperature": [150.2]})},
            chain,
        )


def test_context_rejects_nested_tabular_values_under_allowed_summary_key(chain):
    with pytest.raises(ValueError, match="Assistant context exceeds the local summary limit"):
        build_assistant_context(
            "project-a",
            "dataImport",
            {"dataset_summary": [["temperature", "pressure"], [150.2, 5.1]]},
            chain,
        )
