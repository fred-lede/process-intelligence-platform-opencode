"""Test the engine method handlers directly (dispatch layer)."""

import json

import pytest

from process_intelligence_engine.main import handle_request, REGISTRY
from process_intelligence_engine.reporting.registry import _REPORT_REGISTRY


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
