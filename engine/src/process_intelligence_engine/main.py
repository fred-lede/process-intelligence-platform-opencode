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
import asyncio
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
from process_intelligence_engine.data.grr import analyze_grr
from process_intelligence_engine.data.deidentify import (
    generate_upload_preview,
    apply_deidentification,
    record_upload,
    list_upload_records,
)
from process_intelligence_engine.project.manifest import ProjectEngine, _PROCESS_GROUP_TEMPLATES
from process_intelligence_engine.modeling.interactions import compute_interactions
from process_intelligence_engine.modeling.shap_explainer import compute_shap
from process_intelligence_engine.modeling.extrapolation import compute_extrapolation_risk
from process_intelligence_engine.modeling.validation import cross_validate, analyze_residuals, recommend_experiments, compute_credibility
from process_intelligence_engine.modeling.model_selection import compare_models
from process_intelligence_engine.modeling.experiment_recommendation import recommend_experiments as recommend_experiments_full
from process_intelligence_engine.modeling.fitters import (
    fit_doe_linear,
    fit_doe_quadratic,
    fit_random_forest,
    fit_residual_hybrid,
    fit_logistic_regression,
    fit_weibull_regression,
)
from process_intelligence_engine.modeling.doe import generate_design
from process_intelligence_engine.modeling.registry import ModelRegistry
from process_intelligence_engine.reporting.models import ReportData
from process_intelligence_engine.reporting.html import HTMLReportGenerator
from process_intelligence_engine.reporting.excel import ExcelReportGenerator
from process_intelligence_engine.reporting.pdf import PDFReportGenerator
from process_intelligence_engine.auth.models import UserRole, AuditAction
from process_intelligence_engine.auth.manager import AuthManager
from process_intelligence_engine.ai.ollama_client import get_ollama_client
from process_intelligence_engine.spc import (
    compute_i_mr,
    compute_xbar_r,
    compute_xbar_s,
    compute_capability,
)
from process_intelligence_engine.monte_carlo import run_monte_carlo
from process_intelligence_engine.prediction import predict_single, get_input_ranges
from process_intelligence_engine.settings import get_settings_manager
from process_intelligence_engine.features.time_series import (
    compute_time_features,
    compute_consecutive_exceedance,
)
from process_intelligence_engine.copula import compute_joint_probabilities
from process_intelligence_engine.approval.workflow import APPROVAL_WORKFLOW


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
AUTH_MANAGER = AuthManager()
PROJECT_ENGINE = ProjectEngine()


class ExperimentRecord:
    """Immutable record of a single validation experiment run."""

    def __init__(
        self,
        experiment_id: str,
        model_id: str,
        planned_inputs: dict[str, float],
        actual_inputs: dict[str, float],
        predicted_output: float,
        actual_output: float,
        result: str,
        operator: str,
        notes: str,
        timestamp: str,
    ) -> None:
        self.experiment_id = experiment_id
        self.model_id = model_id
        self.planned_inputs = planned_inputs
        self.actual_inputs = actual_inputs
        self.predicted_output = predicted_output
        self.actual_output = actual_output
        self.prediction_error = actual_output - predicted_output
        self.result = result
        self.operator = operator
        self.notes = notes
        self.timestamp = timestamp


class ExperimentRegistry:
    """In-memory registry of validation experiment records."""

    def __init__(self) -> None:
        self._experiments: dict[str, ExperimentRecord] = {}
        self._lock = threading.Lock()

    def record(self, record: ExperimentRecord) -> str:
        with self._lock:
            self._experiments[record.experiment_id] = record
        return record.experiment_id

    def get(self, experiment_id: str) -> ExperimentRecord:
        with self._lock:
            if experiment_id not in self._experiments:
                raise KeyError(f"Unknown experiment_id: {experiment_id}")
            return self._experiments[experiment_id]

    def list_by_model(self, model_id: str) -> list[dict]:
        with self._lock:
            return [
                {
                    "experiment_id": e.experiment_id,
                    "model_id": e.model_id,
                    "planned_inputs": e.planned_inputs,
                    "actual_inputs": e.actual_inputs,
                    "predicted_output": e.predicted_output,
                    "actual_output": e.actual_output,
                    "prediction_error": e.prediction_error,
                    "result": e.result,
                    "operator": e.operator,
                    "notes": e.notes,
                    "timestamp": e.timestamp,
                }
                for e in self._experiments.values()
                if e.model_id == model_id
            ]

    def list_all(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "experiment_id": e.experiment_id,
                    "model_id": e.model_id,
                    "planned_inputs": e.planned_inputs,
                    "actual_inputs": e.actual_inputs,
                    "predicted_output": e.predicted_output,
                    "actual_output": e.actual_output,
                    "prediction_error": e.prediction_error,
                    "result": e.result,
                    "operator": e.operator,
                    "notes": e.notes,
                    "timestamp": e.timestamp,
                }
                for e in self._experiments.values()
            ]


