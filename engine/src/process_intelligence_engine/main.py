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
import math
import sys
import asyncio
import threading
import traceback
import uuid
import hashlib
from copy import deepcopy

import numpy as np
import pandas as pd
from process_intelligence_engine.project.session import save_dataset, load_dataset, prediction_check, rebuild_model

from process_intelligence_engine.analysis.anomalies import (
    build_analysis_package,
    detect_anomaly_scenarios,
    register_anomaly_event,
)
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
from process_intelligence_engine.modeling.validation import cross_validate, analyze_residuals, recommend_experiments, compute_credibility, compute_doe_statistics
from process_intelligence_engine.modeling.model_selection import compare_models
from process_intelligence_engine.modeling.experiment_recommendation import recommend_experiments as recommend_experiments_full
from process_intelligence_engine.modeling.fitters import (
    fit_doe_linear,
    fit_doe_quadratic,
    fit_random_forest,
    fit_residual_hybrid,
    fit_logistic_regression,
    fit_weibull_regression,
    fit_xgboost,
    fit_lightgbm,
)
from process_intelligence_engine.modeling.doe import generate_design
from process_intelligence_engine.modeling.registry import ModelRegistry
from process_intelligence_engine.reporting.models import ReportData
from process_intelligence_engine.reporting.registry import _REPORT_REGISTRY as REPORT_REGISTRY
from process_intelligence_engine.reporting.html import HTMLReportGenerator
from process_intelligence_engine.reporting.excel import ExcelReportGenerator
from process_intelligence_engine.reporting.pdf import PDFReportGenerator
from process_intelligence_engine.auth.models import UserRole, AuditAction
from process_intelligence_engine.auth.manager import AuthManager
from process_intelligence_engine.ai.ollama_client import get_ollama_client
from process_intelligence_engine.ai.context import build_assistant_context
from process_intelligence_engine.ai.contracts import AssistantRequest
from process_intelligence_engine.ai.orchestrator import AssistantOrchestrator
from process_intelligence_engine.project.manifest import ProjectManifest
from process_intelligence_engine.spc import (
    compute_i_mr,
    compute_xbar_r,
    compute_xbar_s,
    compute_capability,
    compute_ewma,
    compute_cusum,
    compute_spc_suggestions,
)
from process_intelligence_engine.monte_carlo import run_monte_carlo
from process_intelligence_engine.prediction import predict_single, get_input_ranges, SUPPORTED_MODELS
from process_intelligence_engine.settings import get_settings_manager
from process_intelligence_engine.features.time_series import (
    compute_time_features,
    compute_consecutive_exceedance,
)
from process_intelligence_engine.copula import compute_joint_probabilities
from process_intelligence_engine.approval.workflow import APPROVAL_WORKFLOW
from process_intelligence_engine.versioning.chain import VersionChain
from process_intelligence_engine.modeling.governance import (
    check_model_applicability,
    check_doeb_ai_discrepancy,
    recommend_models,
    compute_experiment_verdict,
    update_model_after_experiment,
    recommend_next_experiment,
)
from process_intelligence_engine.gates.manager import GateManager


def _plain_types(value):
    """Recursively convert numpy/pandas scalars to JSON-native types.

    Engine internals legitimately produce numpy ints/floats; this keeps the
    entire IPC contract JSON-serializable regardless of which layer leaks a
    numpy value.
    """
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        result = value.item()
        if isinstance(result, float) and not math.isfinite(result):
            return None
        return result
    if isinstance(value, np.ndarray):
        return _plain_types(value.tolist())
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _plain_types(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_types(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
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
_PROJECT_ROOT = "/tmp/default-project"
_VERSION_CHAIN = VersionChain(_PROJECT_ROOT, "anonymous")
GATE_MANAGER = GateManager(project_root=_PROJECT_ROOT, project_id="default")
_ASSISTANT_STATE = None
try:
    _VERSION_CHAIN.load()
except Exception:
    # A corrupt/cross-version state file must never prevent engine startup.
    import traceback
    print(f"[engine] version_chain.load() failed at startup: {traceback.format_exc()}", file=sys.stderr)


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
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    EXPERIMENT_REGISTRY.record(record)
    exp_chain_id = _VERSION_CHAIN.register_entity(
        entity_type="experiment",
        project_id="default",
        metadata={
            "model_id": model_id,
            "dataset_id": params.get("dataset_id", ""),
            "predicted_output": predicted_output,
            "actual_output": actual_output,
            "record": vars(record).copy(),
        },
        created_by=operator,
    )
    return {
         "experiment_id": experiment_id,
         "prediction_error": record.prediction_error,
         "result": result,
         "chain_entity_id": exp_chain_id,
     }


def _handle_experiment_record_with_verdict(params: dict) -> dict:
    """Record experiment with automatic verdict computation."""
    predicted = float(params.get("predicted_output", 0))
    actual = float(params.get("actual_output", 0))
    fit = MODEL_REGISTRY.get(params["model_id"])
    tolerance = params.get("tolerance")
    rmse = params.get("rmse", fit.metrics.get("rmse"))
    binary = fit.model_type == "logistic_regression"
    verdict = compute_experiment_verdict(predicted, actual, tolerance,
        spec_range=params.get("spec_range"), rmse=rmse, is_classification=binary,
        accuracy=params.get("accuracy"), recall=params.get("recall"))
    exp_result = _handle_experiment_record({**params, "result": verdict})
    model_entities = [e for e in _VERSION_CHAIN.get_chain_summary() if e["entity_type"] == "model"
                      and _VERSION_CHAIN.get_entity(e["entity_id"]).metadata.get("model_id") == fit.model_id]
    if model_entities:
        model_entity_id = model_entities[-1]["entity_id"]
        _VERSION_CHAIN.add_link(exp_result["chain_entity_id"], model_entity_id, "tests_model")
        _VERSION_CHAIN.add_claim(model_entity_id, "experiment_verdict", verdict,
            [exp_result["chain_entity_id"]], "historical_observation", "unverified")
    GATE_MANAGER.reset("validation", "New experiment requires review")

    return {
        **exp_result,
        "verdict": verdict,
        "prediction_error": abs(actual - predicted),
    }


def _handle_experiment_suggest_next(params: dict) -> dict:
    """Recommend next experiment conditions."""
    model_id = params["model_id"]
    n_suggestions = params.get("n_suggestions", 3)
    dataset_id = params.get("dataset_id")
    if not dataset_id:
        for item in reversed(_VERSION_CHAIN.get_chain_summary()):
            entity = _VERSION_CHAIN.get_entity(item["entity_id"])
            if entity.entity_type == "model" and entity.metadata.get("model_id") == model_id:
                dataset_id = entity.metadata.get("dataset_id")
                break

    df = None
    if dataset_id:
        df = REGISTRY.get(dataset_id)

    suggestions = recommend_next_experiment(model_id, df, n_suggestions)
    return {"suggestions": suggestions}


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
            "metadata_columns": [c for c in result.columns if c in {
                "measurement_id", "product_id", "lot_id", "machine_id", "station_id",
                "process_step", "timestamp", "subgroup_id", "metric", "unit",
            }],
        },
    )
    dto = result.to_dto()
    dto["dataset_id"] = dataset_id
    checksum = save_dataset(_VERSION_CHAIN._project_root, dataset_id, df)
    dataset_chain_id = _VERSION_CHAIN.register_entity(
        entity_type="dataset",
        project_id="default",
        metadata={
            "dataset_id": dataset_id,
            "source_file": result.file_path,
            "row_count": result.row_count,
            "column_count": result.column_count,
            "metadata_columns": [c for c in result.columns if c in {
                "measurement_id", "product_id", "lot_id", "machine_id", "station_id",
                "process_step", "timestamp", "subgroup_id", "metric", "unit",
            }],
            "import_result": dto.copy(),
        },
        created_by=params.get("operator", "anonymous"),
        content_hash=checksum,
    )
    dto["chain_entity_id"] = dataset_chain_id
    for module in GATE_MANAGER.ALL_MODULES:
        GATE_MANAGER.reset(module, "Dataset imported; review current analysis")
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
        input_columns=params.get("input_columns", []),
        output_columns=params.get("output_columns", []),
        input_ranges=params.get("input_ranges"),
        spec=params.get("spec"),
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


