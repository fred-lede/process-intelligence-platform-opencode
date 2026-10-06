import pandas as pd
import pytest

from process_intelligence_engine.modeling.fitters import fit_doe_categorical_factorial
from process_intelligence_engine.modeling.validation import compute_doe_statistics
from process_intelligence_engine.prediction import predict_single
from process_intelligence_engine.modeling.shap_explainer import compute_shap


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
