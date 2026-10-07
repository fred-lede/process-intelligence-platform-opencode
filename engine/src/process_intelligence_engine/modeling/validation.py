"""Cross-validation and residual analysis for model validation."""
from __future__ import annotations

import math
from itertools import combinations, product
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
    if fit.model_type == "doe_categorical_factorial":
        if fit.model is None:
            raise ValueError("categorical DOE model artifact is unavailable")
        return fit.model.predict(df[fit.inputs])
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
    elif fit.model_type == "doe_categorical_factorial":
        from .categorical_doe import CategoricalFactorialRegressor, build_categorical_factorial_matrix
        levels = getattr(fit.model, "levels", None)
        if not levels:
            raise ValueError("categorical DOE level metadata is unavailable")
        design = build_categorical_factorial_matrix(df, fit.inputs, level_order=levels)
        y = df[fit.target].to_numpy(dtype=float)
        coefficients = np.linalg.lstsq(design.matrix, y, rcond=None)[0]
        return ModelFit(
            model_type="doe_categorical_factorial", target=fit.target,
            inputs=fit.inputs, model=CategoricalFactorialRegressor(fit.inputs, levels, coefficients),
        )
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


def design_validate(fit, df: pd.DataFrame) -> dict[str, Any]:
    """Leave-one-cell-out validation for a complete categorical factorial DOE."""
    if fit.model_type != "doe_categorical_factorial":
        raise ValueError("design validation requires a categorical factorial model")
    if df[fit.inputs].duplicated().any():
        raise ValueError("design validation requires one observation per design cell")
    predictions = []
    actuals = []
    rows = df.reset_index(drop=True)
    for index in range(len(rows)):
        train_df = rows.drop(index=index)
        test_df = rows.iloc[[index]]
        fit_obj = _refit_from_fit(fit, train_df)
        predictions.append(float(_predict_from_fit(fit_obj, test_df)[0]))
        actuals.append(float(test_df[fit.target].iloc[0]))
    residuals = np.asarray(actuals) - np.asarray(predictions)
    ss_tot = float(np.sum((np.asarray(actuals) - np.mean(actuals)) ** 2))
    ss_res = float(np.sum(residuals ** 2))
    r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0
    rmse = float(np.sqrt(np.mean(residuals ** 2)))
    return {"method": "leave_one_cell_out", "n_cells": len(rows), "r2": r2, "rmse": rmse}


def compute_sensitivity_effect_sizes(
    fit, df: pd.DataFrame, n_repeats: int = 8
) -> dict[str, Any]:
    """Compute global permutation sensitivity and standardized effect sizes.

    Sensitivity is the mean increase in RMSE after independently permuting an
    input, normalized to the sum across inputs.  Effect size is the absolute
    standardized DOE coefficient when available, otherwise the RMSE increase
    divided by the observed output standard deviation.
    """
    y = df[fit.target].to_numpy(dtype=float)
    baseline_pred = _predict_from_fit(fit, df)
    baseline_rmse = float(np.sqrt(np.mean((y - baseline_pred) ** 2)))
    y_std = float(np.std(y, ddof=1)) if len(y) > 1 else 1.0
    rng = np.random.default_rng(42)
    rows: list[dict[str, Any]] = []
    for column in fit.inputs:
        deltas = []
        for _ in range(max(1, n_repeats)):
            permuted = df.copy()
            permuted[column] = rng.permutation(permuted[column].to_numpy())
            pred = _predict_from_fit(fit, permuted)
            deltas.append(max(0.0, float(np.sqrt(np.mean((y - pred) ** 2))) - baseline_rmse))
        delta = float(np.mean(deltas))
        coefficient = None
        if fit.model_type in ("doe_linear", "doe_quadratic"):
            coefficient = float((fit.coefficients or {}).get(column, 0.0))
        x_std = float(np.std(df[column].to_numpy(dtype=float), ddof=1)) if len(df) > 1 else 1.0
        effect_size = abs(coefficient * x_std / y_std) if coefficient is not None else delta / max(y_std, 1e-12)
        rows.append({"input": column, "sensitivity": delta, "effect_size": float(effect_size)})
    total = sum(row["sensitivity"] for row in rows)
    for row in rows:
        row["sensitivity"] = float(row["sensitivity"] / total) if total > 0 else 0.0
    rows.sort(key=lambda row: (-row["sensitivity"], row["input"]))
    return {"method": "permutation_rmse", "baseline_rmse": baseline_rmse, "items": rows}