def _apply_row_filter(df, params):
    filter_column = params.get("filter_column")
    filter_value = params.get("filter_value")
    if filter_column:
        if filter_column not in df.columns:
            raise KeyError(f"Unknown filter column: {filter_column}")
        if filter_value is None or filter_value == "":
            raise ValueError("filter_value is required when filter_column is set")
        df = df[df[filter_column].astype(str) == str(filter_value)]
        if df.empty:
            raise ValueError("No rows match filter")
    return df


def _handle_distribution(params: dict) -> dict:
    """Fit distributions for a registered dataset column."""
    if params.get("dataset_id"):
        df = REGISTRY.get(params["dataset_id"])
        column = params["column"]
        df = _apply_row_filter(df, params)
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

    df = _apply_row_filter(df, params)

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
    "xgboost": fit_xgboost,
    "lightgbm": fit_lightgbm,
}


def _handle_modeling_fit(params: dict) -> dict:
    df = REGISTRY.get(params["dataset_id"])
    model_type = params["model_type"]
    target = params["target"]
    inputs = list(params.get("inputs", []))
    fitter = MODEL_FITTERS.get(model_type)
    if fitter is None:
        raise ValueError(f"Unknown model_type: {model_type}")
    governance_warnings = check_model_applicability(df, target, inputs, is_binary=model_type == "logistic_regression")

    # Extract hyperparameters (pass-through for tree models)
    hyperparams: dict = {}
    for key in ("n_estimators", "max_depth", "min_samples_leaf", "learning_rate",
                "auto_select_features", "importance_threshold", "max_features"):
        if key in params:
            hyperparams[key] = params[key]
    # Also pass common params
    for key in ("test_size", "random_state"):
        if key in params:
            hyperparams[key] = params[key]
    hyperparams = {k: v for k, v in hyperparams.items() if v is not None}
    hyperparams.setdefault("random_state", 42)

    fit = fitter(df, target=target, inputs=inputs, **hyperparams)
    MODEL_REGISTRY.register(fit)
    model_chain_id = _VERSION_CHAIN.register_entity(
        entity_type="model",
        project_id="default",
        metadata={
            "model_type": model_type,
            "model_id": fit.model_id,
            "dataset_id": params["dataset_id"],
            "target": target,
            "inputs": inputs,
            "n_train": int(fit.n_train) if hasattr(fit, 'n_train') else 0,
            "n_test": int(fit.n_test) if hasattr(fit, 'n_test') else 0,
            "governance_warnings": governance_warnings,
            "recipe": hyperparams,
            "training_inputs": inputs,
            "fit_snapshot": fit.to_dto(),
            "prediction_check": prediction_check(fit, df),
        },
        created_by=params.get("operator", "anonymous"),
        parameters_hash=hashlib.sha256(json.dumps(hyperparams, sort_keys=True).encode()).hexdigest(),
        parent_ids=[e.entity_id for e in _report_entities(params["dataset_id"], [])],
    )
    result_dict = fit.to_dto()
    result_dict["chain_entity_id"] = model_chain_id
    result_dict["governance_warnings"] = governance_warnings
    for module in ("modeling", "monte_carlo", "prediction", "validation"):
        GATE_MANAGER.reset(module, "Model fitted; review current analysis")
    return result_dict


def _handle_modeling_list(params: dict) -> dict:
    return {
        "models": [MODEL_REGISTRY.get(mid).to_dto() for mid in MODEL_REGISTRY.list_ids()]
    }


def _handle_modeling_transition(params: dict) -> dict:
    fit = MODEL_REGISTRY.transition(params["model_id"], params["status"])
    _VERSION_CHAIN.register_entity("model_state", "default", {"model_id": fit.model_id, "status": fit.status})
    return fit.to_dto()


def _handle_modeling_delete(params: dict) -> dict:
    """Delete a model from the registry."""
    model_id = params["model_id"]
    MODEL_REGISTRY.delete(model_id)
    return {"success": True, "model_id": model_id}


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
    max_explain = params.get("max_explain", 1000)
    fit = MODEL_REGISTRY._get_unlocked(model_id)
    df = REGISTRY.get(dataset_id)
    return compute_shap(fit, df, nsamples, max_explain)


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


def _handle_stats_compute(params: dict) -> dict:
    """Compute ANOVA and coefficient p-values for DOE models."""
    model_id = params["model_id"]
    dataset_id = params["dataset_id"]
    fit = MODEL_REGISTRY.get(model_id)
    df = REGISTRY.get(dataset_id)
    result = compute_doe_statistics(fit, df)
    return {"success": True, "statistics": result}


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


def _report_entities(dataset_id: str, model_ids: list[str]) -> list:
    """Resolve only the requested runtime IDs; never guess legacy mappings."""
    selected = []
    for item in _VERSION_CHAIN.get_chain_summary():
        entity = _VERSION_CHAIN.get_entity(item["entity_id"])
        meta = entity.metadata
        if entity.entity_type == "dataset" and meta.get("dataset_id") == dataset_id:
            selected.append(entity)
        elif (entity.entity_type == "model" and meta.get("dataset_id") == dataset_id
              and meta.get("model_id") in model_ids):
            selected.append(entity)
    return selected


