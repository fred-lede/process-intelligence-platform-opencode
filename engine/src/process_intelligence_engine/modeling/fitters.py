"""Model fitting: linear/quadratic DOE, random-forest AI, residual hybrid.

The residual hybrid fits Y = f_DOE(X) + r_AI(X): a linear/quadratic
regression captures the interpretable structure and a random forest models
the residual r = Y - f_DOE(X).
"""

from __future__ import annotations

from typing import Any

from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, recall_score, roc_auc_score
from scipy.optimize import minimize

from .metrics import (
    mean_absolute_error,
    mean_squared_error,
    root_mean_squared_error,
    r2_score,
    adjusted_r2,
)

MODEL_TYPES = {
    "doe_linear": "doe_linear",
    "doe_quadratic": "doe_quadratic",
    "random_forest": "random_forest",
    "residual_hybrid": "residual_hybrid",
    "logistic_regression": "logistic_regression",
    "weibull_regression": "weibull_regression",
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
    model: Any = None

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
        "mse": mean_squared_error(y_true, y_pred),
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
    n_predictors = len(design.columns) - 1  # exclude intercept "1"
    metrics = _compute_all_metrics(y_te, y_pred, n_predictors)
    terms = [f"{model.intercept_:.4g}"]
    coefficients = {}
    for name, c in coefs.items():
        if name == "1":
            continue
        terms.append(f"{c:+.4g}*{name}")
        coefficients[name] = float(c)
    coefficients["_intercept"] = float(model.intercept_)
    fit = ModelFit(
        model_type="doe_quadratic" if degree >= 2 else "doe_linear",
        target=target,
        inputs=list(inputs),
        metrics=metrics,
        coefficients=coefficients,
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
        model=rf,
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
    idx = rs.permutation(idx)
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
    n_predictors = len(doe_cols) - 1  # exclude intercept "1"
    coefficients = {}
    for name, c in coefs.items():
        if name == "1":
            continue
        coefficients[name] = float(c)
    coefficients["_intercept"] = float(doe.intercept_)
    return ModelFit(
        model_type="residual_hybrid",
        target=target,
        inputs=list(inputs),
        metrics=_compute_all_metrics(y_test, y_pred, n_predictors),
        coefficients=coefficients,
        equation="Y = f_DOE(X) + r_RF(X)",
        n_train=len(train_idx),
        n_test=len(test_idx),
        created_at=_now(),
    )


def fit_logistic_regression(
    df: pd.DataFrame,
    target: str,
    inputs: list[str],
    test_size: float = 0.3,
    random_state: int | None = None,
) -> ModelFit:
    """Fit a logistic regression model for binary classification (NG prediction)."""
    if not inputs:
        raise ValueError("at least one input is required")
    y = df[target].astype(float)
    # Support both binary (0/1) and label-encoded (OK/NG) targets
    unique_vals = y.unique()
    if set(unique_vals).issubset({0.0, 1.0}):
        pass  # already binary
    elif len(unique_vals) == 2:
        # Encode: first unique value -> 0, second -> 1
        label_map = {v: i for i, v in enumerate(unique_vals)}
        y = y.map(label_map).astype(float)
    X = df[inputs].to_numpy(dtype=float)
    X_tr, X_te, y_tr, y_te = _train_test(X, y, test_size, random_state)
    lr = LogisticRegression(random_state=random_state, max_iter=1000)
    lr.fit(X_tr, y_tr)
    y_pred_proba = lr.predict_proba(X_te)[:, 1]
    y_pred_class = lr.predict(X_te)
    acc = accuracy_score(y_te, y_pred_class)
    try:
        auc = float(roc_auc_score(y_te, y_pred_proba))
    except ValueError:
        auc = 0.5
    # Compute recall (sensitivity): TP / (TP + FN)
    recall = recall_score(y_te, y_pred_class, zero_division=0)
    # Negative class count = NG (class 1)
    n_ng = int(y_tr.sum())
    n_ok = len(y_tr) - n_ng
    return ModelFit(
        model_type="logistic_regression",
        target=target,
        inputs=list(inputs),
        metrics={
            "accuracy": float(acc),
            "recall": float(recall),
            "auc": auc,
            "n_ng": n_ng,
            "n_ok": n_ok,
        },
        coefficients={inputs[i]: float(lr.coef_[0, i]) for i in range(len(inputs))},
        equation=f"logit(P(NG)) = {lr.intercept_[0]:.4g} + " + " + ".join(
            f"{lr.coef_[0, i]:+.4g}*{inputs[i]}" for i in range(len(inputs))
        ),
        n_train=len(X_tr),
        n_test=len(X_te),
        created_at=_now(),
        model=lr,
    )


def _weibull_nll(params: np.ndarray, X: np.ndarray, t: np.ndarray) -> float:
    """Negative log-likelihood for Weibull regression.

    log(λ) = X @ β,  shape = k
    NLL = Σ [ log(k) - k*log(λ) + (k-1)*log(t) - (t/λ)^k ]
    """
    beta = params[:-1]
    log_k = params[-1]
    k = np.exp(log_k)
    log_lambda = X @ beta
    lambda_val = np.exp(log_lambda)
    if np.any(lambda_val <= 0) or k <= 0:
        return 1e15
    nll = np.sum(
        np.log(k)
        - k * np.log(lambda_val)
        + (k - 1.0) * np.log(t)
        - (t / lambda_val) ** k
    )
    return float(nll)


def fit_weibull_regression(
    df: pd.DataFrame,
    target: str,
    inputs: list[str],
    test_size: float = 0.3,
    random_state: int | None = None,
) -> ModelFit:
    """Fit a Weibull regression model for reliability / life-data analysis.

    The scale parameter λ is modeled as log(λ) = β₀ + β₁x₁ + … + βₚxₚ.
    The shape k is constant across observations.
    """
    if not inputs:
        raise ValueError("at least one input is required")
    t = df[target].to_numpy(dtype=float)
    if np.any(t <= 0):
        raise ValueError("Weibull target values must be strictly positive")
    X = df[inputs].to_numpy(dtype=float)
    X_tr, X_te, t_tr, t_te = _train_test(X, t, test_size, random_state)
    n_features = X_tr.shape[1]
    # Initial guess: log(scale) from OLS on log(t), shape ≈ 1
    log_t = np.log(t_tr)
    X_with_intercept = np.column_stack([np.ones(len(t_tr)), X_tr])
    beta_init, _, _, _ = np.linalg.lstsq(X_with_intercept, log_t, rcond=None)
    start = np.concatenate([beta_init, [0.0]])  # log(k)=0 → k=1

    result = minimize(
        _weibull_nll,
        start,
        args=(X_tr, t_tr),
        method="Nelder-Mead",
        options={"maxiter": 5000, "xatol": 1e-8, "fatol": 1e-8},
    )
    beta = result.x[:-1]
    log_k = result.x[-1]
    k = float(np.exp(log_k))
    lambda_te = np.exp(X_te @ beta)
    # Reliability at test times
    r_te = np.exp(-(t_te / lambda_te) ** k)
    # AIC
    aic = float(2 * (n_features + 1) - 2 * result.fun)
    # Median time-to-failure for test set
    median_ttf = float(lambda_te * (np.log(2) ** (1.0 / k)))
    coefficients = {
        inputs[i]: float(beta[i]) for i in range(n_features)
    }
    coefficients["_intercept"] = float(beta[0])
    coefficients["_weibull_shape"] = k
    return ModelFit(
        model_type="weibull_regression",
        target=target,
        inputs=list(inputs),
        metrics={
            "aic": aic,
            "shape_k": k,
            "median_ttf": float(np.mean(median_ttf)),
            "mean_ll": float(-result.fun / len(t_tr)),
        },
        coefficients=coefficients,
        equation=(
            f"Weibull(shape={k:.3f}), log(λ) = {beta[0]:.4g} + "
            + " + ".join(f"{beta[i+1]:+.4g}*{inputs[i]}" for i in range(n_features))
        ),
        n_train=len(t_tr),
        n_test=len(t_te),
        created_at=_now(),
        model={"beta": beta, "k": k, "inputs": inputs},
    )
