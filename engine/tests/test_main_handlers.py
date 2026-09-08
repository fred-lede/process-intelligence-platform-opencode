"""Test the engine method handlers directly (dispatch layer)."""

import json

import pytest

from types import SimpleNamespace

from process_intelligence_engine.main import handle_request, REGISTRY
from process_intelligence_engine.reporting.registry import _REPORT_REGISTRY


@pytest.fixture
def assistant_project(tmp_path, monkeypatch):
    from process_intelligence_engine import main as app
    from process_intelligence_engine.ai.ollama_client import OllamaClient
    from process_intelligence_engine.ai.orchestrator import AssistantOrchestrator
    from process_intelligence_engine.settings import AIProviderConfig

    for name in ("PROJECT_ENGINE", "_VERSION_CHAIN", "GATE_MANAGER", "REGISTRY",
                 "MODEL_REGISTRY", "EXPERIMENT_REGISTRY", "APPROVAL_WORKFLOW", "REPORT_REGISTRY"):
        monkeypatch.setattr(app, name, getattr(app, name))
    monkeypatch.setattr(app, "PROJECT_ENGINE", app.ProjectEngine())
    monkeypatch.setattr(app, "AUTH_MANAGER", app.AuthManager())
    monkeypatch.setattr(app, "_ASSISTANT_STATE", None, raising=False)
    config = AIProviderConfig(enabled=True)
    monkeypatch.setattr(app, "get_settings_manager", lambda: SimpleNamespace(_config=config))
    state = SimpleNamespace(app=app, root=tmp_path / "a", config=config, messages=[],
                            output={"explanation": "Review this evidence", "evidence_ids": [],
                                    "evidence_status": "confirmed", "recommendations": [],
                                    "action_draft": None, "limitations": []})

    async def health(self):
        return True

    async def chat(self, messages):
        state.messages.append(messages)
        return json.dumps(state.output)

    async def cloud_chat(self, payload):
        state.messages.append(payload["messages"])
        return json.dumps(state.output)

    monkeypatch.setattr(OllamaClient, "health_check", health)
    monkeypatch.setattr(OllamaClient, "chat", chat)
    monkeypatch.setattr(AssistantOrchestrator, "_cloud_chat", cloud_chat)
    state.project = handle_request("project/create", {"root": str(state.root)})
    state.project_id = app.PROJECT_ENGINE.get_manifest()["project_id"]
    return state


def _assistant_request(state, **updates):
    return {"message": "Explain the analysis", "project_id": state.project_id,
            "page": "modeling", **updates}


def _assistant_dataset(state):
    path = state.root / "sample.csv"
    path.write_text("x,y\n1,2\n2,4\n3,6\n4,8\n5,10\n6,12\n7,14\n8,16\n9,18\n10,20\n")
    return handle_request("data/import", {"file_path": str(path)})


def _assistant_draft(state, method, params):
    state.output["action_draft"] = {"method": method, "params": params,
        "impact": "Creates a new draft artifact", "expected_result": "Reviewable result"}
    result = handle_request("assistant/respond", _assistant_request(state))
    assert result["success"] is True
    return result["action_draft"]


@pytest.mark.parametrize("confirmed", [None, False, 1, "true"])
def test_assistant_execute_requires_literal_confirmation(assistant_project, confirmed):
    result = handle_request("assistant/draft/execute", {"draft_id": "invented", "confirmed": confirmed})
    assert result["error_code"] == "confirmation_required"


def test_assistant_unknown_draft_is_rejected(assistant_project):
    result = handle_request("assistant/draft/execute", {"draft_id": "invented", "confirmed": True,
        "method": "report/generate", "params": {"dataset_id": "invented"}})
    assert result["error_code"] == "draft_not_found"


def test_assistant_context_uses_server_evidence_and_summary(assistant_project):
    s = assistant_project
    dataset = _assistant_dataset(s)
    eid = dataset["chain_entity_id"]
    foreign = s.app._VERSION_CHAIN.register_entity("dataset", "other-project", {})
    s.output["evidence_ids"] = [eid]
    result = handle_request("assistant/respond", _assistant_request(s, context={
        "project_id": "spoofed", "evidence": [{"entity_id": eid, "evidence_status": "confirmed"}],
        "page_summary": {"selected_dataset_id": dataset["dataset_id"],
                         "dataset_summary": {"row_count": 999}, "evidence_status": "confirmed"}}))
    sent = json.loads(s.messages[-1][-1]["content"])["context"]
    assert sent["project_id"] == s.project_id
    assert [e["entity_id"] for e in sent["evidence"]] == [eid]
    assert foreign not in json.dumps(sent)
    assert sent["page_summary"]["dataset_summary"]["row_count"] == 10
    assert "source_file" not in json.dumps(sent)
    assert result["evidence_status"] == "unverified"


