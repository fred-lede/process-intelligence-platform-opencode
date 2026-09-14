"""Safe, project-scoped persistence for fitted time-series estimators."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import joblib

from .fitters import ModelFit


def _schema(df) -> str:
    payload = [(str(c), str(df[c].dtype)) for c in df.columns]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def save_estimator(root: Path, fit: ModelFit, estimator: Any, *, dataset_id: str,
                   df, time_column: str, feature_configuration: dict,
                   evaluation_protocol: str, training_time_range: dict,
                   feature_names: list[str] | None = None,
                   replay_metadata: dict | None = None,
                   validation_gate_evidence: dict | None = None) -> dict:
    if estimator is None or not hasattr(estimator, "predict"):
        raise ValueError("time-series estimator is not fitted")
    model_id = fit.model_id
    directory = Path(root).resolve() / "models" / "time_series"
    directory.mkdir(parents=True, exist_ok=True)
    transformer = fit.model_type == "time_series_transformer"
    path = (directory / f"{model_id}.{ 'keras' if transformer else 'joblib'}").resolve()
    if directory not in path.parents:
        raise ValueError("invalid model artifact path")
    if transformer:
        replay = replay_metadata or {}
        normalization = replay.get("normalization")
        if (
            not isinstance(replay.get("sequence_length"), int)
            or replay["sequence_length"] < 1
            or not isinstance(normalization, dict)
        ):
            raise ValueError("Transformer replay metadata is incomplete")
        estimator.save(path)
    else:
        joblib.dump(estimator, path)
    metadata = {
        "schema_version": "ts-transformer-1" if transformer else "ts-estimator-1",
        "model_id": model_id, "model_type": fit.model_type,
        "dataset_id": dataset_id, "dataset_schema": _schema(df),
        "target": fit.target, "inputs": list(fit.inputs),
        "time_column": time_column, "feature_configuration": feature_configuration,
        "feature_names": list(feature_names or []),
        "evaluation_protocol": evaluation_protocol,
        "training_time_range": training_time_range,
        "artifact": str(path.relative_to(Path(root).resolve())),
    }
    if transformer:
        metadata.update({
            "artifact_format": "keras",
            "replay": replay_metadata,
            "validation_gate_evidence": validation_gate_evidence or {},
        })
    (directory / f"{model_id}.json").write_text(json.dumps(metadata, default=str, indent=2), encoding="utf-8")
    return metadata


def load_estimator(root: Path, model_id: str, *, df, target: str | None = None,
                   inputs: list[str] | None = None, time_column: str | None = None):
    base = Path(root).resolve() / "models" / "time_series"
    meta_path = (base / f"{model_id}.json").resolve()
    if base not in meta_path.parents or not meta_path.is_file():
        raise KeyError(f"Unknown persisted time-series model: {model_id}")
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    schema_version = metadata.get("schema_version")
    if schema_version not in {"ts-estimator-1", "ts-transformer-1"}:
        raise ValueError("Unsupported persisted time-series metadata version")
    transformer = metadata.get("model_type") == "time_series_transformer"
    if transformer:
        replay = metadata.get("replay")
        normalization = replay.get("normalization") if isinstance(replay, dict) else None
        if (
            schema_version != "ts-transformer-1"
            or metadata.get("artifact_format") != "keras"
            or not isinstance(replay.get("sequence_length") if isinstance(replay, dict) else None, int)
            or not isinstance(normalization, dict)
        ):
            raise ValueError("Invalid Transformer replay metadata")
    required = [metadata["target"], *metadata["inputs"], metadata["time_column"]]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Incompatible dataset: missing columns {missing}")
    if target is not None and target != metadata["target"]:
        raise ValueError("Incompatible target column")
    if inputs is not None and list(inputs) != metadata["inputs"]:
        raise ValueError("Incompatible input columns")
    if time_column is not None and time_column != metadata["time_column"]:
        raise ValueError("Incompatible time column")
    if _schema(df) != metadata["dataset_schema"]:
        raise ValueError("Incompatible dataset schema")
    artifact = (Path(root).resolve() / metadata["artifact"]).resolve()
    if base not in artifact.parents or not artifact.is_file():
        raise FileNotFoundError("Persisted estimator artifact is missing")
    if transformer:
        from tensorflow import keras
        return keras.models.load_model(artifact), metadata
    return joblib.load(artifact), metadata
