import pandas as pd
import pytest

from process_intelligence_engine.modeling.fitters import fit_doe_categorical_factorial
from process_intelligence_engine.modeling.validation import compute_doe_statistics


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
