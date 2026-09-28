"""Data-only session snapshots and checked model replay (no pickle loading)."""
from io import StringIO
import hashlib
import json
import uuid

import numpy as np
import pandas as pd


def dataset_path(root, dataset_id):
    uuid.UUID(dataset_id)
    return root / "curated_data" / f"{dataset_id}.json"


def save_dataset(root, dataset_id, df):
    text = df.to_json(orient="table", date_format="iso", double_precision=15)
    path = dataset_path(root, dataset_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode()).hexdigest()


def load_dataset(root, entity):
    path = dataset_path(root, entity.metadata["dataset_id"])
    text = path.read_text(encoding="utf-8")
    if hashlib.sha256(text.encode()).hexdigest() != entity.content_hash:
        raise ValueError(f"Dataset checksum mismatch: {entity.entity_id}")
    return pd.read_json(StringIO(text), orient="table", precise_float=True)


def prediction_check(fit, df):
    """Store replay checks in data form, independent of executable model artifacts."""
    from process_intelligence_engine.prediction import predict_single
    inputs = fit.selected_inputs or fit.inputs
    if fit.model_type == "logistic_regression":
        return fit.model.predict_proba(df[inputs].to_numpy())[:, 1].tolist()
    if fit.model is not None:
        if fit.model_type in ("doe_linear", "doe_quadratic"):
            from process_intelligence_engine.modeling.validation import _build_design_matrix
            degree = 2 if fit.model_type == "doe_quadratic" else 1
            matrix = _build_design_matrix(df, inputs, degree).to_numpy(dtype=float)
            return fit.model.predict(matrix).tolist()
        return fit.model.predict(df[inputs].to_numpy(dtype=float)).tolist()
    return [predict_single(fit.model_type, fit.coefficients or {}, row, model=fit.model,
                           feature_names=inputs)
            for row in df[fit.inputs].to_dict(orient="records")]


def rebuild_model(entity, df, fitters):
    from process_intelligence_engine.prediction import PREDICTION_CONTRACT

    recipe = entity.metadata["recipe"]
    snapshot = entity.metadata["fit_snapshot"]
    kind = snapshot["model_type"]
    fit = fitters[kind](df, target=snapshot["target"],
                        inputs=entity.metadata.get("training_inputs", snapshot["inputs"]), **recipe)
    expected = np.asarray(entity.metadata["prediction_check"], dtype=float)
    actual = np.asarray(prediction_check(fit, df), dtype=float)
    if actual.shape != expected.shape or not np.allclose(actual, expected, rtol=1e-8, atol=1e-10, equal_nan=False):
        saved_contract = entity.metadata.get("prediction_contract")
        if saved_contract != PREDICTION_CONTRACT:
            # The stored predictions came from a defective predictor, so a
            # mismatch here is expected rather than corruption. Say so plainly
            # instead of implying the dataset or the model was tampered with.
            raise ValueError(
                f"Model {entity.entity_id} was saved under prediction contract "
                f"{saved_contract if saved_contract is not None else 'unknown (pre-fix)'} "
                f"but this engine implements contract {PREDICTION_CONTRACT}: the older "
                f"predictor returned the residual alone for residual_hybrid and ignored "
                f"the fitted feature order for tree models. Refit and re-approve this "
                f"model to restore the trust chain."
            )
        raise ValueError(f"Model replay differs from saved predictions: {entity.entity_id}; refit and review required")
    fit.model_id = snapshot["model_id"]
    fit.version = snapshot["version"]
    fit.created_at = snapshot["created_at"]
    fit.status = snapshot["status"]
    return fit