def _handle_report_generate(params: dict) -> dict:
    """Generate a report from project data.

    Covers the full 14-section report specification (spec 17.2). Each
    analysis section is assembled defensively so a missing/invalid piece
    degrades that section only, never the whole report.
    """
    project_name = params.get("project_name", "Untitled Project")
    operator = params.get("operator", "Unknown")
    output_format = params.get("format", "html")  # html | pdf | excel
    if output_format not in ("html", "pdf", "excel"):
        raise ValueError(f"Unsupported format: {output_format}")

    dataset_id = params.get("dataset_id")
    if not dataset_id:
        raise ValueError("dataset_id is required")

    df = REGISTRY.get(dataset_id)
    source_row_count = len(df)
    report_filter_column = params.get("filter_column")
    report_filter_value = params.get("filter_value")
    if report_filter_column:
        df = _apply_row_filter(df, params)
    meta = REGISTRY.meta(dataset_id)

    spec = params.get("spec") or {}
    lsl = params.get("lsl")
    usl = params.get("usl")
    runs_length = int(params.get("runs_length", 5))

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
        if not best_model and model_comparison:
            best_model = MODEL_REGISTRY._get_unlocked(model_ids[0]).to_dto()

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

    # ---- Section assembly (defensive: each independent) -------------------
    quality_summary = {}
    try:
        q = run_quality_checks(df)
        quality_summary = {
            "row_count": q.row_count,
            "column_count": q.column_count,
            "issue_count": len(q.issues),
            "issues_by_severity": {
                k: int(v) for k, v in q.issues_by_severity().items()
            },
            "issues": [
                {
                    "check": i.check.value,
                    "column": i.column,
                    "severity": i.severity.value,
                    "message": i.message,
                    "detail": i.detail,
                }
                for i in q.issues
            ],
        }
    except Exception:
        pass

    time_range = {}
    try:
        num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    except Exception:
        num_cols = []

    distribution_fits = {}
    try:
        for col in num_cols:
            vals = df[col].dropna().tolist()
            if len(vals) < 5:
                continue
            fits = fit_best_distribution(vals, top_n=1)
            if fits:
                f = fits[0]
                distribution_fits[col] = [{
                    "name": f.name,
                    "params": f.params,
                    "aic": f.aic,
                    "ks_p_value": f.ks_p_value,
                    "skewness": f.skewness,
                    "kurtosis": f.kurtosis,
                    "histogram": f.histogram,
                    "pdf": f.pdf,
                }]
    except Exception:
        pass

    anomalies = []
    try:
        scenarios = detect_anomaly_scenarios(df, spec=spec, runs_length=runs_length)
        anomalies = [s.to_dto() for s in scenarios]
    except Exception:
        pass

    interactions = {}
    credibility = {}
    recommendations = []
    process_window = {}
    monte_carlo_result = {}
    if best_model:
        try:
            interactions = compute_interactions(MODEL_REGISTRY._get_unlocked(best_model["model_id"]), df)
        except Exception:
            pass
        try:
            credibility = compute_credibility(MODEL_REGISTRY._get_unlocked(best_model["model_id"]), df)
        except Exception:
            pass
        try:
            rec = recommend_experiments_full(MODEL_REGISTRY._get_unlocked(best_model["model_id"]), df, interactions, {})
            recommendations = rec.get("recommendations", []) if isinstance(rec, dict) else []
        except Exception:
            pass
        try:
            window = _proposed_process_window(df, best_model)
            if window:
                process_window = window
        except Exception:
            pass
        try:
            mc = run_monte_carlo(
                df=df,
                model_type=best_model["model_type"],
                coefficients=best_model.get("coefficients") or {},
                input_columns=best_model.get("inputs") or [],
                output_column=best_model.get("target", ""),
                n_simulations=int(params.get("n_simulations", 10000)),
                seed=int(params.get("seed", 42)),
                enable_anomalies=bool(params.get("enable_anomalies", False)),
                anomalies=anomalies,
                lsl=lsl,
                usl=usl,
            )
            monte_carlo_result = {
                k: v for k, v in mc.items() if k != "output_values"
            }
        except Exception:
            pass

    # SPC analysis
    spc_results = []
    try:
        from process_intelligence_engine.spc import compute_i_mr, compute_spc_suggestions
        output_cols = [f['name'] for f in fields_list if f.get('role') == 'output']
        if not output_cols:
            output_cols = num_cols[:1]
        for col in output_cols:
            values = df[col].dropna().tolist()
            if len(values) < 5:
                continue
            r = compute_i_mr(values, lsl=lsl, usl=usl)
            suggestions = compute_spc_suggestions(r)
            spc_results.append({
                "column": col,
                "chart_type": r["chart_type"],
                "n_points": len(values),
                "x_mean": r["control_limits"]["x"]["cl"],
                "x_ucl": r["control_limits"]["x"]["ucl"],
                "x_lcl": r["control_limits"]["x"]["lcl"],
                "mr_ucl": r["control_limits"]["mr"]["ucl"],
                "mr_mean": r["control_limits"]["mr"]["cl"],
                "violations": len(r["violations"]),
                "capability": r.get("capability"),
                "suggestions": suggestions,
                "x_values": r["x_values"],
                "mr_values": r["mr_values"],
            })
    except Exception:
        pass

    # Resolve the actual report inputs, excluding unrelated project evidence.
    evidence = _report_entities(dataset_id, model_ids)
    if monte_carlo_result:
        simulation_id = _VERSION_CHAIN.register_entity(
            "simulation", "default",
            {"dataset_id": dataset_id, "model_id": best_model.get("model_id"),
             "seed": int(params.get("seed", 42)),
             "n_simulations": int(params.get("n_simulations", 10000)),
             "spec": _spec_serializable(spec, lsl, usl),
             "result": monte_carlo_result},
            created_by=operator, parent_ids=[e.entity_id for e in evidence],
        )
        evidence.append(_VERSION_CHAIN.get_entity(simulation_id))
        GATE_MANAGER.reset("monte_carlo", "Report generated a new simulation")
    selected_ids = {e.entity_id for e in evidence}
    chain_summary = [e for e in _VERSION_CHAIN.get_chain_summary()
                     if e["entity_id"] in selected_ids]
    dataset_trace = next((_VERSION_CHAIN.get_trace(e.entity_id) for e in evidence
                          if e.entity_type == "dataset"), {})
    chain_trace = {"steps": [
        {"step": e["entity_type"], "entity_id": e["entity_id"],
         "operator": e["created_by"], "timestamp": e["created_at"],
         "status": e["evidence_status"]}
        for e in chain_summary
    ], "dataset": dataset_trace}
    gate_summary = GATE_MANAGER.get_summary()
    unconfirmed_items = [m for m, s in gate_summary.items() if s != "confirmed"]
    report_claims: dict = {"claims": []}
    for entry in chain_summary:
        try:
            entity_id = entry["entity_id"]
            claims = _VERSION_CHAIN.get_claims(entity_id)
            if claims:
                report_claims["claims"].extend(claims)
        except KeyError:
            pass

    # Confirmation makes a report eligible for review, never auto-approved.
    report_status, approved_by, approved_at = "draft", "", ""

    report_data = ReportData(
        project_name=project_name,
        operator=operator,
        dataset_id=dataset_id,
        source_file=meta.get("file_path", ""),
        row_count=len(df),
        column_count=len(df.columns),
        time_range=time_range,
        fields=fields_list,
        spec=_spec_serializable(spec, lsl, usl),
        quality_summary=quality_summary,
        distribution_fits=distribution_fits,
        anomalies=anomalies,
        model_comparison=model_comparison,
        best_model=best_model,
        interactions=interactions,
        monte_carlo=monte_carlo_result,
        credibility=credibility,
        recommendations=recommendations,
        process_window=process_window,
        spc_results=spc_results,
        chain_trace=chain_trace,
        gate_summary=gate_summary,
        approval_record=report_claims,
        unconfirmed_items=unconfirmed_items,
        extrapolation_summary={},
        version_chain_summary=chain_summary,
        report_status=report_status,
        approved_by=approved_by,
        approved_at=approved_at,
    )

    from dataclasses import asdict
    snapshot = json.dumps(_plain_types(asdict(report_data)), default=str)
    rep_chain_id = _VERSION_CHAIN.register_entity(
        entity_type="report",
        project_id="default",
        metadata={
            "model_id": model_ids[0] if model_ids else "",
            "project_name": project_name,
            "model_ids": model_ids,
            "dataset_id": dataset_id,
            "format": output_format,
            "report_status": "draft",
            "has_simulation": bool(monte_carlo_result),
            "grain": {
                "filter_column": report_filter_column,
                "filter_value": report_filter_value,
                "source_row_count": source_row_count,
                "analyzed_row_count": len(df),
            },
        },
        created_by=operator,
        parent_ids=[e.entity_id for e in evidence],
        content_hash=hashlib.sha256(snapshot.encode()).hexdigest(),
    )
    REPORT_REGISTRY.register(project_name, operator, output_format, report_id=rep_chain_id,
                             metadata={"dataset_id": dataset_id, "grain": {
                                 "filter_column": report_filter_column,
                                 "filter_value": report_filter_value,
                                 "source_row_count": source_row_count,
                                 "analyzed_row_count": len(df),
                             }})
    path = _VERSION_CHAIN._project_root / "reports" / f"{rep_chain_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(snapshot, encoding="utf-8")
    return _render_saved_report(report_data, output_format, rep_chain_id)