EXPERIMENT_REGISTRY = ExperimentRegistry()


def _handle_experiment_record(params: dict) -> dict:
    """Record a validation experiment result."""
    import datetime

    experiment_id = str(uuid.uuid4())
    model_id = params["model_id"]
    planned_inputs = params.get("planned_inputs", {})
    actual_inputs = params.get("actual_inputs", {})
    predicted_output = float(params.get("predicted_output", 0))
    actual_output = float(params.get("actual_output", 0))
    result = params.get("result", "unknown")
    operator = params.get("operator", "anonymous")
    notes = params.get("notes", "")

    record = ExperimentRecord(
        experiment_id=experiment_id,
        model_id=model_id,
        planned_inputs=planned_inputs,
        actual_inputs=actual_inputs,
        predicted_output=predicted_output,
        actual_output=actual_output,
        result=result,
        operator=operator,
        notes=notes,
        timestamp=datetime.datetime.utcnow().isoformat() + "Z",
    )
    EXPERIMENT_REGISTRY.record(record)
    return {
        "experiment_id": experiment_id,
        "prediction_error": record.prediction_error,
        "result": result,
    }


def _handle_experiment_list(params: dict) -> dict:
    """List experiment records, optionally filtered by model_id."""
    model_id = params.get("model_id")
    if model_id:
        experiments = EXPERIMENT_REGISTRY.list_by_model(model_id)
    else:
        experiments = EXPERIMENT_REGISTRY.list_all()
    return {"experiments": experiments}


def _handle_experiment_get(params: dict) -> dict:
    """Get a single experiment record by ID."""
    experiment_id = params["experiment_id"]
    record = EXPERIMENT_REGISTRY.get(experiment_id)
    return {
        "experiment_id": record.experiment_id,
        "model_id": record.model_id,
        "planned_inputs": record.planned_inputs,
        "actual_inputs": record.actual_inputs,
        "predicted_output": record.predicted_output,
        "actual_output": record.actual_output,
        "prediction_error": record.prediction_error,
        "result": record.result,
        "operator": record.operator,
        "notes": record.notes,
        "timestamp": record.timestamp,
    }


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
    "logistic_regression": fit_logistic_regression,
    "weibull_regression": fit_weibull_regression,
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


def _handle_interactions_compute(params: dict) -> dict:
    model_id = params["model_id"]
    dataset_id = params["dataset_id"]
    threshold = params.get("threshold", 0.01)
    fit = MODEL_REGISTRY._get_unlocked(model_id)
    df = REGISTRY.get(dataset_id)
    return compute_interactions(fit, df, threshold)


def _handle_shap_explain(params: dict) -> dict:
    model_id = params["model_id"]
    dataset_id = params["dataset_id"]
    nsamples = params.get("nsamples", 100)
    fit = MODEL_REGISTRY._get_unlocked(model_id)
    df = REGISTRY.get(dataset_id)
    return compute_shap(fit, df, nsamples)


def _handle_extrapolation_check(params: dict) -> dict:
    dataset_id = params["dataset_id"]
    prediction_points = params.get("prediction_points", [])
    df = REGISTRY.get(dataset_id)
    return compute_extrapolation_risk(df, prediction_points)


def _handle_validation_analyze(params: dict) -> dict:
    model_id = params["model_id"]
    dataset_id = params["dataset_id"]
    k = params.get("k", 5)
    fit = MODEL_REGISTRY._get_unlocked(model_id)
    df = REGISTRY.get(dataset_id)

    cv_result = cross_validate(fit, df, k)
    residual_result = analyze_residuals(fit, df)
    interactions = {"significant_pairs": []}
    recommendations = recommend_experiments(fit, df, interactions)
    credibility = compute_credibility(fit, df)

    return {
        **cv_result,
        **residual_result,
        "recommendations": recommendations,
        "credibility": credibility,
    }