def test_assistant_rejects_other_project_request(assistant_project):
    with pytest.raises(PermissionError):
        handle_request("assistant/respond", _assistant_request(assistant_project, project_id="other"))


def test_assistant_draft_is_inert_server_owned_and_consumed_once(assistant_project):
    s = assistant_project
    dataset = _assistant_dataset(s)
    draft = _assistant_draft(s, "modeling/fit", {"dataset_id": dataset["dataset_id"],
        "model_type": "doe_linear", "target": "y", "inputs": ["x"]})
    assert s.app.MODEL_REGISTRY.list_ids() == []
    draft["params"]["dataset_id"] = "tampered"
    result = handle_request("assistant/draft/execute", {"draft_id": draft["draft_id"],
        "confirmed": True, "params": {"dataset_id": "also-tampered"}})
    assert result["model_id"] in s.app.MODEL_REGISTRY.list_ids()
    assert handle_request("assistant/draft/execute", {"draft_id": draft["draft_id"],
        "confirmed": True})["error_code"] == "draft_not_found"
    events = [e for e in handle_request("audit/log", {})["log"]
              if e["target"] == "assistant_draft_confirmed"]
    assert len(events) == 1
    assert events[0]["details"]["draft_id"] == draft["draft_id"]
    assert events[0]["details"]["project_id"] == s.project_id


def test_assistant_failed_execution_keeps_draft_for_retry(assistant_project):
    s = assistant_project
    draft = _assistant_draft(s, "report/generate", {"dataset_id": "missing"})
    for _ in range(2):
        with pytest.raises(KeyError):
            handle_request("assistant/draft/execute", {"draft_id": draft["draft_id"], "confirmed": True})
    assert not any(e["target"] == "assistant_draft_confirmed" for e in handle_request("audit/log", {})["log"])


def test_assistant_project_switch_invalidates_drafts(assistant_project):
    s = assistant_project
    draft = _assistant_draft(s, "report/generate", {"dataset_id": "missing"})
    handle_request("project/create", {"root": str(s.root.parent / "b")})
    assert handle_request("assistant/draft/execute", {"draft_id": draft["draft_id"],
        "confirmed": True})["error_code"] == "draft_not_found"
    handle_request("project/open", {"root": str(s.root)})
    assert handle_request("assistant/draft/execute", {"draft_id": draft["draft_id"],
        "confirmed": True})["error_code"] == "draft_not_found"


@pytest.mark.parametrize("method", ["settings/update", "experiment/record", "cloud/upload"])
def test_assistant_disallowed_actions_never_become_executable(assistant_project, method):
    with pytest.raises(ValueError, match="not allowed"):
        _assistant_draft(assistant_project, method, {})


def test_assistant_confirmed_experiment_creates_persisted_plan_only(assistant_project):
    s = assistant_project
    dataset = _assistant_dataset(s)
    fit = handle_request("modeling/fit", {"dataset_id": dataset["dataset_id"],
        "model_type": "doe_linear", "target": "y", "inputs": ["x"]})
    draft = _assistant_draft(s, "validation/experiment/create", {
        "model_id": fit["model_id"], "conditions": {"x": 4.5}})
    result = handle_request("assistant/draft/execute", {"draft_id": draft["draft_id"], "confirmed": True})
    assert result["status"] == "planned"
    entity = s.app._VERSION_CHAIN.get_entity(result["chain_entity_id"])
    assert entity.metadata["conditions"] == {"x": 4.5}
    assert entity.parent_ids == [fit["chain_entity_id"]]
    assert entity.evidence_status == "unverified"
    assert "actual_output" not in entity.metadata
    assert handle_request("experiment/list", {})["experiments"] == []
    handle_request("project/open", {"root": str(s.root)})
    assert s.app._VERSION_CHAIN.get_entity(result["chain_entity_id"]).metadata["status"] == "planned"


def test_assistant_cloud_consent_requires_preview_and_confirmation(assistant_project):
    s = assistant_project
    result = handle_request("assistant/cloud_consent", {"preview_hash": "abc", "confirmed": False})
    assert result["error_code"] == "confirmation_required"
    with pytest.raises(PermissionError):
        handle_request("assistant/cloud_consent", {"preview_hash": "abc", "confirmed": True})


