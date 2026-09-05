"""Tests for SPC IPC handlers."""
import json
import pytest
from process_intelligence_engine.main import handle_request


def _import_csv_for_spc(tmp_path):
    import numpy as np
    rng = np.random.default_rng(42)
    rows = ["batch,temp,pressure,output"]
    for i in range(100):
        t = rng.uniform(200, 300)
        p = rng.uniform(50, 100)
        output = 100 + 0.5 * t - 0.3 * p + rng.normal(0, 2)
        rows.append(f"{i},{t:.2f},{p:.2f},{output:.2f}")
    path = tmp_path / "spc.csv"
    path.write_text("\n".join(rows), encoding="utf-8")
    return handle_request("data/import", {"file_path": str(path)})["dataset_id"]


def test_spc_analyze_i_mr(tmp_path):
    did = _import_csv_for_spc(tmp_path)
    result = handle_request("spc/analyze", {
        "dataset_id": did,
        "column": "output",
        "chart_type": "i-mr",
    })
    assert result["success"]
    assert result["chart_type"] == "i-mr"
    assert "control_limits" in result
    assert "violations" in result
    assert "capability" in result
    assert result["capability"]["total_observations"] == 100
    json.dumps(result)


def test_spc_analyze_xbar_r(tmp_path):
    did = _import_csv_for_spc(tmp_path)
    result = handle_request("spc/analyze", {
        "dataset_id": did,
        "column": "output",
        "chart_type": "xbar-r",
        "subgroup_size": 5,
    })
    assert result["success"]
    assert result["chart_type"] == "xbar-r"
    assert len(result["xbar_values"]) == 20  # 100/5 = 20 subgroups


def test_spc_analyze_xbar_s(tmp_path):
    did = _import_csv_for_spc(tmp_path)
    result = handle_request("spc/analyze", {
        "dataset_id": did,
        "column": "output",
        "chart_type": "xbar-s",
        "subgroup_size": 5,
    })
    assert result["success"]
    assert result["chart_type"] == "xbar-s"


def test_spc_analyze_unknown_column_raises(tmp_path):
    did = _import_csv_for_spc(tmp_path)
    with pytest.raises(KeyError):
        handle_request("spc/analyze", {
            "dataset_id": did,
            "column": "nonexistent",
            "chart_type": "i-mr",
        })


def test_spc_analyze_unknown_dataset_raises():
    with pytest.raises(KeyError):
        handle_request("spc/analyze", {
            "dataset_id": "nonexistent",
            "column": "output",
            "chart_type": "i-mr",
        })


def test_spc_analyze_xbar_r_insufficient_data(tmp_path):
    did = _import_csv_for_spc(tmp_path)
    with pytest.raises(ValueError):
        handle_request("spc/analyze", {
            "dataset_id": did,
            "column": "output",
            "chart_type": "xbar-r",
            "subgroup_size": 999,
        })


def test_spc_analyze_unknown_chart_type_raises(tmp_path):
    did = _import_csv_for_spc(tmp_path)
    with pytest.raises(ValueError):
        handle_request("spc/analyze", {
            "dataset_id": did,
            "column": "output",
            "chart_type": "p-chart",
        })


def _import_csv_for_spc_filter(tmp_path):
    import numpy as np
    rng = np.random.default_rng(7)
    rows = ["work_order,output"]
    for i in range(60):
        group = "A" if i < 30 else "B"
        base = 50.0 if group == "A" else 150.0
        out = base + rng.normal(0, 1.5)
        rows.append(f"{group},{out:.2f}")
    path = tmp_path / "spc_filter.csv"
    path.write_text("\n".join(rows), encoding="utf-8")
    return handle_request("data/import", {"file_path": str(path)})["dataset_id"]


def test_spc_analyze_with_filter(tmp_path):
    did = _import_csv_for_spc_filter(tmp_path)
    result = handle_request("spc/analyze", {
        "dataset_id": did,
        "column": "output",
        "chart_type": "i-mr",
        "filter_column": "work_order",
        "filter_value": "A",
    })
    assert result["success"]
    assert len(result["x_values"]) == 30
    assert all(v < 100 for v in result["x_values"])
    assert abs(result["subgroup_stats"]["x_mean"] - 50.0) < 1.5


def test_spc_analyze_with_filter_unknown_column(tmp_path):
    did = _import_csv_for_spc_filter(tmp_path)
    with pytest.raises(KeyError):
        handle_request("spc/analyze", {
            "dataset_id": did,
            "column": "output",
            "chart_type": "i-mr",
            "filter_column": "nonexistent",
            "filter_value": "A",
        })


def test_spc_capability_only(tmp_path):
    did = _import_csv_for_spc(tmp_path)
    result = handle_request("spc/capability", {
        "dataset_id": did,
        "column": "output",
        "lsl": 90.0,
        "usl": 110.0,
    })
    assert result["success"]
    assert result["capability"]["total_observations"] == 100
    assert result["capability"]["cp"] is not None
    assert result["capability"]["cpk"] is not None
    json.dumps(result)


def test_spc_capability_no_limits(tmp_path):
    did = _import_csv_for_spc(tmp_path)
    result = handle_request("spc/capability", {
        "dataset_id": did,
        "column": "output",
    })
    assert result["success"]
    assert result["capability"]["cp"] is None
    assert result["capability"]["cpk"] is None
