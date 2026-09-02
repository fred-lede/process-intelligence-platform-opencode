"""Model fitting: linear/quadratic DOE, random-forest AI, residual hybrid.

The residual hybrid fits Y = f_DOE(X) + r_AI(X): a linear/quadratic
regression captures the interpretable structure and a random forest models
the residual r = Y - f_DOE(X).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split

from .metrics import (
    mean_absolute_error,
    root_mean_squared_error,
    r2_score,
    adjusted_r2,
)

MODEL_TYPES = {
    "doe_linear": "doe_linear",
    "doe_quadratic": "doe_quadratic",
    "random_forest": "random_forest",
    "residual_hybrid": "residual_hybrid",
}

STATUS = ("draft", "pending_validation", "validated", "approved", "retired")


@dataclass
class ModelFit:
    """A fitted model + comparison metrics, ready for IPC serialization."""

    model_type: str
    target: str
    inputs: list[str]
    metrics: dict = field(default_factory=dict)
    coefficients: dict | None = None
    equation: str = ""
    n_train: int = 0
    n_test: int = 0
    status: str = "draft"
    model_id: str = ""
    created_at: str = ""
    version: int = 1
    direction: str | None = None

    def to_dto(self) -> dict:
        return {
            "model_id": self.model_id,
            "model_type": self.model_type,
            "target": self.target,
            "inputs": list(self.inputs),
            "status": self.status,
            "created_at": self.created_at,
            "version": self.version,
            "metrics": dict(self.metrics),
            "coefficients": self.coefficients,
            "equation": self.equation,
            "n_train": self.n_train,
            "n_test": self.n_test,
        }


def _compute_all_metrics(y_true, y_pred, n_features: int) -> dict:
    return {
        "rmse": root_mean_squared_error(y_true, y_pred),
        "mae": mean_absolute_error(y_true, y_pred),
        "r2": r2_score(y_true, y_pred),
        "adj_r2": adjusted_r2(r2_score(y_true, y_pred), len(y_true), n_features),
    }


def _train_test(X: np.ndarray, y: np.ndarray, test_size: float, random_state: int | None):
    return train_test_split(
        X, y, test_size=test_size, random_state=random_state
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _design_matrix(df: pd.DataFrame, inputs: list[str], degree: int = 1) -> pd.DataFrame:
    """Build a (possibly quadratic) design matrix with an intercept column."""
    if not inputs:
        raise ValueError("at least one input is required")
    cols: dict[str, np.ndarray] = {"1": np.ones(len(df))}
    for x in inputs:
        cols[x] = df[x].to_numpy(dtype=float)
        if degree >= 2:
            cols[f"{x}^2"] = df[x].to_numpy(dtype=float) ** 2
    if degree >= 2 and len(inputs) >= 2:
        for i in range(len(inputs)):
            for j in range(i + 1, len(inputs)):
                xi = inputs[i]
                xj = inputs[j]
                cols[f"{xi}*{xj}"] = (
                    df[xi].to_numpy(dtype=float) * df[xj].to_numpy(dtype=float)
                )
    return pd.DataFrame(cols)


def _fit_linear_on_matrix(df, target, inputs, degree, test_size, random_state) -> ModelFit:
    X = _design_matrix(df, inputs, degree).to_numpy(dtype=float)
    y = df[target].to_numpy(dtype=float)
    X_tr, X_te, y_tr, y_te = _train_test(X, y, test_size, random_state)
    model = LinearRegression().fit(X_tr, y_tr)
    y_pred = model.predict(X_te)
    design = _design_matrix(df, inputs, degree)
    coefs = dict(zip(design.columns, model.coef_.tolist()))
    metrics = _compute_all_metrics(y_te, y_pred, len(inputs))
    terms = [f"{model.intercept_:.4g}"]
    for name, c in coefs.items():
        if name == "1":
            continue
        terms.append(f"{c:+.4g}*{name}")
    fit = ModelFit(
        model_type="doe_quadratic" if degree >= 2 else "doe_linear",
        target=target,
        inputs=list(inputs),
        metrics=metrics,
        coefficients={k: float(v) for k, v in coefs.items()},
        equation=" ".join(terms),
        n_train=len(X_tr),
        n_test=len(X_te),
        created_at=_now(),
    )
    return fit


def fit_doe_linear(
    df: pd.DataFrame, target: str, inputs: list[str], test_size: float = 0.3, random_state: int | None = None
) -> ModelFit:
    return _fit_linear_on_matrix(df, target, inputs, degree=1, test_size=test_size, random_state=random_state)


def fit_doe_quadratic(
    df: pd.DataFrame, target: str, inputs: list[str], test_size: float = 0.3, random_state: int | None = None
) -> ModelFit:
    return _fit_linear_on_matrix(df, target, inputs, degree=2, test_size=test_size, random_state=random_state)


def fit_random_forest(
    df: pd.DataFrame,
    target: str,
    inputs: list[str],
    test_size: float = 0.3,
    random_state: int | None = None,
    n_estimators: int = 100,
) -> ModelFit:
    if not inputs:
        raise ValueError("at least one input is required")
    X = df[inputs].to_numpy(dtype=float)
    y = df[target].to_numpy(dtype=float)
    X_tr, X_te, y_tr, y_te = _train_test(X, y, test_size, random_state)
    rf = RandomForestRegressor(n_estimators=n_estimators, random_state=random_state, n_jobs=1)
    rf.fit(X_tr, y_tr)
    y_pred = rf.predict(X_te)
    return ModelFit(
        model_type="random_forest",
        target=target,
        inputs=list(inputs),
        metrics=_compute_all_metrics(y_te, y_pred, len(inputs)),
        coefficients=None,
        equation=f"RandomForest(y, {inputs})",
        n_train=len(X_tr),
        n_test=len(X_te),
        created_at=_now(),
    )


def fit_residual_hybrid(
    df: pd.DataFrame,
    target: str,
    inputs: list[str],
    test_size: float = 0.3,
    random_state: int | None = None,
    n_estimators: int = 100,
) -> ModelFit:
    if not inputs:
        raise ValueError("at least one input is required")
    y = df[target].to_numpy(dtype=float)
    X = df[inputs].to_numpy(dtype=float)
    D = _design_matrix(df, inputs, degree=2).to_numpy(dtype=float)
    doe_cols = _design_matrix(df, inputs, degree=2).columns
    n = len(df)
    # Single index scheme: shuffle row indices once, share across DOE+RF.
    idx = np.arange(n)
    rs = np.random.default_rng(random_state)
    idx = rs.permutation(idx) if random_state is not None else idx[::-1]
    test_n = int(n * test_size)
    test_idx = idx[:test_n]
    train_idx = idx[test_n:]
    # DOE quadratic captures interpretable curvature on the training slice.
    doe = LinearRegression().fit(D[train_idx], y[train_idx])
    residual = y[train_idx] - doe.predict(D[train_idx])
    rf = RandomForestRegressor(n_estimators=n_estimators, random_state=random_state, n_jobs=1)
    rf.fit(X[train_idx], residual)
    y_pred = doe.predict(D[test_idx]) + rf.predict(X[test_idx])
    y_test = y[test_idx]
    coefs = dict(zip(doe_cols, doe.coef_.tolist()))
    return ModelFit(
        model_type="residual_hybrid",
        target=target,
        inputs=list(inputs),
        metrics=_compute_all_metrics(y_test, y_pred, len(inputs)),
        coefficients={k: float(v) for k, v in coefs.items()},
        equation="Y = f_DOE(X) + r_RF(X)",
        n_train=len(train_idx),
        n_test=len(test_idx),
        created_at=_now(),
    )