def test_assistant_cloud_consent_persisted_and_exact_preview_sent(assistant_project):
    from process_intelligence_engine.project.manifest import ProjectManifest
    s = assistant_project
    s.config.provider, s.config.cloud_enabled = "openai", True
    s.config.model = "test-cloud"
    request = _assistant_request(s, provider="openai")
    preview = handle_request("assistant/cloud_preview", request)
    assert s.messages == []
    result = handle_request("assistant/cloud_consent", {"preview_hash": preview["payload_hash"], "confirmed": True})
    assert result["cloud_consent"] is True
    assert ProjectManifest.load(s.root).assistant_policy["preview_hash"] == preview["payload_hash"]
    response = handle_request("assistant/respond", {**request, "context": {"preview_hash": preview["payload_hash"]}})
    assert response["success"] is True
    assert s.messages[-1] == preview["payload"]["messages"]
    manifest = ProjectManifest.load(s.root)
    manifest.assistant_policy["cloud_consent"] = False
    manifest.save()
    with pytest.raises(PermissionError):
        handle_request("assistant/respond", {**request, "context": {"preview_hash": preview["payload_hash"]}})


def test_assistant_cloud_preview_invalid_after_project_switch(assistant_project):
    s = assistant_project
    s.config.provider, s.config.cloud_enabled = "openai", True
    preview = handle_request("assistant/cloud_preview", _assistant_request(s, provider="openai"))
    handle_request("project/create", {"root": str(s.root.parent / "b")})
    with pytest.raises(PermissionError):
        handle_request("assistant/cloud_consent", {"preview_hash": preview["payload_hash"], "confirmed": True})


def test_assistant_cloud_send_rebuilds_changed_server_context(assistant_project):
    s = assistant_project
    s.config.provider, s.config.cloud_enabled = "openai", True
    request = _assistant_request(s, provider="openai")
    preview = handle_request("assistant/cloud_preview", request)
    handle_request("assistant/cloud_consent", {"preview_hash": preview["payload_hash"], "confirmed": True})
    _assistant_dataset(s)
    with pytest.raises(PermissionError):
        handle_request("assistant/respond", {**request, "context": {"preview_hash": preview["payload_hash"]}})
    assert s.messages == []


def test_assistant_cloud_consent_survives_project_settings_save(assistant_project):
    from process_intelligence_engine.project.manifest import ProjectManifest
    s = assistant_project
    s.config.provider, s.config.cloud_enabled = "openai", True
    preview = handle_request("assistant/cloud_preview", _assistant_request(s, provider="openai"))
    handle_request("assistant/cloud_consent", {"preview_hash": preview["payload_hash"], "confirmed": True})
    handle_request("project/settings", {"updates": {"theme": "dark"}})
    assert ProjectManifest.load(s.root).assistant_policy["cloud_consent"] is True


def test_assistant_cloud_consent_rejects_changed_server_evidence(assistant_project):
    from process_intelligence_engine.project.manifest import ProjectManifest
    s = assistant_project
    s.config.provider, s.config.cloud_enabled = "openai", True
    preview = handle_request("assistant/cloud_preview", _assistant_request(s, provider="openai"))
    _assistant_dataset(s)
    with pytest.raises(PermissionError):
        handle_request("assistant/cloud_consent", {"preview_hash": preview["payload_hash"], "confirmed": True})
    assert ProjectManifest.load(s.root).assistant_policy["cloud_consent"] is False


def _detect_fields_payload():
    return {
        "columns": [
            {"name": "barcode", "values": ["A1", "B2", "C3"]},
            {"name": "temperature", "values": ["230.5", "241.0", "255.2"]},
            {"name": "ok_flag", "values": ["OK", "NG", "OK"]},
        ]
    }


def test_handle_detect_fields_returns_roles():
    result = handle_request("data/detect_fields", _detect_fields_payload())

    assert result["fields"][0]["role"] == "identifier"
    assert result["fields"][1]["role"] == "input"
    assert result["fields"][2]["role"] == "quality_label"
    assert all("reason" in f and f["reason"] for f in result["fields"])


def test_handle_import_unknown_file_raises_propagated():
    with pytest.raises(FileNotFoundError):
        handle_request("data/import", {"file_path": "/nope/nope.csv"})


def _import_csv_and_return_id(tmp_path, csv_text: str) -> str:
    path = tmp_path / "sample.csv"
    path.write_text(csv_text, encoding="utf-8")
    result = handle_request("data/import", {"file_path": str(path)})
    return result["dataset_id"]