def _handle_validation_full(params: dict) -> dict:
    """Full validation: model comparison + experiment recommendation."""
    dataset_id = params["dataset_id"]
    model_ids = params.get("model_ids", [])
    k = params.get("k", 5)

    if not model_ids:
        model_ids = [mid for mid in MODEL_REGISTRY.list_ids()
                     if MODEL_REGISTRY._get_unlocked(mid).status in ("validated", "approved")]

    if len(model_ids) < 1:
        raise ValueError("No models to validate")

    df = REGISTRY.get(dataset_id)

    fits = [MODEL_REGISTRY._get_unlocked(mid) for mid in model_ids]

    comparison = compare_models(fits, df, k)

    best_fit = next(f for f in fits if f.model_id == comparison["best_model_id"])
    residual_analysis = analyze_residuals(best_fit, df)

    interactions = compute_interactions(best_fit, df)

    validation_result = {
        "residuals": residual_analysis["residuals"],
        "stats": residual_analysis["stats"],
    }
    exp_recommendation = recommend_experiments_full(best_fit, df, interactions, validation_result)

    credibility_per_model = {
        mid: compute_credibility(MODEL_REGISTRY._get_unlocked(mid), df)
        for mid in model_ids
    }

    return {
        **comparison,
        "residual_analysis": residual_analysis,
        "interaction_analysis": interactions,
        "experiment_recommendations": exp_recommendation,
        "credibility": credibility_per_model,
    }


def _handle_report_generate(params: dict) -> dict:
    """Generate a report from project data."""
    project_name = params.get("project_name", "Untitled Project")
    operator = params.get("operator", "Unknown")
    output_format = params.get("format", "html")  # html | pdf | excel

    dataset_id = params.get("dataset_id")
    if not dataset_id:
        raise ValueError("dataset_id is required")

    df = REGISTRY.get(dataset_id)

    model_ids = params.get("model_ids", [])
    model_comparison = []
    best_model = {}
    if model_ids:
        for mid in model_ids:
            try:
                fit = MODEL_REGISTRY._get_unlocked(mid)
                model_comparison.append({
                    "model_id": fit.model_id,
                    "model_type": fit.model_type,
                    "metrics": fit.metrics,
                    "status": fit.status,
                })
                if fit.status in ("validated", "approved"):
                    best_model = fit.to_dto()
            except Exception:
                pass

    fields_list = []
    if model_ids:
        for mid in model_ids:
            try:
                fit = MODEL_REGISTRY._get_unlocked(mid)
                for col in df.columns:
                    role = "metadata"
                    if col in fit.inputs:
                        role = "input"
                    elif col == fit.target:
                        role = "output"
                    fields_list.append({"name": col, "role": role})
                break
            except Exception:
                pass

    report_data = ReportData(
        project_name=project_name,
        operator=operator,
        dataset_id=dataset_id,
        row_count=len(df),
        column_count=len(df.columns),
        fields=fields_list,
        model_comparison=model_comparison,
        best_model=best_model,
    )

    if output_format == "html":
        generator = HTMLReportGenerator(report_data)
        result = generator.generate()
        return {"format": "html", "content": result}
    elif output_format == "pdf":
        generator = PDFReportGenerator(report_data)
        pdf_bytes = generator.generate()
        return {"format": "pdf", "content_base64": pdf_bytes.hex()}
    elif output_format == "excel":
        generator = ExcelReportGenerator(report_data)
        result = generator.generate()
        return {"format": "excel", "content_base64": result.hex()}
    else:
        raise ValueError(f"Unsupported format: {output_format}")


def _handle_doe_generate(params: dict) -> dict:
    return generate_design(
        factors=params["factors"],
        design_type=params["design_type"],
        params=params.get("params"),
    )


def _handle_auth_login(params: dict) -> dict:
    username = params.get("username", "")
    password = params.get("password", "")
    user = AUTH_MANAGER.authenticate(username, password)
    if user:
        return {"success": True, "username": user.username, "role": user.role.value}
    return {"success": False, "error": "Invalid credentials"}


def _handle_auth_logout(params: dict) -> dict:
    AUTH_MANAGER.logout()
    return {"success": True}


def _handle_auth_register(params: dict) -> dict:
    username = params.get("username", "")
    role = params.get("role", "viewer")
    try:
        user_role = UserRole(role)
    except ValueError:
        raise ValueError(f"Invalid role: {role}")
    user = AUTH_MANAGER.register_user(username, user_role)
    return {"success": True, "username": user.username, "role": user.role.value}


def _handle_audit_log(params: dict) -> dict:
    limit = params.get("limit", 100)
    return {"log": AUTH_MANAGER.get_audit_log(limit)}


def _handle_users_list(params: dict) -> dict:
    return {"users": AUTH_MANAGER.get_users()}


def _handle_current_user(params: dict) -> dict:
    user = AUTH_MANAGER.current_user
    if user:
        return {"username": user.username, "role": user.role.value}
    return {"username": None, "role": None}


