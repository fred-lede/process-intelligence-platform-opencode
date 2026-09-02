"""Tests for report generation IPC handler."""
import pytest

from process_intelligence_engine.main import handle_request, REGISTRY, MODEL_REGISTRY
from process_intelligence_engine.modeling.fitters import fit_doe_linear
import pandas as pd
import numpy as np


def _setup():
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "A": rng.uniform(0, 10, 20),
        "B": rng.uniform(0, 10, 20),
        "C": rng.uniform(0, 10, 20),
    })
    df["Y"] = 2.0 + 3.0 * df["A"] - 2.0 * df["B"] + rng.normal(0, 0.5, 20)

    dataset_id = REGISTRY.register(df, {"source": "test"})

    fit1 = fit_doe_linear(df, target="Y", inputs=["A", "B", "C"])
    MODEL_REGISTRY.register(fit1)

    return fit1, dataset_id


def test_report_generate_missing_dataset_id():
    with pytest.raises(ValueError, match="dataset_id is required"):
        handle_request("report/generate", {
            "project_name": "Test",
            "format": "html",
        })


def test_report_generate_html():
    fit1, dataset_id = _setup()

    result = handle_request("report/generate", {
        "project_name": "Test Project",
        "operator": "Fred Wang",
        "dataset_id": dataset_id,
        "format": "html",
    })

    assert result["format"] == "html"
    assert result["content"]
    assert "Test Project" in result["content"]
    assert "Fred Wang" in result["content"]


def test_report_generate_html_with_model():
    fit1, dataset_id = _setup()

    result = handle_request("report/generate", {
        "project_name": "Test Project",
        "operator": "Fred Wang",
        "dataset_id": dataset_id,
        "model_ids": [fit1.model_id],
        "format": "html",
    })

    assert result["format"] == "html"
    assert "html" in result["content"]
    assert "input" in result["content"]
    assert "output" in result["content"]


def test_report_generate_excel():
    fit1, dataset_id = _setup()

    result = handle_request("report/generate", {
        "project_name": "Test Project",
        "operator": "Fred Wang",
        "dataset_id": dataset_id,
        "format": "excel",
    })

    assert result["format"] == "excel"
    assert result["content_base64"]
    assert isinstance(result["content_base64"], str)
    assert len(result["content_base64"]) > 0


def test_report_generate_unsupported_format():
    _, dataset_id = _setup()

    with pytest.raises(ValueError, match="Unsupported format"):
        handle_request("report/generate", {
            "project_name": "Test",
            "dataset_id": dataset_id,
            "format": "pdf",
        })


def test_report_generate_json_serializable():
    fit1, dataset_id = _setup()

    result = handle_request("report/generate", {
        "project_name": "Test",
        "dataset_id": dataset_id,
        "format": "html",
    })

    import json
    json.dumps(result)