def test_handle_quality_returns_issues(tmp_path):
    csv_text = "\n".join(
        [
            "temp,flag",
            "1.0,OK",
            "2.0,OK",
            "3.0,NG",
            "4.0,OK",
            ",OK",
        ]
    )
    dataset_id = _import_csv_and_return_id(tmp_path, csv_text)

    result = handle_request(
        "data/quality",
        {
            "dataset_id": dataset_id,
            "quality_columns": ["flag"],
            "categorical_columns": ["flag"],
        },
    )

    codes = {i["check"] for i in result["issues"]}
    assert "missing_value" in codes
    assert "unbalanced_okng" in codes


def test_handle_quality_unknown_dataset_raises():
    with pytest.raises(KeyError):
        handle_request(
            "data/quality",
            {"dataset_id": "does-not-exist", "categorical_columns": []},
        )


def test_handle_distribution_returns_fits(tmp_path):
    csv_text = "\n".join(
        [
            "value",
            "254.0",
            "254.5",
            "255.0",
            "255.5",
            "256.0",
            "254.2",
            "255.3",
            "251.0",
            "258.0",
            "257.0",
            "252.0",
            "253.0",
        ]
    )
    dataset_id = _import_csv_and_return_id(tmp_path, csv_text)

    result = handle_request(
        "data/distribution",
        {"dataset_id": dataset_id, "column": "value", "top_n": 3},
    )

    assert len(result["fits"]) >= 1
    assert isinstance(result["fits"][0]["params"], dict)
    assert result["fits"][0]["name"]


def test_handle_distribution_values_payload_still_supported():
    result = handle_request(
        "data/distribution",
        {"values": [254.0, 254.5, 255.0, 255.5, 256.0, 254.2, 255.3, 251.0, 258.0, 257.0, 252.0, 253.0], "top_n": 3},
    )

    assert len(result["fits"]) >= 1
    assert isinstance(result["fits"][0]["params"], dict)
    assert result["fits"][0]["name"]


def _import_csv_for_explore_filter(tmp_path):
    import numpy as np
    rng = np.random.default_rng(11)
    rows = ["work_order,value"]
    for i in range(60):
        group = "A" if i < 30 else "B"
        base = 50.0 if group == "A" else 150.0
        val = base + rng.normal(0, 1.5)
        rows.append(f"{group},{val:.2f}")
    path = tmp_path / "explore_filter.csv"
    path.write_text("\n".join(rows), encoding="utf-8")
    return handle_request("data/import", {"file_path": str(path)})["dataset_id"]


def test_handle_distribution_with_filter(tmp_path):
    did = _import_csv_for_explore_filter(tmp_path)
    result = handle_request("data/distribution", {
        "dataset_id": did,
        "column": "value",
        "filter_column": "work_order",
        "filter_value": "A",
    })
    fits = result["fits"]
    assert len(fits) >= 1
    for f in fits:
        assert sum(f["histogram"]["counts"]) == 30
    # Group A values cluster near 50 (group B near 150).
    assert max(fits[0]["histogram"]["edges"]) < 100


def test_handle_series_with_filter(tmp_path):
    did = _import_csv_for_explore_filter(tmp_path)
    result = handle_request("data/series", {
        "dataset_id": did,
        "column": "value",
        "filter_column": "work_order",
        "filter_value": "A",
    })
    assert result["numeric"] is True
    assert len(result["values"]) == 30
    assert all(v < 100 for v in result["values"])


def test_handle_distribution_with_filter_missing_value(tmp_path):
    did = _import_csv_for_explore_filter(tmp_path)
    with pytest.raises(ValueError):
        handle_request("data/distribution", {
            "dataset_id": did,
            "column": "value",
            "filter_column": "work_order",
        })


def test_handle_series_with_filter_missing_value(tmp_path):
    did = _import_csv_for_explore_filter(tmp_path)
    with pytest.raises(ValueError):
        handle_request("data/series", {
            "dataset_id": did,
            "column": "value",
            "filter_column": "work_order",
        })


def test_handle_distribution_with_filter_unknown_column(tmp_path):
    did = _import_csv_for_explore_filter(tmp_path)
    with pytest.raises(KeyError):
        handle_request("data/distribution", {
            "dataset_id": did,
            "column": "value",
            "filter_column": "nonexistent",
            "filter_value": "A",
        })


def test_handle_series_with_filter_unknown_column(tmp_path):
    did = _import_csv_for_explore_filter(tmp_path)
    with pytest.raises(KeyError):
        handle_request("data/series", {
            "dataset_id": did,
            "column": "value",
            "filter_column": "nonexistent",
            "filter_value": "A",
        })