def _handle_ai_chat(params: dict) -> dict:
    """Handle AI chat request."""
    mgr = get_settings_manager()
    provider = mgr._config.provider
    base_url = mgr._config.base_url
    model = mgr._config.model
    api_key = mgr._config.api_key
    messages = params.get("messages", [])

    try:
        if provider == "ollama":
            client = get_ollama_client()
            client.base_url = base_url
            client.model = model
            response = asyncio.run(client.chat(messages))
            return {"success": True, "response": response}
        else:
            import aiohttp
            url = f"{base_url.rstrip('/')}/chat/completions"
            payload = {"model": model, "messages": messages}
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"} if api_key else {"Content-Type": "application/json"}
            async def _chat():
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                        body = await resp.text()
                        if resp.status != 200:
                            raise Exception(f"HTTP {resp.status}: {body[:300]}")
                        data = await resp.json()
                        choices = data.get("choices", [])
                        if not choices:
                            return ""
                        msg = choices[0].get("message", {})
                        return msg.get("content", "")
            response = asyncio.run(_chat())
            return {"success": True, "response": response}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _handle_ai_models(params: dict) -> dict:
    """List available models from configured provider."""
    mgr = get_settings_manager()
    provider = mgr._config.provider
    base_url = mgr._config.base_url
    api_key = mgr._config.api_key

    try:
        if provider == 'ollama':
            client = get_ollama_client()
            models = asyncio.run(client.list_models())
            return {"success": True, "models": [m["name"] for m in models]}
        else:
            import aiohttp
            url = f"{base_url.rstrip('/')}/models"
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            async def _fetch():
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status != 200:
                            body = await resp.text()
                            raise Exception(f"HTTP {resp.status}: {body}")
                        data = await resp.json()
                        items = data.get("data", [])
                        return [m["id"] if "id" in m else m.get("model", m.get("id", "")) for m in items]
            models = asyncio.run(_fetch())
            return {"success": True, "models": models}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _handle_ai_health(params: dict) -> dict:
    """Check AI provider health."""
    mgr = get_settings_manager()
    provider = mgr._config.provider
    base_url = mgr._config.base_url
    api_key = mgr._config.api_key

    try:
        if provider == 'ollama':
            client = get_ollama_client()
            is_healthy = asyncio.run(client.health_check())
            return {"healthy": is_healthy}
        else:
            import aiohttp
            url = f"{base_url.rstrip('/')}/models"
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            async def _check():
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        return resp.status == 200
            return {"healthy": asyncio.run(_check())}
    except Exception as e:
        return {"healthy": False, "error": str(e)}


def _handle_settings_get(params: dict) -> dict:
    """Get current settings."""
    mgr = get_settings_manager()
    return {"config": mgr.get_config()}


def _handle_settings_update(params: dict) -> dict:
    """Update settings."""
    mgr = get_settings_manager()
    updates = params.get("config", {})
    mgr.update_config(updates)
    return {"success": True, "config": mgr.get_config()}


def _handle_settings_test(params: dict) -> dict:
    """Test connection to configured provider."""
    mgr = get_settings_manager()
    return mgr.test_connection()


def _handle_spc_analyze(params: dict) -> dict:
    """Analyze SPC control chart for a column."""
    df = REGISTRY.get(params["dataset_id"])
    column = params["column"]
    if column not in df.columns:
        raise KeyError(f"Unknown column: {column}")
    values = df[column].dropna().tolist()
    chart_type = params.get("chart_type", "i-mr")
    subgroup_size = params.get("subgroup_size", 1)
    lsl = params.get("lsl")
    usl = params.get("usl")

    def _chunk_subgroups(vals: list, size: int) -> list[list]:
        return [
            vals[i:i + size] for i in range(0, len(vals), size)
            if len(vals[i:i + size]) == size
        ]

    if chart_type == "i-mr":
        result = compute_i_mr(values, lsl=lsl, usl=usl)
    elif chart_type == "xbar-r":
        subgroups = _chunk_subgroups(values, subgroup_size)
        if not subgroups:
            raise ValueError("Not enough data points for requested subgroup_size")
        result = compute_xbar_r(subgroups, subgroup_size=subgroup_size, lsl=lsl, usl=usl)
    elif chart_type == "xbar-s":
        subgroups = _chunk_subgroups(values, subgroup_size)
        if not subgroups:
            raise ValueError("Not enough data points for requested subgroup_size")
        result = compute_xbar_s(subgroups, subgroup_size=subgroup_size, lsl=lsl, usl=usl)
    else:
        raise ValueError(f"Unknown chart_type: {chart_type}")

    result["chart_type"] = chart_type
    return {"success": True, **result}


def _handle_spc_capability(params: dict) -> dict:
    """Compute process capability for a column."""
    df = REGISTRY.get(params["dataset_id"])
    column = params["column"]
    if column not in df.columns:
        raise KeyError(f"Unknown column: {column}")
    values = df[column].dropna().tolist()
    lsl = params.get("lsl")
    usl = params.get("usl")
    subgroup_size = params.get("subgroup_size", 1)

    capability = compute_capability(values, lsl=lsl, usl=usl, subgroup_size=subgroup_size)
    return {"success": True, "capability": capability}


