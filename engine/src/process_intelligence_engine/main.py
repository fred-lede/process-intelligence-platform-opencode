"""Analysis engine entry point.

The engine runs as a child process, communicating with the Tauri backend
via JSON request/response on stdin/stdout. Each request is a JSON object:

    {"id": "uuid", "method": "engine/ping", "params": {...}}

Each response is a JSON object:

    {"id": "uuid", "result": {...}}      # success
    {"id": "uuid", "error": {...}}       # failure

This protocol keeps the engine language-agnostic and easily testable.
"""

from __future__ import annotations

import json
import sys
import threading
import traceback
import uuid

import numpy as np
import pandas as pd

from process_intelligence_engine.analysis.anomalies import build_analysis_package, detect_anomaly_scenarios
from process_intelligence_engine.data.distribution import fit_best_distribution
from process_intelligence_engine.data.field_detector import detect_fields
from process_intelligence_engine.data.importer import import_file
from process_intelligence_engine.data.quality import run_quality_checks
from process_intelligence_engine.modeling.fitters import (
    fit_doe_linear,
    fit_doe_quadratic,
    fit_random_forest,
    fit_residual_hybrid,
)
from process_intelligence_engine.modeling.registry import ModelRegistry


def _plain_types(value):
    """Recursively convert numpy/pandas scalars to JSON-native types.

    Engine internals legitimately produce numpy ints/floats; this keeps the
    entire IPC contract JSON-serializable regardless of which layer leaks a
    numpy value.
    """
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return value.item()
    if isinstance(value, np.ndarray):
        return _plain_types(value.tolist())
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _plain_types(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_types(v) for v in value]
    return value


class DatasetRegistry:
    """In-memory registry of imported datasets.

    Keeps full DataFrames in the engine process so that downstream stages
    (quality, distribution, modeling) operate on complete data without
    shipping it back to the UI. Datasets are read-only after import.
    """

    def __init__(self) -> None:
        self._datasets: dict[str, pd.DataFrame] = {}
        self._meta: dict[str, dict] = {}
        self._lock = threading.Lock()

    def register(self, df: pd.DataFrame, meta: dict) -> str:
        dataset_id = str(uuid.uuid4())
        with self._lock:
            self._datasets[dataset_id] = df
            self._meta[dataset_id] = meta
        return dataset_id

    def get(self, dataset_id: str) -> pd.DataFrame:
        if dataset_id not in self._datasets:
            raise KeyError(f"Unknown dataset_id: {dataset_id}")
        return self._datasets[dataset_id]

    def meta(self, dataset_id: str) -> dict:
        if dataset_id not in self._meta:
            raise KeyError(f"Unknown dataset_id: {dataset_id}")
        return self._meta[dataset_id]

    def list_ids(self) -> list[str]:
        return sorted(self._datasets.keys())


# Registry shared across requests within a single engine process.
REGISTRY = DatasetRegistry()
MODEL_REGISTRY = ModelRegistry()


def _handle_import(params: dict) -> dict:
    """Import an Excel/CSV file, register it, and return a serializable result."""
    file_path = params["file_path"]
    result = import_file(file_path)
    df = result.to_dataframe()
    dataset_id = REGISTRY.register(
        df,
        {
            "file_path": result.file_path,
            "format": result.format,
            "encoding": result.encoding,
            "delimiter": result.delimiter,
            "row_count": result.row_count,
            "column_count": result.column_count,
        },
    )
    dto = result.to_dto()
    dto["dataset_id"] = dataset_id
    return dto


def _handle_detect_fields(params: dict) -> dict:
    """Detect roles/types for columns.

    If `dataset_id` is given, use the registered dataset's values.
    Otherwise use `columns` (list of {name, values}).
    """
    if params.get("dataset_id"):
        df = REGISTRY.get(params["dataset_id"])
        columns = [
            {"name": str(col), "values": df[col].tolist()}
            for col in df.columns
        ]
    else:
        columns = params.get("columns", [])

    fields = detect_fields(columns)

    return {
        "fields": [
            {
                "name": f.name,
                "role": f.role.value,
                "data_type": f.data_type,
                "confidence": f.confidence,
                "reason": f.reason,
            }
            for f in fields
        ]
    }