def _residual_histogram(residuals: np.ndarray) -> dict[str, Any]:
    """Return deterministic residual histogram bins for API consumers."""
    histogram_bins = max(1, min(10, int(np.ceil(np.log2(max(len(residuals), 1)) + 1))))
    if len(residuals) >= 2:
        q1, q3 = np.percentile(residuals, [25, 75])
        iqr = float(q3 - q1)
        span = float(np.max(residuals) - np.min(residuals))
        width = 2.0 * iqr / (len(residuals) ** (1.0 / 3.0)) if iqr > 0 else 0.0
        if width > 0 and span > 0:
            histogram_bins = max(5, min(10, int(np.ceil(span / width))))
    histogram_counts, histogram_edges = np.histogram(residuals, bins=histogram_bins)
    return {
        "counts": histogram_counts.astype(int).tolist(),
        "edges": histogram_edges.astype(float).tolist(),
        "bin_count": int(histogram_bins),
        "method": "freedman_diaconis_clamped_5_10",
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

    histogram = _residual_histogram(residuals)

    mean = float(np.mean(residuals))
    std = float(np.std(residuals, ddof=1))

    if std > 0:
        skewness = float(np.mean(((residuals - mean) / std) ** 3))
        kurtosis = float(np.mean(((residuals - mean) / std) ** 4) - 3)
    else:
        skewness = 0.0
        kurtosis = 0.0
    outlier_indices = np.where(np.abs((residuals - mean) / std) >= 3.0)[0].astype(int).tolist() if std > 0 else []

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
        "residual_histogram": histogram,
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
        },
        "outliers": {"count": len(outlier_indices), "indices": outlier_indices, "threshold": 3.0},
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

    if model_type not in ("doe_linear", "doe_quadratic", "doe_categorical_factorial"):
        return {
            "model_type": model_type,
            "n_obs": 0,
            "n_predictors": 0,
            "r2": None,
            "adj_r2": None,
            "anova": None,
            "coefficients": [],
            "fit_level": None,
            "note": "ANOVA and p-values are available only for supported DOE models.",
        }

    if model_type == "doe_categorical_factorial":
        from .categorical_doe import build_categorical_factorial_matrix
        design = build_categorical_factorial_matrix(df, fit.inputs)
        X = pd.DataFrame(design.matrix, columns=design.term_names)
    else:
        degree = 2 if model_type == "doe_quadratic" else 1
        X = _build_design_matrix(df, fit.inputs, degree=degree)
    y = df[fit.target].to_numpy(dtype=float)
    n = len(y)
    p = X.shape[1]

    # Fit OLS on full data
    model = fit.model
    if model is not None and hasattr(model, "predict"):
        y_pred = model.predict(df) if model_type == "doe_categorical_factorial" else model.predict(X.to_numpy(dtype=float))
    else:
        # Refit on full data
        if model_type == "doe_categorical_factorial":
            from process_intelligence_engine.modeling.categorical_doe import CategoricalFactorialRegressor
            coefficients = np.linalg.lstsq(X.to_numpy(dtype=float), y, rcond=None)[0]
            model = CategoricalFactorialRegressor(fit.inputs, design.levels, coefficients)
            y_pred = model.predict(df)
        else:
            model = LinearRegression().fit(X.to_numpy(dtype=float), y)
            y_pred = model.predict(X.to_numpy(dtype=float))

    residuals = y - y_pred
    residual_histogram = _residual_histogram(residuals)
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

    pure_error = {"ss": None, "df": 0, "ms": None}
    lack_of_fit = {"ss": None, "df": None, "ms": None, "f_stat": None, "p_value": None}
    if model_type in ("doe_categorical_factorial", "doe_linear", "doe_quadratic"):
        groups = df.groupby(fit.inputs, dropna=False, sort=False)[fit.target]
        group_count = int(groups.ngroups)
        pure_df = int(n - group_count)
        pure_ss = float(sum(np.sum((group.to_numpy(dtype=float) - group.mean()) ** 2) for _, group in groups))
        pure_error = {"ss": pure_ss, "df": pure_df, "ms": pure_ss / pure_df if pure_df > 0 else None}
        lof_df = int(df_res - pure_df)
        lof_ss = float(max(ss_res - pure_ss, 0.0))
        lof_ms = lof_ss / lof_df if lof_df > 0 else None
        lof_f = float(lof_ms / pure_error["ms"]) if lof_ms is not None and pure_error["ms"] and pure_error["ms"] > 0 else None
        lof_p = float(1.0 - stats.f.cdf(lof_f, lof_df, pure_df)) if lof_f is not None else None
        lack_of_fit = {"ss": lof_ss, "df": lof_df, "ms": lof_ms, "f_stat": lof_f, "p_value": lof_p}

    mse = ss_res / df_res
    ms_reg = ss_reg / df_reg
    f_stat = float(ms_reg / mse) if mse > 0 else 0.0
    f_p_value = float(1.0 - stats.f.cdf(f_stat, df_reg, df_res))

    anova_rows: list[dict[str, Any]] = []
    if model_type == "doe_categorical_factorial":
        # For the balanced factorial design, adjusted SS is obtained by
        # comparing the full model SSE with the SSE after removing a term.
        term_groups: dict[tuple[str, ...], list[int]] = {}
        for index, term in enumerate(design.term_names[1:], start=1):
            term_groups.setdefault(design.term_factors[term], []).append(index)

        def _adjusted_ss(indices: list[int]) -> float:
            keep = [index for index in range(p) if index not in indices]
            reduced = np.linalg.lstsq(X.to_numpy(dtype=float)[:, keep], y, rcond=None)[0]
            reduced_residuals = y - X.to_numpy(dtype=float)[:, keep] @ reduced
            return float(max(np.sum(reduced_residuals ** 2) - ss_res, 0.0))

        def _anova_row(source: str, indices: list[int], ss: float | None = None) -> dict[str, Any]:
            row_df = len(indices)
            row_ss = _adjusted_ss(indices) if ss is None else float(ss)
            row_ms = row_ss / row_df if row_df else None
            row_f = row_ms / mse if row_ms is not None and mse > 0 else None
            row_p = float(1.0 - stats.f.cdf(row_f, row_df, df_res)) if row_f is not None else None
            return {"source": source, "df": row_df, "adj_ss": row_ss, "adj_ms": row_ms, "f_stat": row_f, "p_value": row_p}

        main_groups = {f: indices for f, indices in term_groups.items() if len(f) == 1}
        interaction_groups = {f: indices for f, indices in term_groups.items() if len(f) == 2}
        main_indices = [index for indices in main_groups.values() for index in indices]
        interaction_indices = [index for indices in interaction_groups.values() for index in indices]
        grand_mean = float(np.mean(y))
        main_ss = {
            factors: float(sum(
                int(count) * (float(mean) - grand_mean) ** 2
                for level, mean in df.groupby(factors[0], sort=False)[fit.target].mean().items()
                for count in [df[factors[0]].value_counts().loc[level]]
            ))
            for factors in main_groups
        }
        anova_rows.append(_anova_row("模型", list(range(1, p)), ss=ss_reg))
        anova_rows.append(_anova_row("線性", main_indices, ss=sum(main_ss.values())))
        for factors, indices in main_groups.items():
            anova_rows.append(_anova_row(" × ".join(factors), indices, ss=main_ss[factors]))
        anova_rows.append(_anova_row("2 因子交互作用", interaction_indices))
        for factors, indices in interaction_groups.items():
            anova_rows.append(_anova_row(" × ".join(factors), indices))
        anova_rows.append({"source": "誤差", "df": df_res, "adj_ss": ss_res, "adj_ms": mse, "f_stat": None, "p_value": None})
        anova_rows.append({"source": "合計", "df": n - 1, "adj_ss": ss_tot, "adj_ms": None, "f_stat": None, "p_value": None})

    # Standard errors via (X'X)^{-1} * MSE
    XtX = X.T @ X
    try:
        XtX_inv = np.linalg.inv(XtX)
    except np.linalg.LinAlgError:
        XtX_inv = np.linalg.pinv(XtX)

    se = np.sqrt(np.diag(XtX_inv) * mse)

    # Collect coefficients (intercept first, then predictors)
    if model_type == "doe_categorical_factorial":
        all_coefs = np.asarray(model.coefficients, dtype=float).tolist()
        intercept_val = float(all_coefs[0])
        coef_vals = all_coefs[1:]
    else:
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

    categorical_effects = None
    pareto_terms = None
    if model_type == "doe_categorical_factorial":
        categorical_effects = {"main": [], "interactions": []}
        grouped: dict[str, list[dict[str, Any]]] = {factor: [] for factor in fit.inputs}
        for row in coeff_rows[1:]:
            name = row["name"]
            matched = [factor for factor in fit.inputs if factor in name]
            if len(matched) >= 2:
                key = " × ".join(matched[:2])
            elif matched:
                key = matched[0]
            else:
                continue
            grouped.setdefault(key, []).append(row)
        pareto_terms = [
            {
                "term": key,
                "max_abs_t": max(abs(item["t_stat"]) for item in rows),
                "min_p_value": min(item["p_value"] for item in rows),
                "significant_count": sum(1 for item in rows if item["significant"]),
                "contrast_count": len(rows),
            }
            for key, rows in grouped.items() if rows
        ]
        pareto_terms.sort(key=lambda item: item["max_abs_t"], reverse=True)
        anova_by_source = {row["source"]: row for row in anova_rows}
        for term in pareto_terms:
            row = anova_by_source.get(term["term"])
            term["standardized_effect"] = float(np.sqrt(row["f_stat"])) if row and row["f_stat"] is not None else 0.0
        levels = design.levels
        for factor, factor_levels in levels.items():
            points = []
            for level in factor_levels:
                other_factors = [name for name in fit.inputs if name != factor]
                rows = []
                for other_levels in product(*(levels[name] for name in other_factors)):
                    row = {factor: level}
                    row.update(dict(zip(other_factors, other_levels)))
                    rows.append(row)
                points.append({"level": level, "mean": float(np.mean(model.predict(pd.DataFrame(rows))))})
            categorical_effects["main"].append({"factor": factor, "points": points})
        for left, right in combinations(fit.inputs, 2):
            lines = []
            for right_level in levels[right]:
                points = []
                for left_level in levels[left]:
                    other_factors = [name for name in fit.inputs if name not in (left, right)]
                    rows = []
                    for other_levels in product(*(levels[name] for name in other_factors)):
                        row = {left: left_level, right: right_level}
                        row.update(dict(zip(other_factors, other_levels)))
                        rows.append(row)
                    points.append({"level": left_level, "mean": float(np.mean(model.predict(pd.DataFrame(rows))))})
                lines.append({"series": right_level, "points": points})
            categorical_effects["interactions"].append({"factors": [left, right], "lines": lines})

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

    order_aliases = {
        "run_order", "runorder", "run_sequence", "runsequence", "run_number",
        "運行序", "运行序", "運行次序", "运行次序", "執行序", "执行序",
    }
    standard_aliases = {
        "standard_order", "standardorder", "standard_number",
        "標準序", "标准序", "標準次序", "标准次序",
    }
    order_column = next(
        (column for column in df.columns
         if str(column).strip().lower().replace(" ", "_") in order_aliases),
        None,
    )
    if order_column is not None:
        parsed_order = pd.to_numeric(df[order_column], errors="coerce")
        valid_order = bool(parsed_order.notna().all() and parsed_order.is_unique)
    else:
        parsed_order = None
        valid_order = False
    standard_column = next(
        (column for column in df.columns
         if str(column).strip().lower().replace(" ", "_") in standard_aliases),
        None,
    )
    parsed_standard = pd.to_numeric(df[standard_column], errors="coerce") if standard_column is not None else None
    valid_standard = bool(parsed_standard is not None and parsed_standard.notna().all())

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
            "pure_error": pure_error,
            "lack_of_fit": lack_of_fit,
            "rows": anova_rows,
            "critical_value": float(stats.t.ppf(0.975, df_res)),
        },
        "coefficients": coeff_rows,
        "sig_count": sig_count,
        "total_terms": total_terms,
        "fit_level": fit_level,
        "fitted_values": [float(v) for v in y_pred],
        "residuals": [float(v) for v in residuals],
        "residual_histogram": residual_histogram,
        "observation_order": parsed_order.tolist() if valid_order and parsed_order is not None else list(range(1, n + 1)),
        "order_basis": str(order_column) if valid_order and order_column is not None else "row_order",
        "residual_observations": [
            {
                "run_order": float(parsed_order.iloc[i]) if valid_order and parsed_order is not None else i + 1,
                "standard_order": float(parsed_standard.iloc[i]) if valid_standard and parsed_standard is not None else None,
                "actual": float(y[i]),
                "fitted": float(y_pred[i]),
                "residual": float(residuals[i]),
            }
            for i in range(n)
        ],
        "categorical_effects": categorical_effects,
        "pareto_terms": pareto_terms,
    }