def _render_saved_report(data, output_format, entity_id):
    import base64
    generators = {"html": HTMLReportGenerator, "pdf": PDFReportGenerator, "excel": ExcelReportGenerator}
    if output_format not in generators:
        raise ValueError(f"Unsupported format: {output_format}")
    content = generators[output_format](data).generate()
    result = {"format": output_format, "chain_entity_id": entity_id, "report_status": data.report_status}
    entity = _VERSION_CHAIN.get_entity(entity_id)
    if entity is not None:
        result["report_metadata"] = {
            "dataset_id": entity.metadata.get("dataset_id"),
            "grain": entity.metadata.get("grain"),
            "format": output_format,
            "status": data.report_status,
        }
    result["content" if output_format == "html" else "content_base64"] = content if output_format == "html" else base64.b64encode(content).decode("ascii")
    return result


def _handle_report_export(params):
    entity = _VERSION_CHAIN.get_entity(params["report_id"])
    if entity.entity_type != "report":
        raise ValueError("Expected report ID")
    path = _VERSION_CHAIN._project_root / "reports" / f"{entity.entity_id}.json"
    from datetime import datetime
    snapshot = path.read_text(encoding="utf-8")
    if hashlib.sha256(snapshot.encode()).hexdigest() != entity.content_hash:
        raise ValueError("Report snapshot checksum mismatch")
    saved = json.loads(snapshot)
    saved["created_at"] = datetime.fromisoformat(saved["created_at"])
    data = ReportData(**saved)
    data.report_status = APPROVAL_WORKFLOW.get_status("report", entity.entity_id)
    if data.report_status == "approved":
        approvals = [r for r in APPROVAL_WORKFLOW.list_records("report", entity.entity_id) if r["action"] == "approve"]
        if not approvals:
            raise ValueError("Missing approval evidence")
        data.approved_by = approvals[-1]["reviewer"]
        data.approved_at = approvals[-1]["timestamp"]
        data.approval_record = {**(data.approval_record or {}), "approval": approvals[-1]}
    return _render_saved_report(data, params.get("format", "html"), entity.entity_id)


def _handle_report_list(params: dict) -> dict:
    return {"reports": REPORT_REGISTRY.list()}


def _spec_serializable(spec: dict, lsl, usl) -> dict:
    """Normalize spec into a JSON-serializable form, merging explicit LSL/USL."""
    out: dict = {}
    for k, v in spec.items():
        if k == "limits" and isinstance(v, dict):
            out["limits"] = {
                subk: (float(subv) if isinstance(subv, (int, float)) else subv)
                for subk, subv in v.items()
            }
        else:
            out[str(k)] = v
    if lsl is not None or usl is not None:
        limits = dict(out.get("limits") or {})
        if lsl is not None:
            limits["lsl"] = float(lsl)
        if usl is not None:
            limits["usl"] = float(usl)
        out["limits"] = limits
    return out


def _proposed_process_window(df: pd.DataFrame, best_model: dict) -> dict:
    """Derive a suggested process window from data stats around the model inputs."""
    limits = {}
    for col in best_model.get("inputs") or []:
        if col not in df.columns:
            continue
        series = df[col].dropna()
        if len(series) == 0 or not pd.api.types.is_numeric_dtype(series):
            continue
        mean = float(series.mean())
        std = float(series.std()) if len(series) > 1 else 0.0
        if std and std > 0:
            limits[col] = {
                "min": round(mean - 3 * std, 4),
                "max": round(mean + 3 * std, 4),
                "center": round(mean, 4),
            }
    if not limits:
        return {}
    return {"column_limits": limits, "basis": "mean +/- 3 sigma"}


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
    source_row_count = len(df)
    df = _apply_row_filter(df, params)
    column = params["column"]
    if column not in df.columns:
        raise KeyError(f"Unknown column: {column}")
    values = df[column].dropna().tolist()
    chart_type = params.get("chart_type", "i-mr")
    subgroup_size = params.get("subgroup_size", 1)
    lsl = params.get("lsl")
    usl = params.get("usl")
    manual_limits = (params.get("control_limits") or {}).get(column)

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
    elif chart_type == "ewma":
        result = compute_ewma(
            values,
            lambda_param=params.get("ewma_lambda", 0.2),
            L=params.get("ewma_L", 3.0),
            lsl=lsl,
            usl=usl,
        )
    elif chart_type == "cusum":
        result = compute_cusum(
            values,
            k=params.get("cusum_k", 0.5),
            H=params.get("cusum_H", 5.0),
            lsl=lsl,
            usl=usl,
        )
    else:
        raise ValueError(f"Unknown chart_type: {chart_type}")

    result["chart_type"] = chart_type

    # Apply manual control limits override when provided for this column
    if manual_limits:
        if "ucl" in manual_limits and manual_limits["ucl"] is not None:
            if "control_limits" in result and "x" in result["control_limits"]:
                result["control_limits"]["x"]["ucl"] = float(manual_limits["ucl"])
            result["ucl"] = float(manual_limits["ucl"])
        if "lcl" in manual_limits and manual_limits["lcl"] is not None:
            if "control_limits" in result and "x" in result["control_limits"]:
                result["control_limits"]["x"]["lcl"] = float(manual_limits["lcl"])
            result["lcl"] = float(manual_limits["lcl"])

    # Detect outliers and change points
    from process_intelligence_engine.spc import detect_outliers, detect_change_points
    outlier_result = detect_outliers(values)
    change_point_result = detect_change_points(values)
    result["outlier_indices"] = outlier_result["outlier_indices"]
    result["change_points"] = change_point_result["change_points"]
    result["outlier_stats"] = outlier_result["stats"]

    result["grain"] = {"filter_column": params.get("filter_column"),
                        "filter_value": params.get("filter_value"),
                        "source_row_count": source_row_count,
                        "analyzed_row_count": len(df)}
    return {"success": True, **result}


def _handle_spc_multi_dataset_analyze(params: dict) -> dict:
    """Analyze SPC across multiple datasets and return comparison results."""
    entries = params.get("entries", [])
    chart_type = params.get("chart_type", "i-mr")
    lsl = params.get("lsl")
    usl = params.get("usl")

    results = []
    for entry in entries:
        did = entry.get("dataset_id")
        col = entry.get("column")
        if not did or not col:
            continue
        try:
            df = REGISTRY.get(did)
        except KeyError:
            continue
        if df is None or col not in df.columns:
            continue
        values = df[col].dropna().tolist()
        if len(values) < 5:
            continue
        try:
            if chart_type == "i-mr":
                r = compute_i_mr(values, lsl=lsl, usl=usl)
                r["chart_type"] = chart_type
            elif chart_type == "ewma":
                r = compute_ewma(values, lambda_param=params.get("ewma_lambda", 0.2), L=params.get("ewma_L", 3.0), lsl=lsl, usl=usl)
            elif chart_type == "cusum":
                r = compute_cusum(values, k=params.get("cusum_k", 0.5), H=params.get("cusum_H", 5.0), lsl=lsl, usl=usl)
            else:
                continue
            r["suggestions"] = compute_spc_suggestions(r)
            results.append({
                "dataset_id": did,
                "column": col,
                "source_file": REGISTRY.meta(did).get("file_path", ""),
                "n_points": len(values),
                "result": r,
            })
        except Exception:
            pass

    return {"results": results, "count": len(results)}