def _handle_monte_carlo_run(params: dict) -> dict:
    """Run Monte Carlo simulation."""
    did = params["dataset_id"]
    model_id = params["model_id"]
    df = REGISTRY.get(did)
    fit = MODEL_REGISTRY.get(model_id)

    if fit.model_type not in ("doe_linear", "doe_quadratic"):
        raise ValueError(f"Monte Carlo only supports doe_linear and doe_quadratic models, got {fit.model_type}")

    n_simulations = params.get("n_simulations", 10000)
    seed = params.get("seed", 42)
    enable_anomalies = params.get("enable_anomalies", False)
    anomalies = params.get("anomalies", [])
    lsl = params.get("lsl")
    usl = params.get("usl")

    result = run_monte_carlo(
        df=df,
        model_type=fit.model_type,
        coefficients=fit.coefficients or {},
        input_columns=fit.inputs,
        output_column=fit.target,
        n_simulations=n_simulations,
        seed=seed,
        enable_anomalies=enable_anomalies,
        anomalies=anomalies,
        lsl=lsl,
        usl=usl,
    )
    return {"success": True, "result": result}


def _handle_prediction_predict(params: dict) -> dict:
    """Predict output for given input values."""
    model_id = params["model_id"]
    fit = MODEL_REGISTRY.get(model_id)

    input_values = params.get("input_values", {})
    predicted = predict_single(fit.model_type, fit.coefficients or {}, input_values)

    return {
        "success": True,
        "predicted": float(predicted),
        "equation": fit.equation,
        "inputs": list(fit.inputs),
        "model_type": fit.model_type,
    }


def _handle_prediction_model_info(params: dict) -> dict:
    """Get model info for prediction UI."""
    model_id = params["model_id"]
    fit = MODEL_REGISTRY.get(model_id)

    return {
        "success": True,
        "model_type": fit.model_type,
        "inputs": list(fit.inputs),
        "coefficients": fit.coefficients or {},
        "equation": fit.equation,
        "n_train": fit.n_train,
        "target": fit.target,
    }


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

    if method == "modeling/doe/generate":
        return _handle_doe_generate(params)

    if method == "modeling/interactions/compute":
        return _handle_interactions_compute(params)

    if method == "modeling/shap/explain":
        return _handle_shap_explain(params)

    if method == "modeling/extrapolation/check":
        return _handle_extrapolation_check(params)

    if method == "modeling/validation/analyze":
        return _handle_validation_analyze(params)

    if method == "modeling/validation/full":
        return _handle_validation_full(params)

    if method == "report/generate":
        return _handle_report_generate(params)

    if method == "auth/login":
        return _handle_auth_login(params)
    if method == "auth/logout":
        return _handle_auth_logout(params)
    if method == "auth/register":
        return _handle_auth_register(params)
    if method == "audit/log":
        return _handle_audit_log(params)
    if method == "users/list":
        return _handle_users_list(params)
    if method == "auth/current":
        return _handle_current_user(params)

    if method == "ai/chat":
        return _handle_ai_chat(params)
    if method == "ai/models":
        return _handle_ai_models(params)
    if method == "ai/health":
        return _handle_ai_health(params)

    if method == "settings/get":
        return _handle_settings_get(params)
    if method == "settings/update":
        return _handle_settings_update(params)
    if method == "settings/test_connection":
        return _handle_settings_test(params)

    if method == "experiment/record":
        return _handle_experiment_record(params)
    if method == "experiment/list":
        return _handle_experiment_list(params)
    if method == "experiment/get":
        return _handle_experiment_get(params)

    if method == "approval/submit":
        return _handle_approval_submit(params)
    if method == "approval/approve":
        return _handle_approval_approve(params)
    if method == "approval/reject":
        return _handle_approval_reject(params)
    if method == "approval/status":
        return _handle_approval_status(params)
    if method == "approval/records":
        return _handle_approval_records(params)

    if method == "spc/analyze":
        return _handle_spc_analyze(params)
    if method == "spc/capability":
        return _handle_spc_capability(params)

    if method == "monte_carlo/run":
        return _handle_monte_carlo_run(params)

    if method == "prediction/predict":
        return _handle_prediction_predict(params)
    if method == "prediction/model_info":
        return _handle_prediction_model_info(params)
    if method == "prediction/scenario/save":
        return _handle_prediction_scenario_save(params)
    if method == "prediction/scenario/list":
        return _handle_prediction_scenario_list(params)
    if method == "prediction/scenario/delete":
        return _handle_prediction_scenario_delete(params)

    if method == "features/time_series":
        return _handle_time_series(params)
    if method == "features/consecutive_exceedance":
        return _handle_consecutive_exceedance(params)

    if method == "copula/joint":
        return _handle_copula_joint(params)

    if method == "data/grr":
        return _handle_grr(params)

    if method == "cloud/preview":
        return _handle_cloud_preview(params)
    if method == "cloud/upload":
        return _handle_cloud_upload(params)
    if method == "cloud/records":
        return _handle_cloud_records(params)

    if method == "project/manifest":
        return _handle_project_manifest(params)
    if method == "project/create":
        return _handle_project_create(params)
    if method == "project/open":
        return _handle_project_open(params)
    if method == "project/settings":
        return _handle_project_settings(params)
    if method == "project/dirs":
        return _handle_project_dirs(params)
    if method == "project/source-dirs":
        return _handle_project_source_dirs(params)
    if method == "project/scan":
        return _handle_project_scan(params)
    if method == "project/process-groups":
        return _handle_project_process_groups(params)
    if method == "project/process-group/create":
        return _handle_project_process_group_create(params)
    if method == "project/process-group/update":
        return _handle_project_process_group_update(params)
    if method == "project/process-group/delete":
        return _handle_project_process_group_delete(params)
    if method == "project/process-group-templates":
        return _handle_project_process_group_templates(params)
    if method == "project/process-nodes":
        return _handle_project_process_nodes(params)
    if method == "project/process-node/create":
        return _handle_project_process_node_create(params)
    if method == "project/process-node/update":
        return _handle_project_process_node_update(params)
    if method == "project/process-node/delete":
        return _handle_project_process_node_delete(params)
    if method == "project/datasets":
        return _handle_project_datasets(params)
    if method == "project/dataset/register":
        return _handle_project_dataset_register(params)
    if method == "project/dataset/update":
        return _handle_project_dataset_update(params)
    if method == "project/flow-graph":
        return _handle_project_flow_graph(params)
    if method == "project/flow-validate":
        return _handle_project_flow_validate(params)

    raise ValueError(f"Unknown method: {method}")