def _handle_quality(params: dict) -> dict:
    """Run quality checks over a registered dataset."""
    df = REGISTRY.get(params["dataset_id"])
    report = run_quality_checks(
        df,
        categorical_columns=params.get("categorical_columns", []),
        quality_columns=params.get("quality_columns", []),
        datetime_columns=params.get("datetime_columns", []),
        batch_columns=params.get("batch_columns", []),
    )
    return {
        "row_count": report.row_count,
        "column_count": report.column_count,
        "issues": [
            {
                "check": i.check.value,
                "column": i.column,
                "severity": i.severity.value,
                "message": i.message,
                "detail": i.detail,
            }
            for i in report.issues
        ],
    }


def _df_from_rows(params: dict) -> pd.DataFrame:
    columns: list[str] = params["columns"]
    rows: list[list] = params["rows"]
    data: dict[str, list] = {col: [] for col in columns}
    for row in rows:
        row = list(row) + [None] * (len(columns) - len(row))
        for col, value in zip(columns, row):
            data[col].append(value)
    return pd.DataFrame(data)


def _handle_distribution(params: dict) -> dict:
    """Fit distributions for a registered dataset column."""
    if params.get("dataset_id"):
        df = REGISTRY.get(params["dataset_id"])
        column = params["column"]
        values = df[column].tolist()
    else:
        values = params.get("values", [])

    top_n = int(params.get("top_n", 3))
    fits = fit_best_distribution(values, top_n=top_n)
    return {
        "fits": [
            {
                "name": f.name,
                "params": f.params,
                "aic": f.aic,
                "bic": f.bic,
                "ks_statistic": f.ks_statistic,
                "ks_p_value": f.ks_p_value,
                "loglik": f.loglik,
                "skewness": f.skewness,
                "kurtosis": f.kurtosis,
                "histogram": f.histogram,
                "pdf": f.pdf,
            }
            for f in fits
        ]
    }


def _handle_series(params: dict) -> dict:
    """Return a column's values from a registered dataset (for charts).

    Numeric columns are returned as floats; other values as-is (nulls stay
    null). Phase 1 keeps raw data client-side for charting only.
    """
    df = REGISTRY.get(params["dataset_id"])
    column = params["column"]
    if column not in df.columns:
        raise KeyError(f"Unknown column: {column}")

    series = df[column]
    relaxed = pd.api.types.is_numeric_dtype(series)
    values: list = []
    for v in series.tolist():
        if v is None or (isinstance(v, float) and pd.isna(v)):
            values.append(None)
        elif relaxed:
            values.append(float(v))
        else:
            values.append(str(v))
    return {"column": column, "values": values, "numeric": bool(relaxed)}


def _handle_datasets(params: dict) -> dict:
    """List registered datasets (for debugging/management)."""
    return {
        "datasets": [
            {"dataset_id": did, **REGISTRY.meta(did)}
            for did in REGISTRY.list_ids()
        ]
    }


def _handle_detect_anomalies(params: dict) -> dict:
    """Detect spec/control/engineering anomaly scenarios over a dataset.

    Phase 2 decision: control limits default to mean ± 3σ when a column has
    no manual LCL/UCL; engineering scenarios come from the user's templates.
    """
    df = REGISTRY.get(params["dataset_id"])
    scenarios = detect_anomaly_scenarios(
        df,
        spec=params.get("spec") or {},
        control_limits=params.get("control_limits") or {},
        engineering_scenarios=params.get("engineering_scenarios") or [],
        runs_length=int(params.get("runs_length", 5)),
    )
    return {"scenarios": [s.to_dto() for s in scenarios]}


