import json
from dataclasses import replace

import pytest

from process_intelligence_engine.ai.contracts import AssistantRequest
from process_intelligence_engine.project.manifest import ProjectManifest
from process_intelligence_engine.settings import AIProviderConfig


def valid_response(**changes):
    value = {
        "explanation": "Review the fit before planning an experiment.",
        "evidence_ids": ["model-a"],
        "evidence_status": "statistically_supported",
        "recommendations": ["Run a targeted validation experiment."],
        "action_draft": None,
        "limitations": ["Correlation does not establish causality."],
    }
    value.update(changes)
    return json.dumps(value)


class LocalModel:
    healthy = True
    failure = None

    def __init__(self):
        self.response = valid_response()
        self.messages = []

    async def health_check(self):
        return self.healthy

    async def chat(self, messages):
        if self.failure:
            raise self.failure
        self.messages.append(messages)
        return self.response


@pytest.fixture
def project(tmp_path):
    manifest = ProjectManifest.create(tmp_path, "test-project")
    manifest.save()
    return manifest


@pytest.fixture
def local_model():
    return LocalModel()


@pytest.fixture
def orchestrator(project, local_model):
    from process_intelligence_engine.ai.orchestrator import AssistantOrchestrator

    return AssistantOrchestrator(project.project_root, AIProviderConfig(), local_model)


def request(project, provider="ollama"):
    return AssistantRequest(
        message="Explain the fit",
        project_id=project.project_id,
        page="modelCenter",
        provider=provider,
        context={
            "project_id": project.project_id,
            "page_summary": {"model_summary": {"operator": "Ada", "temperature": 150.2}},
            "evidence": [{"entity_id": "model-a", "entity_type": "model",
                          "project_id": project.project_id, "version": 1,
                          "evidence_status": "statistically_supported"}],
        },
    )


def enable_cloud(orchestrator):
    orchestrator.config.provider = "openai"
    orchestrator.config.base_url = "https://provider.example/v1"
    orchestrator.config.model = "cloud-model"
    orchestrator.config.cloud_enabled = True


def consent(orchestrator, project, cloud_request):
    preview = orchestrator.preview_cloud(cloud_request)
    orchestrator.grant_project_cloud_consent(project.project_root, preview.payload_hash)
    cloud_request.context["preview_hash"] = preview.payload_hash
    return preview


@pytest.mark.parametrize("failure", ["unhealthy", "request"])
def test_unavailable_ollama_never_falls_back_to_cloud(orchestrator, project, local_model, failure):
    enable_cloud(orchestrator)
    if failure == "unhealthy":
        local_model.healthy = False
    else:
        local_model.failure = ConnectionError("secret upstream details")
    result = orchestrator.respond(request(project))
    assert result.error_code == "local_model_unavailable"
    assert result.provider is None
    assert not result.success
    assert "secret upstream details" not in json.dumps(result.to_dict())


def test_cloud_requires_explicit_enablement(orchestrator, project):
    orchestrator.config.provider = "openai"
    with pytest.raises(PermissionError, match="Cloud assistant provider is not enabled"):
        orchestrator.respond(request(project, "openai"))


def test_cloud_requires_project_consent(orchestrator, project):
    enable_cloud(orchestrator)
    with pytest.raises(PermissionError, match="Cloud assistant use requires project consent"):
        orchestrator.respond(request(project, "openai"))


def test_cloud_requires_request_preview_hash(orchestrator, project):
    enable_cloud(orchestrator)
    cloud_request = request(project, "openai")
    consent(orchestrator, project, cloud_request)
    cloud_request.context.pop("preview_hash")
    with pytest.raises(PermissionError, match="current preview"):
        orchestrator.respond(cloud_request)


def test_consent_rejects_hash_without_preview(orchestrator, project):
    with pytest.raises(PermissionError, match="current preview"):
        orchestrator.grant_project_cloud_consent(project.project_root, "invented")
    assert ProjectManifest.load(project.project_root).assistant_policy["cloud_consent"] is False


@pytest.mark.parametrize("change", ["message", "context", "model", "base_url", "rules"])
def test_changed_request_or_policy_invalidates_preview(orchestrator, project, change):
    enable_cloud(orchestrator)
    cloud_request = request(project, "openai")
    consent(orchestrator, project, cloud_request)
    if change == "message":
        cloud_request.message = "Generate a report"
    elif change == "context":
        cloud_request.context["page_summary"]["selected_model_id"] = "model-b"
    elif change == "rules":
        manifest = ProjectManifest.load(project.project_root)
        manifest.assistant_policy["sanitization_rules"] = {"message": "mask"}
        manifest.save()
    else:
        setattr(orchestrator.config, change, "changed")
    with pytest.raises(PermissionError, match="current preview"):
        orchestrator.respond(cloud_request)


def test_consent_persists_but_other_projects_cannot_use_it(orchestrator, project, tmp_path):
    enable_cloud(orchestrator)
    cloud_request = request(project, "openai")
    preview = consent(orchestrator, project, cloud_request)
    saved = ProjectManifest.load(project.project_root).assistant_policy
    assert saved["cloud_consent"] is True
    assert saved["preview_hash"] == preview.payload_hash
    assert saved["consented_at"]
    other = ProjectManifest.create(tmp_path / "other", "other")
    other.save()
    with pytest.raises(PermissionError, match="project"):
        orchestrator.grant_project_cloud_consent(other.project_root, preview.payload_hash)
    with pytest.raises(PermissionError, match="project"):
        orchestrator.respond(replace(cloud_request, project_id=other.project_id))