# ---------------------------------------------------------------------------
# Prediction scenarios (what-if save/load)
# ---------------------------------------------------------------------------

class ScenarioRecord:
    """A saved what-if prediction scenario."""

    def __init__(
        self,
        scenario_id: str,
        name: str,
        model_id: str,
        input_values: dict[str, float],
        predicted_output: float,
        operator: str,
        notes: str,
        timestamp: str,
    ) -> None:
        self.scenario_id = scenario_id
        self.name = name
        self.model_id = model_id
        self.input_values = input_values
        self.predicted_output = predicted_output
        self.operator = operator
        self.notes = notes
        self.timestamp = timestamp


SCENARIO_REGISTRY: dict[str, ScenarioRecord] = {}


def _handle_prediction_scenario_save(params: dict) -> dict:
    """Save a what-if prediction scenario."""
    import datetime as _dt

    scenario_id = str(uuid.uuid4())
    record = ScenarioRecord(
        scenario_id=scenario_id,
        name=params.get("name", "Untitled"),
        model_id=params["model_id"],
        input_values={k: float(v) for k, v in params.get("input_values", {}).items()},
        predicted_output=float(params.get("predicted_output", 0)),
        operator=params.get("operator", "anonymous"),
        notes=params.get("notes", ""),
        timestamp=_dt.datetime.utcnow().isoformat() + "Z",
    )
    SCENARIO_REGISTRY[scenario_id] = record
    return {"scenario_id": scenario_id, "name": record.name}


def _handle_prediction_scenario_list(params: dict) -> dict:
    """List saved scenarios, optionally filtered by model_id."""
    model_id = params.get("model_id")
    records = [
        {
            "scenario_id": s.scenario_id,
            "name": s.name,
            "model_id": s.model_id,
            "input_values": s.input_values,
            "predicted_output": s.predicted_output,
            "operator": s.operator,
            "notes": s.notes,
            "timestamp": s.timestamp,
        }
        for s in SCENARIO_REGISTRY.values()
        if model_id is None or s.model_id == model_id
    ]
    return {"scenarios": records}


def _handle_prediction_scenario_delete(params: dict) -> dict:
    """Delete a saved scenario."""
    scenario_id = params["scenario_id"]
    if scenario_id in SCENARIO_REGISTRY:
        del SCENARIO_REGISTRY[scenario_id]
        return {"deleted": True}
    return {"deleted": False}


# ---------------------------------------------------------------------------
# Time series features
# ---------------------------------------------------------------------------


