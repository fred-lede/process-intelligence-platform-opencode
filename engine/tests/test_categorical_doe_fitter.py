import pandas as pd
import pytest

from process_intelligence_engine.modeling.fitters import fit_doe_categorical_factorial
from process_intelligence_engine.modeling.validation import compute_doe_statistics, cross_validate
from process_intelligence_engine.prediction import predict_single
from process_intelligence_engine.modeling.shap_explainer import compute_shap
from process_intelligence_engine.modeling.model_selection import compare_models
from process_intelligence_engine.modeling.validation import analyze_residuals, compute_credibility
from process_intelligence_engine.modeling.interactions import compute_interactions
from process_intelligence_engine.monte_carlo import predict_output
from process_intelligence_engine.optimization import run_optquest


def _frame():
    rows = []
    for a in (40, 60, 80):
        for b in (5, 7, 9):
            for c in (0.0, 0.5, 1.0):
                rows.append({"A": a, "B": b, "C": c, "Y": a / 100 + b / 100 + c})
    return pd.DataFrame(rows)


def test_categorical_factorial_fit_has_minitab_model_shape_and_predicts():
    fit = fit_doe_categorical_factorial(_frame(), "Y", ["A", "B", "C"])

    assert fit.model_type == "doe_categorical_factorial"
    assert len(fit.coefficients) == 19  # 18 terms plus _intercept
    assert fit.n_train == 27
    assert fit.model.predict(_frame().iloc[[0]])[0] == pytest.approx(_frame().iloc[0]["Y"])


def test_categorical_factorial_fit_rejects_incomplete_design():
    frame = _frame().drop(index=0)
    with pytest.raises(ValueError, match="duplicate or missing"):
        fit_doe_categorical_factorial(frame, "Y", ["A", "B", "C"])


def test_categorical_factorial_fit_rejects_too_many_factors_for_sample_size():
    frame = _frame().head(19)
    with pytest.raises(ValueError, match="duplicate or missing"):
        fit_doe_categorical_factorial(frame, "Y", ["A", "B", "C"])


def test_categorical_factorial_statistics_match_minitab_df_shape():
    frame = _frame()
    fit = fit_doe_categorical_factorial(frame, "Y", ["A", "B", "C"])
    stats = compute_doe_statistics(fit, frame)

    assert stats["anova"]["df_reg"] == 18
    assert stats["anova"]["df_res"] == 8
    assert len(stats["coefficients"]) == 19
    assert [item["term"] for item in stats["pareto_terms"]] == ["A", "B", "C", "A × B", "A × C", "B × C"] or {item["term"] for item in stats["pareto_terms"]} == {"A", "B", "C", "A × B", "A × C", "B × C"}


def test_categorical_effects_are_marginal_means_over_other_factors():
    frame = _frame()
    fit = fit_doe_categorical_factorial(frame, "Y", ["A", "B", "C"])
    stats = compute_doe_statistics(fit, frame)
    main_a = next(item for item in stats["categorical_effects"]["main"] if item["factor"] == "A")

    expected = frame.groupby("A", sort=True)["Y"].mean().tolist()
    assert [point["mean"] for point in main_a["points"]] == pytest.approx(expected)


def test_categorical_prediction_accepts_named_input_mapping():
    frame = _frame()
    fit = fit_doe_categorical_factorial(frame, "Y", ["A", "B", "C"])
    value = predict_single("doe_categorical_factorial", fit.coefficients or {}, {"A": 40, "B": 5, "C": 0.0}, model=fit.model, feature_names=fit.inputs)
    assert value == pytest.approx(frame.iloc[0]["Y"])


def test_categorical_doe_supports_original_factor_shap_explanations():
    frame = _frame()
    fit = fit_doe_categorical_factorial(frame, "Y", ["A", "B", "C"])
    result = compute_shap(fit, frame)

    assert {item["name"] for item in result["feature_importance"]} == {"A", "B", "C"}
    assert len(result["shap_values"]) == len(frame)


def test_categorical_doe_can_run_validation_re_fits():
    frame = _frame()
    fit = fit_doe_categorical_factorial(frame, "Y", ["A", "B", "C"])
    result = cross_validate(fit, frame, k=3)

    assert len(result["cv_results"]) == 3


def test_categorical_doe_supports_full_validation_chain():
    frame = _frame()
    fit = fit_doe_categorical_factorial(frame, "Y", ["A", "B", "C"])
    comparison = compare_models([fit], frame, k=3)

    assert comparison["models"]
    assert analyze_residuals(fit, frame)["residuals"]
    assert compute_interactions(fit, frame)["factors"] == ["A", "B", "C"]
    assert "composite" in compute_credibility(fit, frame)


def test_categorical_interactions_are_nonzero_when_pair_is_nonadditive():
    frame = _frame()
    frame["Y"] = frame["Y"] + ((frame["A"] == 80) & (frame["B"] == 9)).astype(float) * 10
    fit = fit_doe_categorical_factorial(frame, "Y", ["A", "B", "C"])
    result = compute_interactions(fit, frame)
    ab = next(pair for pair in result["significant_pairs"] if {pair["i"], pair["j"]} == {"A", "B"})
    assert ab["strength"] > 0


def test_categorical_doe_supports_monte_carlo_prediction():
    frame = _frame()
    fit = fit_doe_categorical_factorial(frame, "Y", ["A", "B", "C"])
    value = predict_output("doe_categorical_factorial", fit.coefficients or {}, {"A": 40, "B": 5, "C": 0.0}, model=fit.model, feature_names=fit.inputs)
    assert value == pytest.approx(frame.iloc[0]["Y"])


def test_categorical_doe_supports_optquest_discrete_levels():
    frame = _frame()
    fit = fit_doe_categorical_factorial(frame, "Y", ["A", "B", "C"])
    result = run_optquest(fit, frame, objective="hit_target", lsl=None, usl=None,
                          target_value=1.0, n_candidates=6, n_eval_samples=5, seed=7)

    assert result["best_point"]["A"] in (40, 60, 80)
    assert result["best_point"]["B"] in (5, 7, 9)
    assert result["best_point"]["C"] in (0.0, 0.5, 1.0)
