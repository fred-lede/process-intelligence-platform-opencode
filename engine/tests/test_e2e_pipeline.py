"""End-to-end test: spawn the engine subprocess and drive the full
Phase 1 pipeline through the real stdin/stdout JSON-RPC protocol.

This is the same contract the Rust EngineManager talks to, so it locks
in the wire format for the whole app.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ENGINE_MAIN = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "process_intelligence_engine"
    / "main.py"
)
PYTHON = sys.executable


@pytest.fixture(scope="module")
def engine():
    proc = subprocess.Popen(
        [PYTHON, str(ENGINE_MAIN)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
    )
    try:
        yield _Engine(proc)
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)


class _Engine:
    def __init__(self, proc):
        self._proc = proc
        self._counter = 0

    def call(self, method, params=None):
        self._counter += 1
        req_id = f"e2e-{self._counter}"
        payload = {"id": req_id, "method": method, "params": params or {}}
        self._proc.stdin.write(json.dumps(payload) + "\n")
        self._proc.stdin.flush()

        deadline = time.time() + 30
        while time.time() < deadline:
            line = self._proc.stdout.readline()
            if not line:
                raise RuntimeError("Engine exited unexpectedly.")
            response = json.loads(line)
            if response.get("id") == req_id:
                if "error" in response:
                    raise RuntimeError(response["error"]["message"])
                return response["result"]
        raise RuntimeError(f"Timeout waiting for response to {method}")


def test_ping(engine):
    result = engine.call("engine/ping")
    assert result["pong"] is True
    assert result["version"]


def test_full_pipeline(engine, tmp_path):
    # Build a realistic SMT-style file.
    header = "barcode,temperature,pressure,ok_flag,defect"
    rows = [header]
    for i in range(120):
        temp = 240 + (i % 11)
        pressure = round(0.4 + (i % 7) * 0.02, 3)
        ok = "OK" if temp <= 250 else "NG"
        defect = "受潮" if temp > 250 else ""
        rows.append(f"smt{i:05d},{temp},{pressure},{ok},{defect}")
    csv_path = tmp_path / "smt_run.csv"
    csv_path.write_text("\n".join(rows), encoding="utf-8")

    # 1. Import -> dataset_id
    imp = engine.call("data/import", {"file_path": str(csv_path)})
    assert imp["dataset_id"]
    assert imp["row_count"] == 120
    assert imp["column_count"] == 5
    dataset_id = imp["dataset_id"]

    # 2. Detect fields (engine-side, via dataset_id)
    detected = engine.call("data/detect_fields", {"dataset_id": dataset_id})
    roles = {f["name"]: f["role"] for f in detected["fields"]}
    assert roles["barcode"] == "identifier"
    assert roles["temperature"] == "input"
    assert roles["ok_flag"] == "quality_label"
    assert roles["defect"] in {"category", "metadata"}

    # 3. Quality checks
    quality = engine.call(
        "data/quality",
        {
            "dataset_id": dataset_id,
            "quality_columns": ["ok_flag"],
            "categorical_columns": ["ok_flag", "defect"],
        },
    )
    codes = {i["check"] for i in quality["issues"]}
    # ok_flag is all OK here, so the OK/NG ratio is fully imbalanced.
    assert "unbalanced_okng" in codes
    # defect column is blank for most rows -> missing values are expected.
    assert "missing_value" in codes
    assert quality["row_count"] == 120

    # 4. Distribution fit with pdf curve
    fit = engine.call(
        "data/distribution",
        {"dataset_id": dataset_id, "column": "pressure", "top_n": 3},
    )
    assert fit["fits"]
    assert any(f["pdf"]["x"] for f in fit["fits"] if f["name"] != "empirical")

    # 5. Trend series
    series = engine.call(
        "data/series",
        {"dataset_id": dataset_id, "column": "temperature"},
    )
    assert series["numeric"] is True
    assert len(series["values"]) == 120

    # 6. dataset registry lists it
    datasets = engine.call("data/datasets", {})
    assert any(d["dataset_id"] == dataset_id for d in datasets["datasets"])


def test_unknown_method_error(engine):
    with pytest.raises(RuntimeError) as excinfo:
        engine.call("no/such_method", {})
    assert "Unknown method" in str(excinfo.value)