def _handle_time_series(params: dict) -> dict:
    """Compute time-series features for a dataset column."""
    dataset_id = params.get("dataset_id")
    time_column = params["time_column"]
    value_columns = params["value_columns"]
    window_sizes = params.get("window_sizes", [3, 5, 10])

    if dataset_id:
        df = REGISTRY.get(dataset_id)
    else:
        columns = params["columns"]
        rows = params["rows"]
        data = {col: [] for col in columns}
        for row in rows:
            row = list(row) + [None] * (len(columns) - len(row))
            for col, value in zip(columns, row):
                data[col].append(value)
        df = pd.DataFrame(data)

    result = compute_time_features(df, time_column, value_columns, window_sizes)
    return _plain_types(result)


def _handle_consecutive_exceedance(params: dict) -> dict:
    """Compute consecutive exceedance counts for a dataset column."""
    dataset_id = params.get("dataset_id")
    value_column = params["value_column"]
    threshold = float(params["threshold"])
    direction = params.get("direction", "above")

    if dataset_id:
        df = REGISTRY.get(dataset_id)
    else:
        columns = params["columns"]
        rows = params["rows"]
        data = {col: [] for col in columns}
        for row in rows:
            row = list(row) + [None] * (len(columns) - len(row))
            for col, value in zip(columns, row):
                data[col].append(value)
        df = pd.DataFrame(data)

    result = compute_consecutive_exceedance(df, value_column, threshold, direction)
    return _plain_types(result)


# ---------------------------------------------------------------------------
# Approval workflow handlers
# ---------------------------------------------------------------------------


def _handle_approval_submit(params: dict) -> dict:
    return APPROVAL_WORKFLOW.submit_for_review(
        resource_type=params["resource_type"],
        resource_id=params["resource_id"],
        reviewer=params["reviewer"],
        reviewer_role=params["reviewer_role"],
        comments=params.get("comments", ""),
    )


def _handle_approval_approve(params: dict) -> dict:
    return APPROVAL_WORKFLOW.approve(
        resource_type=params["resource_type"],
        resource_id=params["resource_id"],
        reviewer=params["reviewer"],
        reviewer_role=params["reviewer_role"],
        comments=params.get("comments", ""),
    )


def _handle_approval_reject(params: dict) -> dict:
    return APPROVAL_WORKFLOW.reject(
        resource_type=params["resource_type"],
        resource_id=params["resource_id"],
        reviewer=params["reviewer"],
        reviewer_role=params["reviewer_role"],
        comments=params.get("comments", ""),
    )


def _handle_approval_status(params: dict) -> dict:
    return {
        "status": APPROVAL_WORKFLOW.get_status(
            params["resource_type"], params["resource_id"]
        )
    }


def _handle_approval_records(params: dict) -> dict:
    return {
        "records": APPROVAL_WORKFLOW.list_records(
            resource_type=params.get("resource_type"),
            resource_id=params.get("resource_id"),
        )
    }


def _handle_grr(params: dict) -> dict:
    """Run Gage R&R analysis on measurement data."""
    dataset_id = params.get("dataset_id")
    measurement_column = params["measurement_column"]
    part_column = params["part_column"]
    operator_column = params["operator_column"]

    if dataset_id:
        df = REGISTRY.get(dataset_id)
    else:
        columns = params["columns"]
        rows = params["rows"]
        data = {col: [] for col in columns}
        for row in rows:
            row = list(row) + [None] * (len(columns) - len(row))
            for col, value in zip(columns, row):
                data[col].append(value)
        df = pd.DataFrame(data)

    result = analyze_grr(df, measurement_column, part_column, operator_column)
    return _plain_types(result.to_dict())


def _handle_cloud_preview(params: dict) -> dict:
    """Generate a de-identification preview for cloud upload."""
    dataset_id = params["dataset_id"]
    df = REGISTRY.get(dataset_id)
    sensitive_columns = params.get("sensitive_columns", [])
    excluded_columns = params.get("excluded_columns", [])
    noise_std = float(params.get("noise_std", 0.0))
    seed = int(params.get("seed", 42))

    preview = generate_upload_preview(
        df, dataset_id, sensitive_columns, excluded_columns, noise_std, seed
    )
    return _plain_types(preview.to_dict())


def _handle_cloud_upload(params: dict) -> dict:
    """Confirm and record a cloud upload with de-identification."""
    dataset_id = params["dataset_id"]
    df = REGISTRY.get(dataset_id)
    sensitive_columns = params.get("sensitive_columns", [])
    excluded_columns = params.get("excluded_columns", [])
    noise_std = float(params.get("noise_std", 0.0))
    seed = int(params.get("seed", 42))
    operator = params.get("operator", "anonymous")
    provider = params.get("provider", "custom")
    model_version = params.get("model_version", "unknown")
    purpose = params.get("purpose", "")

    preview = generate_upload_preview(
        df, dataset_id, sensitive_columns, excluded_columns, noise_std, seed
    )
    record = record_upload(operator, provider, model_version, preview, purpose)

    return _plain_types({
        "record_id": record.record_id,
        "upload_hash": record.upload_hash,
        "row_count": record.row_count,
        "columns_uploaded": record.columns_uploaded,
        "masked_columns": preview.masked_columns,
        "excluded_columns": preview.excluded_columns,
    })