def test_handle_distribution_with_filter_no_rows_match(tmp_path):
    did = _import_csv_for_explore_filter(tmp_path)
    with pytest.raises(ValueError, match="No rows match filter"):
        handle_request("data/distribution", {
            "dataset_id": did,
            "column": "value",
            "filter_column": "work_order",
            "filter_value": "Z",
        })


def test_handle_series_with_filter_no_rows_match(tmp_path):
    did = _import_csv_for_explore_filter(tmp_path)
    with pytest.raises(ValueError, match="No rows match filter"):
        handle_request("data/series", {
            "dataset_id": did,
            "column": "value",
            "filter_column": "work_order",
            "filter_value": "Z",
        })


def test_handle_quality_json_serializable(tmp_path):
    csv_text = "\n".join(
        [
            "v",
            "1.0",
            "2.0",
            "3.0",
            "30.0",
        ]
    )
    dataset_id = _import_csv_and_return_id(tmp_path, csv_text)

    result = handle_request(
        "data/quality",
        {"dataset_id": dataset_id, "categorical_columns": []},
    )
    # Must round-trip through JSON (dataclasses/enums serialized already).
    json.dumps(result)


def test_handle_datasets_lists_registered(tmp_path):
    csv_text = "x\n1.0\n2.0\n"
    dataset_id = _import_csv_and_return_id(tmp_path, csv_text)

    result = handle_request("data/datasets", {})

    ids = {d["dataset_id"] for d in result["datasets"]}
    assert dataset_id in ids


def test_import_result_contains_dataset_id(tmp_path):
    dataset_id = _import_csv_and_return_id(tmp_path, "a,b\n1,2\n3,4\n")
    meta = REGISTRY.meta(dataset_id)
    assert meta["row_count"] == 2
    assert meta["column_count"] == 2


def test_handle_series_returns_numeric_values(tmp_path):
    dataset_id = _import_csv_and_return_id(
        tmp_path, "temp,ok\n1.0,OK\n2.0,OK\n,NG\n"
    )

    result = handle_request(
        "data/series", {"dataset_id": dataset_id, "column": "temp"}
    )

    assert result["numeric"] is True
    assert result["values"] == [1.0, 2.0, None]


def test_handle_series_unknown_column_raises(tmp_path):
    dataset_id = _import_csv_and_return_id(tmp_path, "a\n1\n")

    with pytest.raises(KeyError):
        handle_request("data/series", {"dataset_id": dataset_id, "column": "nope"})


def test_handle_detect_anomalies_returns_dtos(tmp_path):
    rows = ["temp,pressure"]
    for i in range(30):
        rows.append(f"{245.0 + (i % 5)},0.45")
    rows.append("30.0,0.99")
    dataset_id = _import_csv_and_return_id(tmp_path, "\n".join(rows))

    result = handle_request(
        "analysis/detect_anomalies",
        {
            "dataset_id": dataset_id,
            "spec": {"output_field": "temp", "lsl": 235.0, "usl": 255.0, "target": 245.0},
            "control_limits": {},
            "engineering_scenarios": [],
            "runs_length": 5,
        },
    )

    scenarios = result["scenarios"]
    assert scenarios
    assert all("anomaly_id" in s and s["anomaly_id"] for s in scenarios)
    assert all("confidence" in s for s in scenarios)
    json.dumps(result)  # full DTO is JSON-serializable


def test_handle_detect_anomalies_manual_limits(tmp_path):
    dataset_id = _import_csv_and_return_id(
        tmp_path, "temp\n245.0\n246.0\n244.0\n245.5\n"
    )

    result = handle_request(
        "analysis/detect_anomalies",
        {
            "dataset_id": dataset_id,
            "spec": {},
            "control_limits": {"temp": {"lcl": 100.0, "ucl": 400.0}},
            "engineering_scenarios": [],
        },
    )

    # Manual limits contain all data -> only monitor-type scenarios with 0 events.
    assert all(s["occurrence_probability"] == 0.0 for s in result["scenarios"] if s["type"] == "control")


def test_handle_analysis_package_completion_states(tmp_path):
    dataset_id = _import_csv_and_return_id(tmp_path, "temp,pressure\n245.0,0.45\n")

    complete = handle_request(
        "analysis/package",
        {
            "dataset_id": dataset_id,
            "field_roles": {"temp": "output", "pressure": "input"},
            "spec": {"output_field": "temp", "lsl": 235.0, "usl": 255.0},
            "anomalies": [],
            "confirmed_roles": ["temp", "pressure"],
        },
    )

    assert complete["complete"] is True
    assert complete["data"]["row_count"] == 1
    assert complete["data"]["field_roles"]["temp"] == "output"

    incomplete = handle_request(
        "analysis/package",
        {
            "dataset_id": dataset_id,
            "field_roles": {"temp": "unassigned", "pressure": "input"},
            "spec": {},
            "anomalies": [],
            "confirmed_roles": ["pressure"],
        },
    )
    assert incomplete["complete"] is False
    assert "output" in "".join(incomplete["missing_requirements"])