def _handle_analysis_package(params: dict) -> dict:
    """Assemble the confirmable analysis data package (section 11A)."""
    dataset_id = params["dataset_id"]
    meta = REGISTRY.meta(dataset_id)
    df = REGISTRY.get(dataset_id)
    return build_analysis_package(
        dataset_id=dataset_id,
        source_file=meta.get("file_path", ""),
        row_count=len(df),
        column_count=len(df.columns),
        field_roles=params.get("field_roles") or {},
        spec=params.get("spec") or {},
        anomalies=params.get("anomalies") or [],
        confirmed_roles=params.get("confirmed_roles") or [],
    )


MODEL_FITTERS = {
    "doe_linear": fit_doe_linear,
    "doe_quadratic": fit_doe_quadratic,
    "random_forest": fit_random_forest,
    "residual_hybrid": fit_residual_hybrid,
}


def _handle_modeling_fit(params: dict) -> dict:
    df = REGISTRY.get(params["dataset_id"])
    model_type = params["model_type"]
    target = params["target"]
    inputs = list(params.get("inputs", []))
    fitter = MODEL_FITTERS.get(model_type)
    if fitter is None:
        raise ValueError(f"Unknown model_type: {model_type}")
    fit = fitter(df, target=target, inputs=inputs)
    MODEL_REGISTRY.register(fit)
    return fit.to_dto()


def _handle_modeling_list(params: dict) -> dict:
    return {
        "models": [MODEL_REGISTRY.get(mid).to_dto() for mid in MODEL_REGISTRY.list_ids()]
    }


def _handle_modeling_transition(params: dict) -> dict:
    fit = MODEL_REGISTRY.transition(params["model_id"], params["status"])
    return fit.to_dto()


def handle_request(method: str, params: dict) -> dict:
    """Dispatch an RPC method to its handler.

    Phase 1 methods: engine/ping, engine/health and the data pipeline
    (import, detect_fields, quality, distribution).
    Phase 2 methods: analysis/detect_anomalies, analysis/package.
    """
    if method == "engine/ping":
        return {"pong": True, "version": "0.1.0"}

    if method == "engine/health":
        return {
            "status": "ok",
            "engine": "process-intelligence-engine",
            "version": "0.1.0",
        }

    if method == "data/import":
        return _handle_import(params)

    if method == "data/datasets":
        return _handle_datasets(params)

    if method == "data/detect_fields":
        return _handle_detect_fields(params)

    if method == "data/quality":
        return _handle_quality(params)

    if method == "data/distribution":
        return _handle_distribution(params)

    if method == "data/series":
        return _handle_series(params)

    if method == "analysis/detect_anomalies":
        return _handle_detect_anomalies(params)

    if method == "analysis/package":
        return _handle_analysis_package(params)

    if method == "modeling/fit":
        return _handle_modeling_fit(params)

    if method == "modeling/list":
        return _handle_modeling_list(params)

    if method == "modeling/transition":
        return _handle_modeling_transition(params)

    raise ValueError(f"Unknown method: {method}")


def _read_request() -> dict | None:
    line = sys.stdin.readline()
    if not line:
        return None
    return json.loads(line)


def main() -> int:
    # Log to stderr so stdout stays clean for the RPC protocol.
    while True:
        try:
            request = _read_request()
            if request is None:
                break  # EOF, parent closed the pipe

            req_id = request.get("id")
            method = request.get("method", "")
            params = request.get("params", {})

            try:
                result = handle_request(method, params)
                print(json.dumps({"id": req_id, "result": _plain_types(result)}), flush=True)
            except Exception as exc:  # noqa: BLE001 - report errors to parent
                print(
                    json.dumps(
                        {
                            "id": req_id,
                            "error": {
                                "message": str(exc),
                                "traceback": traceback.format_exc(),
                            },
                        }
                    ),
                    flush=True,
                )
        except json.JSONDecodeError as exc:
            print(
                json.dumps(
                    {"id": None, "error": {"message": f"Invalid JSON: {exc}"}}
                ),
                flush=True,
            )
        except KeyboardInterrupt:
            break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())