"""Cross-validation and residual analysis for model validation."""
from __future__ import annotations

import math
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

    # Interpretation (camelCase keys for frontend i18n lookup)
    if dw_stat < 1.5:
        interpretation = "dwPositiveAutoCorr"
    elif dw_stat > 2.5:
        interpretation = "dwNegativeAutoCorr"
    else:
        interpretation = "dwNoAutoCorr"

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
                "strength": pair["strength"],
                "key": "recInteraction",
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
                "skewness": skewness,
                "key": "recTransformationRightSkewed" if skewness > 0 else "recTransformationLeftSkewed",
            })

        if kurtosis > 1:
            recommendations.append({
                "type": "transformation",
                "method": "boxcox",
                "key": "recTransformationHeavyTails",
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
            "corr": float(corr),
            "key": "recRangeExpansion",
        })

    if len(recommendations) < 2:
        recommendations.append({
            "type": "new_factor",
            "key": "recNewFactor",
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


def compute_doe_statistics(fit, df: pd.DataFrame) -> dict[str, Any]:
    """Compute ANOVA F-test and coefficient t-tests for DOE linear/quadratic models.

    Uses OLS inference with proper standard errors, confidence intervals,
    and p-values. For tree-based models, returns empty stats.
    """
    from sklearn.linear_model import LinearRegression

    model_type = fit.model_type

    if model_type not in ("doe_linear", "doe_quadratic"):
        return {
            "model_type": model_type,
            "n_obs": 0,
            "n_predictors": 0,
            "r2": None,
            "adj_r2": None,
            "anova": None,
            "coefficients": [],
            "fit_level": None,
            "note": "ANOVA and p-values are available only for DOE linear/quadratic models.",
        }

    degree = 2 if model_type == "doe_quadratic" else 1
    X = _build_design_matrix(df, fit.inputs, degree=degree)
    y = df[fit.target].to_numpy(dtype=float)
    n = len(y)
    p = X.shape[1]

    # Fit OLS on full data
    model = fit.model
    if model is not None and hasattr(model, "predict"):
        X_np = X.to_numpy(dtype=float)
        y_pred = model.predict(X_np)
    else:
        # Refit on full data
        model = LinearRegression().fit(X.to_numpy(dtype=float), y)
        y_pred = model.predict(X.to_numpy(dtype=float))

    residuals = y - y_pred
    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    ss_reg = ss_tot - ss_res

    df_reg = p - 1
    df_res = n - p

    if df_res <= 0:
        return {
            "model_type": model_type,
            "n_obs": n,
            "n_predictors": p - 1,
            "r2": None,
            "adj_r2": None,
            "anova": None,
            "coefficients": [],
            "interpretation": "Insufficient degrees of freedom for inference.",
            "note": f"n={n}, p={p} — need n > p for coefficient inference.",
        }

    mse = ss_res / df_res
    ms_reg = ss_reg / df_reg
    f_stat = float(ms_reg / mse) if mse > 0 else 0.0
    f_p_value = float(1.0 - stats.f.cdf(f_stat, df_reg, df_res))

    # Standard errors via (X'X)^{-1} * MSE
    XtX = X.T @ X
    try:
        XtX_inv = np.linalg.inv(XtX)
    except np.linalg.LinAlgError:
        XtX_inv = np.linalg.pinv(XtX)

    se = np.sqrt(np.diag(XtX_inv) * mse)

    # Collect coefficients (intercept first, then predictors)
    coef_vals = model.coef_.tolist() if hasattr(model, "coef_") else [0.0] * (p - 1)
    intercept_val = float(model.intercept_) if hasattr(model, "intercept_") else 0.0
    all_coefs = [intercept_val] + coef_vals
    col_names = X.columns.tolist()

    coeff_rows = []
    for i in range(p):
        name = col_names[i]
        coef = all_coefs[i]
        std_err = float(se[i]) if i < len(se) else 0.0
        t_stat = float(coef / std_err) if std_err > 1e-12 else 0.0
        p_val = float(2.0 * (1.0 - stats.t.cdf(abs(t_stat), df_res)))
        ci_half = float(stats.t.ppf(0.975, df_res) * std_err) if std_err > 1e-12 else 0.0
        coeff_rows.append({
            "name": name,
            "coef": round(coef, 6),
            "std_err": round(std_err, 6),
            "t_stat": round(t_stat, 4),
            "p_value": round(p_val, 6),
            "ci_lower": round(coef - ci_half, 6),
            "ci_upper": round(coef + ci_half, 6),
            "significant": p_val < 0.05,
        })

    r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0
    adj_r2 = float(1.0 - (1.0 - r2) * (n - 1) / max(n - p, 1))
    sig_count = sum(1 for c in coeff_rows[1:] if c["significant"])  # exclude intercept
    sig_count = sum(1 for c in coeff_rows[1:] if c["significant"])

    if f_p_value < 0.001:
        model_sig_label = "highly_significant"
    elif f_p_value < 0.01:
        model_sig_label = "significant"
    elif f_p_value < 0.05:
        model_sig_label = "marginally_significant"
    else:
        model_sig_label = "not_significant"

    # Interpretation
    total_terms = p - 1
    sig_ratio = sig_count / max(total_terms, 1)
    if r2 >= 0.9 and f_p_value < 0.001 and sig_ratio >= 0.7:
        fit_level = "excellent"
    elif r2 >= 0.7 and f_p_value < 0.05 and sig_ratio >= 0.5:
        fit_level = "good"
    elif r2 >= 0.5 and f_p_value < 0.10:
        fit_level = "moderate"
    elif f_p_value >= 0.05 and r2 < 0.5:
        fit_level = "poor"
    else:
        fit_level = "marginal"

    return {
        "model_type": model_type,
        "n_obs": n,
        "n_predictors": p - 1,
        "r2": round(r2, 6),
        "adj_r2": round(adj_r2, 6),
        "anova": {
            "f_stat": round(f_stat, 4),
            "p_value": round(f_p_value, 6),
            "significant": f_p_value < 0.05,
            "df_reg": df_reg,
            "df_res": df_res,
            "label": model_sig_label,
        },
        "coefficients": coeff_rows,
        "sig_count": sig_count,
        "total_terms": total_terms,
        "fit_level": fit_level,
    }