def _copula_anomalies():
    return [
        {"anomaly_id": "A", "occurrence_probability": 0.3},
        {"anomaly_id": "B", "occurrence_probability": 0.4},
    ]


def test_handle_copula_independent_mode():
    result = handle_request(
        "copula/joint",
        {"anomalies": _copula_anomalies()},
    )
    assert result["mode"] == "independent"
    # product 0.3 * 0.4 = 0.12
    key = "A&B"
    assert abs(result["joint_probabilities"][key] - 0.12) < 1e-6
    assert abs(result["joint_probabilities"]["A"] - 0.3) < 1e-6
    assert abs(result["joint_probabilities"]["B"] - 0.4) < 1e-6
    json.dumps(result)


def test_handle_copula_single_anomaly_returns_marginal():
    result = handle_request(
        "copula/joint",
        {"anomalies": [{"anomaly_id": "A", "occurrence_probability": 0.75}]},
    )
    assert result["mode"] == "independent"
    assert abs(result["joint_probabilities"]["A"] - 0.75) < 1e-6


def test_handle_copula_empty_anomalies():
    result = handle_request("copula/joint", {"anomalies": []})
    assert result["mode"] == "independent"
    assert result["joint_probabilities"] == {}


def test_handle_copula_direct_mode():
    result = handle_request(
        "copula/joint",
        {
            "anomalies": _copula_anomalies(),
            "direct_joints": {"A&B": 0.5},
        },
    )
    assert result["mode"] == "direct"
    assert abs(result["joint_probabilities"]["A&B"] - 0.5) < 1e-6


def test_handle_copula_gaussian_correlation_matrix(tmp_path):
    result = handle_request(
        "copula/joint",
        {
            "anomalies": _copula_anomalies(),
            "correlation_matrix": [[1.0, 0.5], [0.5, 1.0]],
            "seed": 42,
            "n_samples": 20000,
        },
    )
    assert result["mode"] == "gaussian_copula"
    assert "pair_correlations" in result
    assert len(result["pair_correlations"]) == 1
    assert result["pair_correlations"][0]["anomaly_a"] == "A"
    assert result["pair_correlations"][0]["anomaly_b"] == "B"
    assert result["pair_correlations"][0]["correlation"] != 0.0
    json.dumps(result)


def test_handle_copula_invalid_matrix_falls_back_with_warning():
    result = handle_request(
        "copula/joint",
        {
            "anomalies": _copula_anomalies(),
            # Not positive semidefinite
            "correlation_matrix": [[1.0, 1.5], [1.5, 1.0]],
        },
    )
    assert result["mode"] == "independent"
    assert "warning" in result


# ---------------------------------------------------------------------------
# cloud/preview & cloud/upload – strategy_overrides passthrough
# ---------------------------------------------------------------------------


def test_handle_cloud_preview_passes_strategy_overrides(tmp_path):
    csv_text = "\n".join(
        ["temperature,operator,ok_flag", "230.5,Alice,OK", "241.0,Bob,NG", "255.2,Carol,OK"]
    )
    dataset_id = _import_csv_and_return_id(tmp_path, csv_text)

    result = handle_request(
        "cloud/preview",
        {
            "dataset_id": dataset_id,
            "sensitive_columns": ["temperature"],
            "strategy_overrides": {"temperature": "noise"},
            "noise_std": 0.5,
        },
    )
    assert result["noise_config"]["temperature"]["method"] == "gaussian"
    assert result["noise_config"]["temperature"]["std"] == 0.5


def test_handle_cloud_preview_and_upload_consistent(tmp_path):
    csv_text = "\n".join(
        ["temperature,operator,ok_flag", "230.5,Alice,OK", "241.0,Bob,NG", "255.2,Carol,OK"]
    )
    dataset_id = _import_csv_and_return_id(tmp_path, csv_text)

    preview = handle_request(
        "cloud/preview",
        {
            "dataset_id": dataset_id,
            "sensitive_columns": ["operator"],
            "strategy_overrides": {"operator": "hash"},
        },
    )
    assert preview["mask_strategies"]["operator"] == "hash"

    result = handle_request(
        "cloud/upload",
        {
            "dataset_id": dataset_id,
            "sensitive_columns": ["operator"],
            "strategy_overrides": {"operator": "hash"},
            "operator": "qa",
            "provider": "azure",
            "model_version": "gpt-5",
            "purpose": "training",
        },
    )
    assert result["record_id"]
    assert result["columns_uploaded"]
    assert "operator" in result["masked_columns"]