def _handle_spc_batch_analyze(params: dict) -> dict:
    """Analyze multiple columns and return results with suggestions."""
    df = REGISTRY.get(params["dataset_id"])
    columns = params.get("columns", [])
    chart_type = params.get("chart_type", "i-mr")
    lsl = params.get("lsl")
    usl = params.get("usl")

    results = {}
    for col in columns:
        if col not in df.columns:
            continue
        values = df[col].dropna().tolist()
        if not values:
            continue

        if chart_type == "i-mr":
            result = compute_i_mr(values, lsl=lsl, usl=usl)
            result["chart_type"] = chart_type
        elif chart_type == "ewma":
            result = compute_ewma(
                values,
                lambda_param=params.get("ewma_lambda", 0.2),
                L=params.get("ewma_L", 3.0),
                lsl=lsl,
                usl=usl,
            )
        elif chart_type == "cusum":
            result = compute_cusum(
                values,
                k=params.get("cusum_k", 0.5),
                H=params.get("cusum_H", 5.0),
                lsl=lsl,
                usl=usl,
            )
        elif chart_type in ("xbar-r", "xbar-s"):
            raise ValueError(f"Batch mode does not support chart_type={chart_type!r} (requires subgrouping)")
        else:
            raise ValueError(f"Unknown chart_type: {chart_type!r}")

        result["suggestions"] = compute_spc_suggestions(result)
        results[col] = result

    return {"results": results, "columns": list(results.keys())}


def _handle_spec_suggest(params: dict) -> dict:
    """Suggest LSL/USL based on mean ± 3σ of a column."""
    df = REGISTRY.get(params["dataset_id"])
    column = params["column"]
    if column not in df.columns:
        raise KeyError(f"Unknown column: {column}")
    values = df[column].dropna().tolist()
    if len(values) < 5:
        raise ValueError("Need at least 5 data points for suggestion")
    arr = np.asarray(values, dtype=float)
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
    if std <= 0:
        raise ValueError("Cannot suggest limits: std is zero (constant values)")
    return {
        "success": True,
        "column": column,
        "mean": round(mean, 6),
        "std": round(std, 6),
        "lsl": round(mean - 3 * std, 6),
        "usl": round(mean + 3 * std, 6),
    }


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
    source_row_count = len(df)
    df = _apply_row_filter(df, params)
    fit = MODEL_REGISTRY.get(model_id)

    if fit.model_type not in SUPPORTED_MODELS:
        raise ValueError(f"Monte Carlo does not support model type {fit.model_type!r}")

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
        model=fit.model,
    )
    sim_chain_id = _VERSION_CHAIN.register_entity(
        entity_type="simulation",
        project_id="default",
        metadata={
            "model_id": model_id,
            "dataset_id": did,
            "n_simulations": n_simulations,
            "seed": seed,
        },
        created_by=params.get("operator", "anonymous"),
    )
    result["chain_entity_id"] = sim_chain_id
    result["grain"] = {"filter_column": params.get("filter_column"), "filter_value": params.get("filter_value"), "source_row_count": source_row_count, "analyzed_row_count": len(df)}
    GATE_MANAGER.reset("monte_carlo", "Simulation changed")
    return {"success": True, "result": result}


def _handle_prediction_predict(params: dict) -> dict:
    """Predict output for given input values."""
    model_id = params["model_id"]
    fit = MODEL_REGISTRY.get(model_id)

    input_values = params.get("input_values", {})
    predicted = predict_single(fit.model_type, fit.coefficients or {}, input_values, model=fit.model)

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


def _assistant_state():
    """Bind pending actions and cloud previews to the opened project session."""
    global _ASSISTANT_STATE
    root = _VERSION_CHAIN._project_root.resolve()
    manifest = ProjectManifest.load(root)
    identity = (root, manifest.project_id, _VERSION_CHAIN)
    if _ASSISTANT_STATE is None or _ASSISTANT_STATE["identity"] != identity:
        _ASSISTANT_STATE = {
            "identity": identity, "drafts": {},
            "orchestrator": AssistantOrchestrator(str(root)),
        }
    _ASSISTANT_STATE["orchestrator"].config = get_settings_manager()._config
    return _ASSISTANT_STATE


def _assistant_request(params: dict, state: dict) -> AssistantRequest:
    project_id = state["identity"][1]
    if params.get("project_id", project_id) != project_id:
        raise PermissionError("Assistant request does not match the current project")
    message, page = params.get("message"), params.get("page", "")
    if not isinstance(message, str) or not message.strip() or not isinstance(page, str):
        raise ValueError("Assistant message and page must be strings")
    supplied = params.get("context", {})
    if not isinstance(supplied, dict):
        raise ValueError("Assistant context must be an object")
    selectors = supplied.get("page_summary", {})
    if not isinstance(selectors, dict):
        raise ValueError("Assistant page summary must be an object")
    context = build_assistant_context(project_id, page, {}, _VERSION_CHAIN)
    # Legacy handlers use 'default' inside a chain already isolated by project root.
    # Normalize only those records; explicit foreign project IDs remain excluded.
    if project_id != "default":
        legacy = build_assistant_context("default", page, {}, _VERSION_CHAIN)
        context["evidence"].extend({**item, "project_id": project_id} for item in legacy["evidence"])
    summary = {}
    for kind, fields in (
        ("dataset", ("row_count", "column_count")),
        ("model", ("model_type", "target", "inputs", "n_train", "n_test")),
    ):
        selected = selectors.get(f"selected_{kind}_id")
        if not isinstance(selected, str):
            continue
        for item in reversed(context["evidence"]):
            entity = _VERSION_CHAIN.get_entity(item["entity_id"])
            if entity.entity_type == kind and entity.metadata.get(f"{kind}_id") == selected:
                summary[f"selected_{kind}_id"] = selected
                summary[f"{kind}_summary"] = {key: entity.metadata[key] for key in fields if key in entity.metadata}
                break
    # Preserve bounded, feature-generated summaries (for example SPC control
    # limits and violations) instead of dropping them during normalization.
    for key in ("dataset_summary", "model_summary", "gate_summary", "report_summary", "evidence_status"):
        value = selectors.get(key)
        if isinstance(value, (str, int, float, bool)):
            summary[key] = value
    # Reuse the bounded summary validation before sending any server-built fields.
    context["page_summary"] = build_assistant_context(project_id, page, _plain_types(summary), _VERSION_CHAIN)["page_summary"]
    if "preview_hash" in supplied:
        context["preview_hash"] = supplied["preview_hash"]
    return AssistantRequest(message=message, project_id=project_id, page=page,
                            context=context, provider=params.get("provider", "ollama"))


def _handle_assistant_respond(params: dict) -> dict:
    state = _assistant_state()
    response = state["orchestrator"].respond(_assistant_request(params, state))
    if response.success and response.action_draft is not None:
        draft = response.action_draft
        state["drafts"][draft.draft_id] = deepcopy(draft.to_dict())
    return response.to_dict()


def _handle_assistant_cloud_preview(params: dict) -> dict:
    state = _assistant_state()
    request = _assistant_request(params, state)
    preview = state["orchestrator"].preview_cloud(request)
    state["preview_request"] = request.to_dict()
    return preview.to_dict()