def _handle_cloud_records(params: dict) -> dict:
    """List cloud upload records."""
    dataset_id = params.get("dataset_id")
    operator = params.get("operator")
    records = list_upload_records(dataset_id, operator)
    return {"records": records}


# ---------------------------------------------------------------------------
# Project manifest (spec 11A)
# ---------------------------------------------------------------------------


def _handle_project_manifest(params: dict) -> dict:
    return PROJECT_ENGINE.get_manifest()


def _handle_project_create(params: dict) -> dict:
    root = params["root"]
    name = params.get("name", "Untitled")
    operator = params.get("operator", "anonymous")
    return PROJECT_ENGINE.create_project(root, name, operator)


def _handle_project_open(params: dict) -> dict:
    root = params["root"]
    return PROJECT_ENGINE.open_project(root)


def _handle_project_settings(params: dict) -> dict:
    updates = params.get("updates", {})
    return PROJECT_ENGINE.update_settings(updates)


def _handle_project_dirs(params: dict) -> dict:
    return PROJECT_ENGINE.get_directories()


def _handle_project_source_dirs(params: dict) -> dict:
    return PROJECT_ENGINE.list_source_dirs()


def _handle_project_scan(params: dict) -> dict:
    directory_path = params["directory_path"]
    return PROJECT_ENGINE.scan_source_dir(directory_path)


def _handle_project_process_groups(params: dict) -> dict:
    PROJECT_ENGINE._ensure_project()
    manifest = PROJECT_ENGINE._load()
    return {"process_groups": [g.to_dict() for g in manifest.process_groups]}


def _handle_project_process_group_create(params: dict) -> dict:
    return PROJECT_ENGINE.create_process_group(
        display_name=params["display_name"],
        directory_name=params["directory_name"],
        description=params.get("description", ""),
        input_templates=params.get("input_templates", []),
        output_templates=params.get("output_templates", []),
        quality_label_templates=params.get("quality_label_templates", []),
        unit_profile=params.get("unit_profile", {}),
    )


def _handle_project_process_group_update(params: dict) -> dict:
    return PROJECT_ENGINE.update_process_group(params["process_group_id"], params.get("updates", {}))


def _handle_project_process_group_delete(params: dict) -> dict:
    deleted = PROJECT_ENGINE.delete_process_group(params["process_group_id"])
    return {"deleted": deleted}


def _handle_project_process_group_templates(params: dict) -> dict:
    return {"templates": _PROCESS_GROUP_TEMPLATES}


def _handle_project_process_nodes(params: dict) -> dict:
    PROJECT_ENGINE._ensure_project()
    manifest = PROJECT_ENGINE._load()
    return {"process_nodes": [n.to_dict() for n in manifest.process_nodes]}


def _handle_project_process_node_create(params: dict) -> dict:
    return PROJECT_ENGINE.create_process_node(
        display_name=params["display_name"],
        node_type=params["node_type"],
        sequence_or_edges=params.get("sequence_or_edges", []),
        input_data_sources=params.get("input_data_sources", []),
        rework_policy=params.get("rework_policy", "default"),
    )


def _handle_project_process_node_update(params: dict) -> dict:
    return PROJECT_ENGINE.update_process_node(params["process_node_id"], params.get("updates", {}))


def _handle_project_process_node_delete(params: dict) -> dict:
    deleted = PROJECT_ENGINE.delete_process_node(params["process_node_id"])
    return {"deleted": deleted}


def _handle_project_datasets(params: dict) -> dict:
    PROJECT_ENGINE._ensure_project()
    return {"datasets": PROJECT_ENGINE.list_datasets()}


def _handle_project_dataset_register(params: dict) -> dict:
    return PROJECT_ENGINE.register_dataset(
        source_path=params["source_path"],
        dataset_id=params.get("dataset_id"),
        format=params.get("format", "csv"),
        row_count=params.get("row_count", 0),
        column_count=params.get("column_count", 0),
        partition_keys=params.get("partition_keys", []),
        time_range=params.get("time_range"),
        quality_status=params.get("quality_status", "unknown"),
    )


def _handle_project_dataset_update(params: dict) -> dict:
    result = PROJECT_ENGINE.update_dataset(params["dataset_id"], params.get("updates", {}))
    return result or {"error": "dataset not found"}


def _handle_project_flow_graph(params: dict) -> dict:
    return PROJECT_ENGINE.get_flow_graph()


def _handle_project_flow_validate(params: dict) -> dict:
    return PROJECT_ENGINE.validate_flow_graph()


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