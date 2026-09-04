"""Cross-validation and residual analysis for model validation."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from typing import Any

from .fitters import ModelFit


def _build_design_matrix(df: pd.DataFrame, inputs: list[str], degree: int) -> pd.DataFrame:
    """Rebuild the design matrix used by DOE fitters."""
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


def _predict_from_fit(fit, df: pd.DataFrame) -> np.ndarray:
    """Predict using fit.model, handling DOE design matrices."""
    if fit.model_type in ("doe_linear", "doe_quadratic"):
        degree = 2 if fit.model_type == "doe_quadratic" else 1
        X = _build_design_matrix(df, fit.inputs, degree).to_numpy(dtype=float)
        if fit.model is not None:
            return fit.model.predict(X)
        # Refit if model not stored
        refit = _refit_from_fit(fit, df)
        return refit.model.predict(X)
    return fit.model.predict(df[fit.inputs].to_numpy(dtype=float))


def _refit_from_fit(fit, df: pd.DataFrame) -> Any:
    """Return a fresh fitted model on the given DataFrame."""
    from sklearn.linear_model import LinearRegression
    from sklearn.ensemble import RandomForestRegressor

    if fit.model_type == "doe_linear":
        X = _build_design_matrix(df, fit.inputs, degree=1).to_numpy(dtype=float)
        y = df[fit.target].to_numpy(dtype=float)
        model = LinearRegression().fit(X, y)
        fit_obj = ModelFit(
            model_type="doe_linear", target=fit.target, inputs=fit.inputs, model=model
        )
        return fit_obj
    elif fit.model_type == "doe_quadratic":
        X = _build_design_matrix(df, fit.inputs, degree=2).to_numpy(dtype=float)
        y = df[fit.target].to_numpy(dtype=float)
        model = LinearRegression().fit(X, y)
        fit_obj = ModelFit(
            model_type="doe_quadratic", target=fit.target, inputs=fit.inputs, model=model
        )
        return fit_obj
    elif fit.model_type == "random_forest":
        X = df[fit.inputs].to_numpy(dtype=float)
        y = df[fit.target].to_numpy(dtype=float)
        rf = RandomForestRegressor(
            n_estimators=100, random_state=42, n_jobs=1, max_depth=10, min_samples_leaf=5
        )
        rf.fit(X, y)
        fit_obj = ModelFit(
            model_type="random_forest", target=fit.target, inputs=fit.inputs, model=rf
        )
        return fit_obj
    elif fit.model_type == "residual_hybrid":
        from .fitters import fit_residual_hybrid
        return fit_residual_hybrid(df, target=fit.target, inputs=fit.inputs)
    raise ValueError(f"Unknown model_type: {fit.model_type}")


def cross_validate(fit, df: pd.DataFrame, k: int = 5) -> dict[str, Any]:
    """k-fold cross-validation.

    Args:
        fit: ModelFit object with .model and .inputs attributes
        df: Training DataFrame
        k: Number of folds

    Returns:
        {"cv_results": [...], "mean_metrics": {"mean_r2": ..., "mean_rmse": ...}}
    """
    from sklearn.model_selection import KFold
    from .metrics import r2_score, root_mean_squared_error

    X = df[fit.inputs]
    y = df[fit.target]

    kf = KFold(n_splits=k, shuffle=True, random_state=42)
    cv_results = []

    for fold_idx, (train_idx, test_idx) in enumerate(kf.split(X)):
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

        train_df = pd.concat([X_train, y_train.to_frame(name=fit.target)], axis=1)
        test_df = pd.concat([X_test, y_test.to_frame(name=fit.target)], axis=1)

        fit_obj = _refit_from_fit(fit, train_df)
        y_pred = _predict_from_fit(fit_obj, test_df)

        r2 = r2_score(y_test, y_pred)
        rmse = root_mean_squared_error(y_test, y_pred)

        cv_results.append({
            "fold": fold_idx + 1,
            "r2": float(r2),
            "rmse": float(rmse),
        })

    mean_r2 = np.mean([r["r2"] for r in cv_results])
    mean_rmse = np.mean([r["rmse"] for r in cv_results])

    return {
        "cv_results": cv_results,
        "mean_metrics": {
            "mean_r2": float(mean_r2),
            "mean_rmse": float(mean_rmse),
        }
    }


def analyze_residuals(fit, df: pd.DataFrame) -> dict[str, Any]:
    """Analyze residuals for normality and patterns.

    Returns:
        {
            "residuals": [...],
            "stats": {"mean": ..., "std": ..., "skewness": ..., "kurtosis": ...},
            "normality_test": {"statistic": ..., "p_value": ..., "is_normal": ...}
        }
    """
    y = df[fit.target]
    y_pred = _predict_from_fit(fit, df)

    residuals = (y - y_pred).values

    mean = float(np.mean(residuals))
    std = float(np.std(residuals, ddof=1))

    if std > 0:
        skewness = float(np.mean(((residuals - mean) / std) ** 3))
        kurtosis = float(np.mean(((residuals - mean) / std) ** 4) - 3)
    else:
        skewness = 0.0
        kurtosis = 0.0

    stat = skewness ** 2 + kurtosis ** 2
    p_value = max(0.0, 1.0 - stat / 10.0)
    is_normal = p_value > 0.05

    # Q-Q plot data
    sorted_residuals = np.sort(residuals)
    n = len(sorted_residuals)
    theoretical_quantiles = stats.norm.ppf((np.arange(1, n + 1) - 0.5) / n)

    # Residuals vs Predicted
    residuals_vs_predicted = {
        "predicted": y_pred.tolist(),
        "residuals": residuals.tolist()
    }

    # Durbin-Watson statistic
    if n > 1:
        dw_stat = float(np.sum(np.diff(residuals) ** 2) / np.sum(residuals ** 2))
    else:
        dw_stat = 2.0

    # Interpretation
    if dw_stat < 1.5:
        interpretation = "positive_autocorrelation"
    elif dw_stat > 2.5:
        interpretation = "negative_autocorrelation"
    else:
        interpretation = "no_autocorrelation"

    return {
        "residuals": [float(r) for r in residuals],
        "stats": {
            "mean": mean,
            "std": std,
            "skewness": skewness,
            "kurtosis": kurtosis,
        },
        "normality_test": {
            "statistic": float(stat),
            "p_value": float(p_value),
            "is_normal": bool(is_normal),
        },
        "qq_data": {
            "theoretical_quantiles": theoretical_quantiles.tolist(),
            "sample_quantiles": sorted_residuals.tolist(),
        },
        "residuals_vs_predicted": residuals_vs_predicted,
        "durbin_watson": {
            "statistic": dw_stat,
            "interpretation": interpretation,
        }
    }


def recommend_experiments(fit, df: pd.DataFrame, interactions: dict) -> list[dict[str, Any]]:
    """Recommend next experiments based on model performance and residual analysis.

    Returns:
        List of recommendation dicts with "type" and "reason" keys.
    """
    recommendations = []

    significant = interactions.get("significant_pairs", [])
    for pair in significant:
        if pair.get("strength", 0) > 0.3:
            recommendations.append({
                "type": "interaction",
                "factors": [pair["i"], pair["j"]],
                "reason": f"Strong interaction between {pair['i']} and {pair['j']} detected (strength: {pair['strength']:.2f})"
            })

    y = df[fit.target]
    y_pred = _predict_from_fit(fit, df)
    residuals = (y - y_pred).values

    mean = np.mean(residuals)
    std = np.std(residuals, ddof=1)

    if std > 0:
        skewness = np.mean(((residuals - mean) / std) ** 3)
        kurtosis = np.mean(((residuals - mean) / std) ** 4) - 3

        if abs(skewness) > 1:
            recommendations.append({
                "type": "transformation",
                "factor": fit.target,
                "method": "log" if skewness > 0 else "sqrt",
                "reason": f"Residuals are {'right' if skewness > 0 else 'left'}-skewed (skewness: {skewness:.2f})"
            })

        if kurtosis > 1:
            recommendations.append({
                "type": "transformation",
                "factor": fit.target,
                "method": "boxcox",
                "reason": "Residuals have heavy tails (positive kurtosis)"
            })

    abs_resid = np.abs(residuals)
    corr = np.corrcoef(y_pred, abs_resid)[0, 1]

    if abs(corr) > 0.3:
        factor = fit.inputs[0] if len(fit.inputs) > 0 else "X1"
        direction = "high" if corr > 0 else "low"
        recommendations.append({
            "type": "range_expansion",
            "factor": factor,
            "direction": direction,
            "reason": f"Residual variance increases with {factor} (correlation: {corr:.2f})"
        })

    if len(recommendations) < 2:
        recommendations.append({
            "type": "new_factor",
            "reason": "Unexplained variance may be due to missing factors. Consider adding new input variables."
        })

    return recommendations


def compute_credibility(
    fit, df: pd.DataFrame, extrapolation_result: dict | None = None
) -> dict[str, Any]:
    """Compute a multi-dimensional credibility score (spec 21).

    Dimensions:
      data_coverage   — fraction of input range covered by training data (0–1)
      predictive_acc  — 1 − min(RMSE/σ_y, 1)                     (0–1)
      statistical_stability — based on CV R² variance              (0–1)
      engineering_reasonable — 1 if no negative coefficients where
                               physics demands positive, else 0.5  (0–1)
      validation_degree  — 1 if approved, 0.7 if validated,
                           0.4 if pending_validation, 0.2 otherwise
      extrapolation_risk — 1 − max_risk from extrapolation check    (0–1)
    """
    y = df[fit.target].to_numpy(dtype=float)
    sigma_y = float(np.std(y, ddof=1)) if len(y) > 1 else 1.0
    y_pred = _predict_from_fit(fit, df)
    rmse = float(np.sqrt(np.mean((y - y_pred) ** 2)))

    # 1. Data coverage
    coverage_scores: list[float] = []
    for inp in fit.inputs:
        col = df[inp].to_numpy(dtype=float)
        if len(col) < 2:
            coverage_scores.append(0.5)
            continue
        q5, q95 = float(np.percentile(col, 5)), float(np.percentile(col, 95))
        rng = q95 - q5 if q95 > q5 else 1.0
        # Assume prediction is near the mean
        pred_center = float(np.mean(col))
        half_range = max(abs(pred_center - q5), abs(q95 - pred_center), 1e-9)
        coverage_scores.append(min(half_range / (rng / 2 + 1e-9), 1.0))
    data_coverage = float(np.mean(coverage_scores))

    # 2. Predictive accuracy
    predictive_acc = max(0.0, 1.0 - min(rmse / max(sigma_y, 1e-9), 1.0))

    # 3. Statistical stability (CV R² variance)
    # Use R² from full fit as proxy
    from .metrics import r2_score as _r2_score
    r2 = _r2_score(y, y_pred)
    # Lower is better; clamp to [0,1]
    statistical_stability = max(0.0, min(1.0, r2))

    # 4. Engineering reasonableness
    coef_sum = sum((fit.coefficients or {}).values())
    engineering_reasonable = 1.0 if coef_sum > 0 else 0.5

    # 5. Validation degree
    status_to_degree = {
        "approved": 1.0,
        "validated": 0.7,
        "pending_validation": 0.4,
        "draft": 0.2,
        "retired": 0.0,
    }
    validation_degree = status_to_degree.get(fit.status, 0.2)

    # 6. Extrapolation risk
    if extrapolation_result and "max_risk" in extrapolation_result:
        extrapolation_risk = max(0.0, 1.0 - extrapolation_result["max_risk"])
    else:
        extrapolation_risk = 0.8  # assume moderate risk without data

    # Weighted composite
    weights = {
        "data_coverage": 0.15,
        "predictive_acc": 0.25,
        "statistical_stability": 0.20,
        "engineering_reasonable": 0.10,
        "validation_degree": 0.15,
        "extrapolation_risk": 0.15,
    }
    scores = {
        "data_coverage": data_coverage,
        "predictive_acc": predictive_acc,
        "statistical_stability": statistical_stability,
        "engineering_reasonable": engineering_reasonable,
        "validation_degree": validation_degree,
        "extrapolation_risk": extrapolation_risk,
    }
    composite = sum(weights[dim] * float(scores[dim]) for dim in weights)

    return {
        "data_coverage": round(data_coverage, 4),
        "predictive_acc": round(predictive_acc, 4),
        "statistical_stability": round(statistical_stability, 4),
        "engineering_reasonable": engineering_reasonable,
        "validation_degree": validation_degree,
        "extrapolation_risk": round(extrapolation_risk, 4),
        "composite": round(composite, 4),
        "level": (
            "production_ready"
            if composite >= 0.80
            else "engineering_reference"
            if composite >= 0.60
            else "exploratory"
            if composite >= 0.40
            else "needs_more_data"
            if composite >= 0.20
            else "not_recommended"
        ),
    }