def _handle_assistant_cloud_consent(params: dict) -> dict:
    if params.get("confirmed") is not True:
        return {"success": False, "error_code": "confirmation_required"}
    state = _assistant_state()
    if "preview_request" in state:
        state["orchestrator"].preview_cloud(_assistant_request(state["preview_request"], state))
    policy = state["orchestrator"].grant_project_cloud_consent(
        str(state["identity"][0]), params.get("preview_hash", ""))
    # Refresh the manifest cache so later project saves retain persisted consent.
    PROJECT_ENGINE.open_project(str(state["identity"][0]))
    return policy


def _handle_assistant_draft_execute(params: dict) -> dict:
    if params.get("confirmed") is not True:
        return {"success": False, "error_code": "confirmation_required"}
    state = _assistant_state()
    draft = state["drafts"].get(params.get("draft_id"))
    if draft is None:
        return {"success": False, "error_code": "draft_not_found"}
    # Revalidate the stored allow-list contract; client execution params are inert.
    validated = AssistantOrchestrator._draft(deepcopy(draft))
    dataset_id = validated.params.get("dataset_id")
    if isinstance(dataset_id, str):
        try:
            REGISTRY.get(dataset_id)
        except KeyError:
            # Rehydrate a project-owned dataset that was restored in the chain
            # but not yet materialized in the runtime registry.
            entity = next((e for e in _VERSION_CHAIN.get_chain_summary()
                           if e["entity_type"] == "dataset"
                           and e.get("metadata", {}).get("dataset_id") == dataset_id), None)
            if entity is not None:
                restored = _VERSION_CHAIN.get_entity(entity["entity_id"])
                REGISTRY._datasets[dataset_id] = load_dataset(_VERSION_CHAIN._project_root, restored)
                REGISTRY._meta[dataset_id] = {"file_path": restored.metadata.get("source_file", "")}
    result = handle_request(validated.method, validated.params)
    if result.get("success") is False or result.get("error_code") or result.get("error"):
        return result
    del state["drafts"][draft["draft_id"]]
    AUTH_MANAGER._log_audit(AuditAction.CHANGE_SETTING, "assistant_draft_confirmed", {
        "draft_id": draft["draft_id"], "project_id": state["identity"][1],
        "method": validated.method,
    })
    return result


def _handle_validation_experiment_create(params: dict) -> dict:
    """Persist planned conditions without recording measurements or a verdict."""
    model_id, conditions = params.get("model_id"), params.get("conditions")
    if not isinstance(model_id, str) or not isinstance(conditions, dict) or not conditions:
        raise ValueError("Experiment requires model_id and conditions")
    fit = MODEL_REGISTRY.get(model_id)
    if (set(conditions) != set(fit.inputs) or any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            for value in conditions.values())):
        raise ValueError("Conditions must contain finite values for every model input")
    project_id = ProjectManifest.load(_VERSION_CHAIN._project_root).project_id
    models = [_VERSION_CHAIN.get_entity(item["entity_id"]) for item in _VERSION_CHAIN.get_chain_summary()
              if item["entity_type"] == "model" and item["project_id"] in (project_id, "default")]
    parents = [entity.entity_id for entity in models if entity.metadata.get("model_id") == model_id]
    if not parents:
        raise ValueError("Model does not belong to the current project")
    experiment_id = str(uuid.uuid4())
    metadata = {"experiment_id": experiment_id, "model_id": model_id,
                "conditions": deepcopy(conditions), "status": "planned"}
    entity_id = _VERSION_CHAIN.register_entity("experiment", project_id, metadata,
        parent_ids=[parents[-1]], created_by=AUTH_MANAGER.current_user.username if AUTH_MANAGER.current_user else "anonymous")
    return {"success": True, **metadata, "chain_entity_id": entity_id}