def test_handle_report_list_returns_registry(tmp_path):
    _REPORT_REGISTRY._clear()
    csv_text = "\n".join(["temp,flag", "1.0,OK", "2.0,OK", "3.0,NG"])
    dataset_id = _import_csv_and_return_id(tmp_path, csv_text)
    handle_request(
        "report/generate",
        {"dataset_id": dataset_id, "project_name": "Proj X", "operator": "qa", "format": "html"},
    )
    result = handle_request("report/list", {})
    assert result["reports"]
    assert result["reports"][0]["project_name"] == "Proj X"


def test_handle_flow_graph_set_association_keys():
    result = handle_request("project/flow-graph", {"set_association_keys": ["barcode", "batch_no"]})
    assert result["association_keys"] == ["barcode", "batch_no"]
    again = handle_request("project/flow-graph", {})
    assert again["association_keys"] == ["barcode", "batch_no"]


def test_time_series_with_filter(tmp_path):
    """Test time_series handler applies row filter."""
    import numpy as np
    from datetime import datetime, timedelta
    rng = np.random.default_rng(42)
    rows = ["time,x,category"]
    for i in range(100):
        t = datetime(2026, 1, 1) + timedelta(minutes=i)
        cat = "A" if i < 50 else "B"
        rows.append(f"{t.isoformat()},{rng.uniform():.6f},{cat}")
    path = tmp_path / "ts.csv"
    path.write_text("\n".join(rows), encoding="utf-8")
    did = handle_request("data/import", {"file_path": str(path)})["dataset_id"]

    # Without filter: should have 100 rows
    result = handle_request("features/time_series", {
        "dataset_id": did, "time_column": "time", "value_columns": ["x"],
    })
    assert result["n_rows"] == 100

    # With filter: should have 50 rows
    result2 = handle_request("features/time_series", {
        "dataset_id": did, "time_column": "time", "value_columns": ["x"],
        "filter_column": "category", "filter_value": "A",
    })
    assert result2["n_rows"] == 50


def test_grr_with_filter(tmp_path):
    """Test GRR handler applies row filter."""
    import numpy as np
    rng = np.random.default_rng(42)
    rows = ["part,operator,measurement,category"]
    for i in range(60):
        rows.append(f"P{i%10},Op{i%3},{rng.uniform(9,11):.4f},{'A' if i<30 else 'B'}")
    path = tmp_path / "grr.csv"
    path.write_text("\n".join(rows), encoding="utf-8")
    did = handle_request("data/import", {"file_path": str(path)})["dataset_id"]

    result = handle_request("data/grr", {
        "dataset_id": did, "measurement_column": "measurement",
        "part_column": "part", "operator_column": "operator",
    })
    assert result["n_parts"] == 10
    assert result["n_reps"] == 2

    result2 = handle_request("data/grr", {
        "dataset_id": did, "measurement_column": "measurement",
        "part_column": "part", "operator_column": "operator",
        "filter_column": "category", "filter_value": "A",
    })
    # 30 rows → 10 parts × 3 operators × 1 rep
    assert result2["n_parts"] == 10
    assert result2["n_reps"] == 1


def test_handle_spec_suggest(tmp_path):
    """Test spec/suggest returns mean±3σ for a numeric column."""
    import numpy as np
    rng = np.random.default_rng(42)
    n = 100
    values = [10.0 + i * 0.1 + rng.normal(0, 0.5) for i in range(n)]
    rows = ["x"] + [f"{v:.6f}" for v in values]
    path = tmp_path / "suggest.csv"
    path.write_text("\n".join(rows), encoding="utf-8")
    did = handle_request("data/import", {"file_path": str(path)})["dataset_id"]

    result = handle_request("spec/suggest", {"dataset_id": did, "column": "x"})
    assert result["success"]
    assert result["column"] == "x"
    assert result["lsl"] < result["mean"] < result["usl"]
    assert abs(result["lsl"] - (result["mean"] - 3 * result["std"])) < 0.001
    assert abs(result["usl"] - (result["mean"] + 3 * result["std"])) < 0.001