def test_revoked_consent_blocks_cloud(orchestrator, project):
    enable_cloud(orchestrator)
    cloud_request = request(project, "openai")
    consent(orchestrator, project, cloud_request)
    saved = ProjectManifest.load(project.project_root)
    saved.assistant_policy["cloud_consent"] = False
    saved.save()
    with pytest.raises(PermissionError, match="project consent"):
        orchestrator.respond(cloud_request)


def test_cloud_sends_exact_preview_with_identifiers_masked(orchestrator, project, monkeypatch):
    enable_cloud(orchestrator)
    cloud_request = request(project, "openai")
    preview = consent(orchestrator, project, cloud_request)
    outgoing = []

    async def transport(payload):
        outgoing.append(payload)
        return valid_response()

    monkeypatch.setattr(orchestrator, "_cloud_chat", transport)
    result = orchestrator.respond(cloud_request)
    assert result.success and result.provider == "openai"
    assert outgoing == [preview.payload]
    wire = json.dumps(outgoing[0])
    assert "Ada" not in wire and "MASKED" in wire and "150.2" in wire
    assert "preview_hash" not in wire


def test_local_response_resolves_evidence_from_context(orchestrator, project):
    result = orchestrator.respond(request(project))
    assert result.success and result.provider == "ollama"
    assert result.evidence[0].evidence_id == "model-a"
    assert result.evidence[0].status == "statistically_supported"
    assert result.evidence_status == "statistically_supported"


@pytest.mark.parametrize("content", ["plain text", "[]", "{}", "null", valid_response(recommendations="wrong")])
def test_invalid_structured_response_returns_error(orchestrator, project, local_model, content):
    local_model.response = content
    result = orchestrator.respond(request(project))
    assert result.error_code == "invalid_assistant_response"
    assert not result.success


@pytest.mark.parametrize("evidence_ids", [[], ["invented"]])
def test_unsupported_claim_cannot_claim_confirmed_status(orchestrator, project, local_model, evidence_ids):
    local_model.response = valid_response(evidence_ids=evidence_ids, evidence_status="confirmed")
    result = orchestrator.respond(request(project))
    assert result.success
    assert result.evidence_status in {"unverified", "ai_guess"}
    assert result.evidence == []


def test_model_cannot_promote_context_evidence_status(orchestrator, project, local_model):
    local_model.response = valid_response(evidence_status="confirmed")
    result = orchestrator.respond(request(project))
    assert result.evidence_status == "statistically_supported"


def draft(method, params):
    return {"method": method, "params": params, "impact": "Creates a new artifact",
            "expected_result": "A reviewable draft"}


def test_disallowed_action_is_rejected(orchestrator, project, local_model):
    local_model.response = valid_response(action_draft=draft("project/delete", {}))
    with pytest.raises(ValueError, match="Assistant action is not allowed"):
        orchestrator.respond(request(project))


@pytest.mark.parametrize("method,params", [
    ("modeling/fit", {"dataset_id": "data-a", "model_type": "doe", "target": "yield", "inputs": ["temperature"]}),
    ("validation/experiment/create", {"model_id": "model-a", "conditions": {"temperature": 150.2}}),
    ("report/generate", {"dataset_id": "data-a"}),
])
def test_allowed_drafts_are_validated_without_execution(orchestrator, project, local_model, method, params):
    before = ProjectManifest.load(project.project_root).to_dict()
    local_model.response = valid_response(action_draft=draft(method, params))
    result = orchestrator.respond(request(project))
    assert result.success
    assert result.action_draft.method == method
    assert result.action_draft.params == params
    assert result.action_draft.draft_id
    assert ProjectManifest.load(project.project_root).to_dict() == before


@pytest.mark.parametrize("method,params", [
    ("modeling/fit", {}),
    ("modeling/fit", {"dataset_id": "d", "model_type": "doe", "target": "y", "inputs": "x"}),
    ("validation/experiment/create", {"model_id": "m"}),
    ("validation/experiment/create", {"model_id": "m", "conditions": []}),
    ("report/generate", {"dataset_id": ""}),
    ("report/generate", {"dataset_id": "d", "format": "executable"}),
])
def test_invalid_action_params_are_rejected(orchestrator, project, local_model, method, params):
    local_model.response = valid_response(action_draft=draft(method, params))
    with pytest.raises(ValueError, match="Invalid assistant action parameters"):
        orchestrator.respond(request(project))


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_non_json_numeric_constants_are_rejected(orchestrator, project, local_model, constant):
    local_model.response = valid_response().replace('"action_draft": null', f'"unexpected": {constant}, "action_draft": null')
    result = orchestrator.respond(request(project))
    assert not result.success
    assert result.error_code == "invalid_assistant_response"


def test_grant_rechecks_preview_after_configuration_change(orchestrator, project):
    enable_cloud(orchestrator)
    preview = orchestrator.preview_cloud(request(project, "openai"))
    orchestrator.config.model = "another-model"
    with pytest.raises(PermissionError, match="current preview"):
        orchestrator.grant_project_cloud_consent(project.project_root, preview.payload_hash)
    assert ProjectManifest.load(project.project_root).assistant_policy["cloud_consent"] is False
