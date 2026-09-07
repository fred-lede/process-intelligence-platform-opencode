from process_intelligence_engine.project.manifest import ProjectManifest
from process_intelligence_engine.ai.contracts import AssistantRequest


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