def test_handle_spec_suggest_unknown_column_raises():
    import numpy as np
    rng = np.random.default_rng(42)
    rows = ["x"] + [f"{rng.normal()}" for _ in range(10)]
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("\n".join(rows))
        path = f.name
    did = handle_request("data/import", {"file_path": path})["dataset_id"]
    os.unlink(path)

    with pytest.raises(KeyError):
        handle_request("spec/suggest", {"dataset_id": did, "column": "nonexistent"})


def test_handle_spec_suggest_constant_raises():
    rows = ["x"] + ["5.0"] * 10
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("\n".join(rows))
        path = f.name
    did = handle_request("data/import", {"file_path": path})["dataset_id"]
    os.unlink(path)

    with pytest.raises(ValueError, match="std is zero"):
        handle_request("spec/suggest", {"dataset_id": did, "column": "x"})


def test_apply_row_filter_rejects_empty_value():
    """Test _apply_row_filter raises when filter_value is empty string."""
    import pandas as pd
    from process_intelligence_engine.main import _apply_row_filter
    df = pd.DataFrame({"x": [1, 2, 3], "cat": ["A", "B", "A"]})
    with pytest.raises(ValueError, match="filter_value is required"):
        _apply_row_filter(df, {"filter_column": "cat", "filter_value": ""})


def test_version_chain_summary_after_import(tmp_path):
    csv = tmp_path / "test.csv"
    csv.write_text("x,y\n1,2\n3,4\n5,6\n")
    handle_request("versioning/chain/summary", {})
    result = handle_request("data/import", {"file_path": str(csv)})
    did = result["dataset_id"]
    summary = handle_request("versioning/chain/summary", {})
    assert any(e["entity_type"] == "dataset" for e in summary["summary"])
    assert "chain_entity_id" in result


def test_experiment_record_with_verdict(tmp_path):
    csv = tmp_path / "test.csv"
    csv.write_text("x,y\n1,2\n3,4\n5,6\n7,8\n9,10\n")
    import_result = handle_request("data/import", {"file_path": str(csv)})
    dataset_id = import_result["dataset_id"]
    fit_result = handle_request("modeling/fit", {
        "dataset_id": dataset_id, "model_type": "doe_linear",
        "target": "y", "inputs": ["x"],
    })
    model_id = fit_result["model_id"]
    result = handle_request("experiment/record_with_verdict", {
        "experiment_id": "exp-test-001",
        "model_id": model_id,
        "planned_inputs": {"x": 2.0},
        "actual_inputs": {"x": 2.0},
        "predicted_output": 4.0,
        "actual_output": 4.1,
        "tolerance": 0.5,
        "operator": "fred",
    })
    assert "verdict" in result
    assert result["verdict"] in ("supports", "partially_supports", "does_not_support", "needs_remodel")


def test_experiment_suggest_next(tmp_path):
    csv = tmp_path / "test.csv"
    csv.write_text("x,y\n1,2\n3,4\n5,6\n7,8\n9,10\n")
    import_result = handle_request("data/import", {"file_path": str(csv)})
    dataset_id = import_result["dataset_id"]
    fit_result = handle_request("modeling/fit", {
        "dataset_id": dataset_id, "model_type": "doe_linear",
        "target": "y", "inputs": ["x"],
    })
    model_id = fit_result["model_id"]
    result = handle_request("experiment/suggest_next", {
        "model_id": model_id,
        "dataset_id": dataset_id,
        "n_suggestions": 3,
    })
    assert "suggestions" in result
    assert isinstance(result["suggestions"], list)


def test_anomaly_register_in_chain(tmp_path):
    csv = tmp_path / "test.csv"
    csv.write_text("x,y\n1,2\n3,4\n5,6\n")
    result = handle_request("data/import", {"file_path": str(csv)})
    dataset_id = result["dataset_id"]
    from process_intelligence_engine.main import _VERSION_CHAIN
    dataset_chain_id = _VERSION_CHAIN.register_entity(
        entity_type="dataset", project_id="default",
        metadata={"dataset_id": dataset_id}, created_by="anonymous",
    )
    exp = handle_request("analysis/anomaly/register", {
        "dataset_id": dataset_chain_id,
        "anomaly_id": "ano-test",
        "source": "engineering_input",
        "confidence": 0.9,
        "user_confirmed": True,
        "operator": "fred",
    })
    assert "entity_id" in exp
    assert exp["entity_id"].startswith("ano-")
    summary = handle_request("versioning/chain/summary", {})
    assert any(e["entity_type"] == "anomaly" for e in summary["summary"])