def handle_request(method: str, params: dict) -> dict:
    """Dispatch an RPC method to its handler.

    Phase 1 methods: engine/ping, engine/health and the data pipeline
    (import, detect_fields, quality, distribution).
    Phase 2 methods: analysis/detect_anomalies, analysis/package.
    """
    if method == "engine/ping":
        return {"pong": True, "version": __import__('process_intelligence_engine').__version__}

    if method == "engine/health":
        return {
            "status": "ok",
            "engine": "process-intelligence-engine",
            "version": __import__('process_intelligence_engine').__version__,
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

    if method in ("modeling/fit", "modeling/governance/fit_with_check"):
        return _handle_modeling_fit(params)

    if method == "modeling/list":
        return _handle_modeling_list(params)

    if method == "modeling/transition":
        return _handle_modeling_transition(params)
    if method == "modeling/delete":
        return _handle_modeling_delete(params)

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
    if method == "modeling/stats":
        return _handle_stats_compute(params)

    if method == "modeling/validation/full":
        return _handle_validation_full(params)

    if method == "modeling/governance/check":
        dataset_id = params.get("dataset_id")
        df = REGISTRY.get(dataset_id)
        warnings = check_model_applicability(
            df, params["target"], params["inputs"],
            is_binary=params.get("is_binary", False),
        )
        result = {"warnings": warnings, "can_proceed": len([w for w in warnings if "tree" in w.lower() and "not recommended" in w]) == 0}
        return result
    if method == "modeling/governance/recommend":
        recs = recommend_models(
            params.get("n_samples", 0),
            params.get("n_features", 0),
            params.get("is_binary_target", False),
            params.get("has_nonlinearity", False),
            params.get("need_interpretability", True),
        )
        result = {"recommendations": recs}
        return result
    if method == "modeling/governance/doe_ai_compare":
        result = check_doeb_ai_discrepancy(
            params.get("doe_r2", 0),
            params.get("ai_r2", 0),
            params.get("ai_pred", []),
            params.get("doe_pred", []),
            params.get("scale", 1.0),
        )
        return result

    if method == "spec/suggest":
        return _handle_spec_suggest(params)

    if method == "report/generate":
        return _handle_report_generate(params)

    if method == "report/list":
        return _handle_report_list(params)
    if method == "report/export":
        return _handle_report_export(params)

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
    if method == "assistant/respond":
        return _handle_assistant_respond(params)
    if method == "assistant/cloud_preview":
        return _handle_assistant_cloud_preview(params)
    if method == "assistant/cloud_consent":
        return _handle_assistant_cloud_consent(params)
    if method == "assistant/draft/execute":
        return _handle_assistant_draft_execute(params)
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
    if method == "validation/experiment/create":
        return _handle_validation_experiment_create(params)
    if method == "experiment/list":
        return _handle_experiment_list(params)
    if method == "experiment/get":
        return _handle_experiment_get(params)
    if method == "experiment/record_with_verdict":
        return _handle_experiment_record_with_verdict(params)
    if method == "experiment/suggest_next":
        return _handle_experiment_suggest_next(params)
    if method == "experiment/impact":
        model_id = params["model_id"]
        verdict = params.get("verdict", "supports")
        result = update_model_after_experiment(model_id, verdict, _VERSION_CHAIN)
        return result

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
    if method == "spc/multi_dataset_analyze":
        return _handle_spc_multi_dataset_analyze(params)

    if method == "spc/batch_analyze":
        return _handle_spc_batch_analyze(params)
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
    if method == "project/save_session":
        return _handle_project_save_session(params)
    if method == "project/save_ui_state":
        return _handle_project_save_ui_state(params)
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

    if method == "versioning/chain/summary":
        return {"summary": _VERSION_CHAIN.get_chain_summary()}
    if method == "versioning/chain/trace":
        return _VERSION_CHAIN.get_trace(params["entity_id"])
    if method == "versioning/chain/link":
        _VERSION_CHAIN.add_link(
            params["from_id"], params["to_id"],
            params["relation"],
            params.get("evidence_status", "unverified"),
            params.get("created_by", params.get("operator", "anonymous")),
        )
        return {"success": True}

    if method == "gates/status":
        return {"statuses": GATE_MANAGER.get_summary()}
    if method == "gates/confirm":
        entity = _VERSION_CHAIN.get_entity(params["entity_id"])
        expected_module = {"dataset": "data_import", "model": "modeling", "simulation": "monte_carlo", "experiment": "validation"}.get(entity.entity_type)
        if params["module"] != expected_module or params["entity_version"] != entity.version:
            raise ValueError("Gate entity type or version does not match")
        if not params.get("confirmed_by", "").strip():
            raise ValueError("Confirmation operator is required")
        return GATE_MANAGER.confirm(
            params["module"],
            params["entity_id"],
            params["entity_version"],
            params["confirmed_by"],
            params.get("comment", ""),
        )
    if method == "gates/reset":
        return GATE_MANAGER.reset(params["module"], params.get("reason", ""))
    if method == "gates/summary":
        return {
            "summary": GATE_MANAGER.get_summary(),
            "all_confirmed": GATE_MANAGER.are_all_confirmed(),
            "details": {m: GATE_MANAGER.get_details(m) for m in params.get("modules", GATE_MANAGER.ALL_MODULES)},
        }
    if method == "gates/history":
        return {"history": GATE_MANAGER.get_history(params.get("module"))}

    if method == "analysis/anomaly/register":
        dataset_id = params.get("dataset_id", "")
        matches = [e for e in _report_entities(dataset_id, []) if e.entity_type == "dataset"]
        if not matches:
            try:
                candidate = _VERSION_CHAIN.get_entity(dataset_id)
                if candidate.entity_type == "dataset":
                    matches = [candidate]
            except KeyError:
                pass
        if not matches:
            raise ValueError("Anomaly requires a registered dataset version")
        entity_id = register_anomaly_event(
            _VERSION_CHAIN,
            matches[-1].entity_id,
            params["anomaly_id"],
            params.get("source", "historical_observation"),
            params.get("confidence", 0.0),
            params.get("user_confirmed", False),
            params.get("operator", "anonymous"),
            params.get("scenario"),
        )
        result = {"entity_id": entity_id}
        GATE_MANAGER.reset("monte_carlo", "Anomaly assumptions changed")
        return result

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
        timestamp=_dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z"),
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
        df = _apply_row_filter(df, params)
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
    result = APPROVAL_WORKFLOW.submit_for_review(
        resource_type=params["resource_type"],
        resource_id=params["resource_id"],
        reviewer=params["reviewer"],
        reviewer_role=params["reviewer_role"],
        comments=params.get("comments", ""),
    )
    APPROVAL_WORKFLOW.save(_VERSION_CHAIN._project_root / "audit" / "approvals.json")
    return result


def _handle_approval_approve(params: dict) -> dict:
    if params["resource_type"] == "report":
        report = _VERSION_CHAIN.get_entity(params["resource_id"])
        if report.entity_type != "report":
            raise ValueError("Expected a report chain entity ID")
        parents = [_VERSION_CHAIN.get_entity(eid) for eid in report.parent_ids]
        if not any(e.entity_type == "dataset" for e in parents):
            raise ValueError("Report dataset has no traceable version; regenerate from imported data")
        found_models = {e.metadata.get("model_id") for e in parents if e.entity_type == "model"}
        if not set(report.metadata.get("model_ids", [])).issubset(found_models):
            raise ValueError("Report model has no traceable version")
        modules = {"dataset": "data_import", "model": "modeling", "simulation": "monte_carlo"}
        for entity in parents:
            module = modules.get(entity.entity_type)
            if module:
                if not GATE_MANAGER.is_confirmed(module, entity.entity_id, entity.version):
                    raise ValueError(f"Report requires confirmation of {module} version {entity.entity_id}")
        if APPROVAL_WORKFLOW.get_status("report", report.entity_id) != "pending_review":
            raise ValueError("Report must be submitted for review before approval")
    result = APPROVAL_WORKFLOW.approve(
        resource_type=params["resource_type"],
        resource_id=params["resource_id"],
        reviewer=params["reviewer"],
        reviewer_role=params["reviewer_role"],
        comments=params.get("comments", ""),
    )
    APPROVAL_WORKFLOW.save(_VERSION_CHAIN._project_root / "audit" / "approvals.json")
    return result


def _handle_approval_reject(params: dict) -> dict:
    result = APPROVAL_WORKFLOW.reject(
        resource_type=params["resource_type"],
        resource_id=params["resource_id"],
        reviewer=params["reviewer"],
        reviewer_role=params["reviewer_role"],
        comments=params.get("comments", ""),
    )
    APPROVAL_WORKFLOW.save(_VERSION_CHAIN._project_root / "audit" / "approvals.json")
    return result


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


def _handle_copula_joint(params: dict) -> dict:
    """Compute joint occurrence probabilities for a set of anomalies.

    Supports Gaussian Copula (with a correlation matrix), independent
    assumption, or direct pair-joint probabilities.
    """
    anomalies = params.get("anomalies") or []
    correlation_matrix = params.get("correlation_matrix")
    direct_joints = params.get("direct_joints")
    seed = params.get("seed")
    n_samples = int(params.get("n_samples", 100_000))

    result = compute_joint_probabilities(
        anomalies,
        correlation_matrix=correlation_matrix,
        direct_joints=direct_joints,
        seed=seed,
        n_samples=n_samples,
    )
    return _plain_types(result.to_dict())


def _handle_grr(params: dict) -> dict:
    """Run Gage R&R analysis on measurement data."""
    dataset_id = params.get("dataset_id")
    measurement_column = params["measurement_column"]
    part_column = params["part_column"]
    operator_column = params["operator_column"]

    if dataset_id:
        df = REGISTRY.get(dataset_id)
        df = _apply_row_filter(df, params)
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
    strategy_overrides = params.get("strategy_overrides", {})

    preview = generate_upload_preview(
        df, dataset_id,
        sensitive_columns=sensitive_columns,
        excluded_columns=excluded_columns,
        strategy_overrides=strategy_overrides,
        noise_std=noise_std,
        seed=seed,
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
    strategy_overrides = params.get("strategy_overrides", {})
    operator = params.get("operator", "anonymous")
    provider = params.get("provider", "custom")
    model_version = params.get("model_version", "unknown")
    purpose = params.get("purpose", "")

    preview = generate_upload_preview(
        df, dataset_id,
        sensitive_columns=sensitive_columns,
        excluded_columns=excluded_columns,
        strategy_overrides=strategy_overrides,
        noise_std=noise_std,
        seed=seed,
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
    result = PROJECT_ENGINE.create_project(root, name, operator)
    restored = _reload_chain_for_project(root)
    return {**result, **restored}


def _handle_project_open(params: dict) -> dict:
    from pathlib import Path
    global PROJECT_ENGINE

    root = params["root"]
    path = Path(root).expanduser().resolve()
    if path.name.endswith(".piproj.json"):
        return _open_portable_project(path)
    if path.is_file() and path.name == "project_manifest.json":
        root = str(path.parent)
    candidate = ProjectEngine()
    result = candidate.open_project(root)
    restored = _reload_chain_for_project(root)
    PROJECT_ENGINE = candidate
    return {**result, **restored}


def _open_portable_project(path) -> dict:
    """Restore a portable settings export without requiring a sibling manifest."""
    from pathlib import Path
    import tempfile

    global PROJECT_ENGINE, _VERSION_CHAIN, GATE_MANAGER, REGISTRY, MODEL_REGISTRY
    global EXPERIMENT_REGISTRY, APPROVAL_WORKFLOW, REPORT_REGISTRY
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("app") != "process-intelligence-platform":
        raise ValueError("Not a Process Intelligence Platform project file")
    version = data.get("version")
    if type(version) is not int or version not in (1, 2):
        raise ValueError(f"Unsupported portable project version: {version}")
    source_info = data.get("import")
    if not isinstance(source_info, dict) or not isinstance(source_info.get("file_path"), str) or not source_info["file_path"].strip():
        raise ValueError("Portable project is missing import.file_path")
    source = Path(source_info["file_path"]).expanduser()
    if not source.is_absolute():
        source = path.parent / source
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Original Excel/CSV not found: {source}. The .piproj.json stores a path, not the source data.")

    # A portable export is a settings snapshot, not a saved approval history.
    # Build an isolated workspace; never turn Downloads itself into a project.
    previous = (PROJECT_ENGINE, _VERSION_CHAIN, GATE_MANAGER, REGISTRY, MODEL_REGISTRY,
                EXPERIMENT_REGISTRY, APPROVAL_WORKFLOW, REPORT_REGISTRY)
    try:
        root = tempfile.mkdtemp(prefix="piproj-")
        PROJECT_ENGINE = ProjectEngine()
        project = PROJECT_ENGINE.create_project(root, path.name.removesuffix(".piproj.json"))
        _reload_chain_for_project(root)
        REGISTRY = DatasetRegistry()
        MODEL_REGISTRY = ModelRegistry()
        imported = _handle_import({"file_path": str(source)})
    except Exception:
        (PROJECT_ENGINE, _VERSION_CHAIN, GATE_MANAGER, REGISTRY, MODEL_REGISTRY,
         EXPERIMENT_REGISTRY, APPROVAL_WORKFLOW, REPORT_REGISTRY) = previous
        raise
    return {**project, "kind": "portable", "datasets": 1, "process_groups": 0,
            "project_file": data, "import_result": imported}


def _reload_chain_for_project(root: str) -> dict:
    """Reinitialize the shared version chain and gate manager for a project root."""
    global _VERSION_CHAIN, GATE_MANAGER, REGISTRY, MODEL_REGISTRY, EXPERIMENT_REGISTRY
    global APPROVAL_WORKFLOW, REPORT_REGISTRY, _ASSISTANT_STATE
    chain = VersionChain(root, "anonymous")
    chain.load()
    datasets = DatasetRegistry()
    models = ModelRegistry()
    experiments = ExperimentRegistry()
    import_result = None
    for item in chain.get_chain_summary():
        entity = chain.get_entity(item["entity_id"])
        if entity.entity_type == "dataset" and entity.metadata.get("import_result"):
            did = entity.metadata["dataset_id"]
            df = load_dataset(chain._project_root, entity)
            datasets._datasets[did] = df
            import_result = entity.metadata["import_result"]
            # Restore the same schema/metadata context that was available
            # immediately after import, not only the raw dataframe.
            datasets._meta[did] = {
                "file_path": entity.metadata["source_file"],
                "format": import_result.get("format"),
                "encoding": import_result.get("encoding"),
                "delimiter": import_result.get("delimiter"),
                "row_count": import_result.get("row_count"),
                "column_count": import_result.get("column_count"),
                "columns": import_result.get("columns", []),
                "metadata_columns": entity.metadata.get("metadata_columns", []),
            }
        elif entity.entity_type == "experiment" and entity.metadata.get("record"):
            record = dict(entity.metadata["record"])
            record.pop("prediction_error", None)
            experiments.record(ExperimentRecord(**record))
    for item in chain.get_chain_summary():
        entity = chain.get_entity(item["entity_id"])
        if entity.entity_type == "model" and "recipe" in entity.metadata:
            models.restore(rebuild_model(entity, datasets.get(entity.metadata["dataset_id"]), MODEL_FITTERS))
    for item in chain.get_chain_summary():
        entity = chain.get_entity(item["entity_id"])
        if entity.entity_type == "model_state" and entity.metadata["model_id"] in models.list_ids():
            models.get(entity.metadata["model_id"]).status = entity.metadata["status"]
    gates = GateManager(project_root=root, project_id="default")
    approvals = type(APPROVAL_WORKFLOW)()
    approvals.load(chain._project_root / "audit" / "approvals.json")
    reports = type(REPORT_REGISTRY)()
    for item in chain.get_chain_summary():
        if item["entity_type"] == "report":
            entity = chain.get_entity(item["entity_id"])
            reports.register(entity.metadata.get("project_name", "Report"), entity.created_by,
                                     entity.metadata.get("format", "html"), entity.entity_id)
    ui_path = chain._project_root / "registry" / "ui_state.json"
    ui_state = json.loads(ui_path.read_text(encoding="utf-8")) if ui_path.exists() else None
    _VERSION_CHAIN = chain
    _ASSISTANT_STATE = None
    REGISTRY, MODEL_REGISTRY, EXPERIMENT_REGISTRY = datasets, models, experiments
    GATE_MANAGER, APPROVAL_WORKFLOW, REPORT_REGISTRY = gates, approvals, reports
    return {"import_result": import_result, "project_file": ui_state, "models_rebuilt": len(models.list_ids())}


def _handle_project_save_session(params):
    """Save a complete data-only analysis directory without overwriting a project."""
    from pathlib import Path
    import shutil
    target = Path(params["root"]).expanduser().resolve()
    if target.exists():
        raise ValueError("Choose a new analysis directory; existing directories are not overwritten")
    source = _VERSION_CHAIN._project_root.resolve()
    if target == source or source in target.parents:
        raise ValueError("Destination must be outside the active project")
    state = params.get("project_file")
    if not isinstance(state, dict):
        raise ValueError("Analysis settings are required")
    target.mkdir(parents=True)
    for folder in ("registry", "audit", "reports", "curated_data", "models", "experiments", "simulations"):
        directory = source / folder
        if directory.exists():
            if directory.is_symlink() or any(p.is_symlink() for p in directory.rglob("*")):
                raise ValueError("Analysis snapshots cannot contain symlinks")
            shutil.copytree(directory, target / folder)
    engine = ProjectEngine()
    if (source / "project_manifest.json").exists():
        shutil.copy2(source / "project_manifest.json", target / "project_manifest.json")
    else:
        engine.create_project(str(target), target.name)
    if params.get("name"):
        engine.create_project(str(target), params["name"])
    (target / "registry").mkdir(exist_ok=True)
    (target / "registry" / "ui_state.json").write_text(json.dumps(state), encoding="utf-8")
    return {"project_root": str(target)}


def _handle_project_save_ui_state(params):
    """Persist the current UI settings inside the active full project."""
    state = params.get("project_file")
    if not isinstance(state, dict):
        raise ValueError("Analysis settings are required")
    target = _VERSION_CHAIN._project_root / "registry"
    target.mkdir(parents=True, exist_ok=True)
    (target / "ui_state.json").write_text(json.dumps(state), encoding="utf-8")
    return {"project_root": str(_VERSION_CHAIN._project_root)}


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
    keys = params.get("set_association_keys")
    if keys is not None:
        return PROJECT_ENGINE.set_association_keys(keys)
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
