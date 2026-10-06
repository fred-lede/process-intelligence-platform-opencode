import pandas as pd
import pytest
from itertools import product

from process_intelligence_engine.modeling.categorical_doe import (
    build_categorical_factorial_matrix,
    validate_categorical_factorial_design,
)


def _frame():
    rows = []
    for a in (40, 60, 80):
        for b in (5, 7, 9):
            for c in (0.0, 0.5, 1.0):
                rows.append({"A": a, "B": b, "C": c})
    return pd.DataFrame(rows)


def test_three_level_numeric_factors_are_coded_as_categories_with_18_model_df():
    result = build_categorical_factorial_matrix(_frame(), ["A", "B", "C"])

    assert result.levels == {"A": [40, 60, 80], "B": [5, 7, 9], "C": [0.0, 0.5, 1.0]}
    assert result.matrix.shape == (27, 19)  # intercept + 6 main + 12 pairwise
    assert result.model_df == 18
    assert result.residual_df == 8
    assert any(name.startswith("A:") for name in result.term_names)
    assert any(name.startswith("A:B:") for name in result.term_names)


def test_design_validation_reports_missing_and_duplicate_combinations():
    frame = _frame().drop(index=0).copy()
    frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)

    report = validate_categorical_factorial_design(frame, ["A", "B", "C"])

    assert report["status"] == "warning"
    assert report["duplicate_combinations"]
    assert report["missing_combinations"]


def test_null_factor_level_is_rejected():
    frame = _frame()
    frame.loc[0, "A"] = None

    with pytest.raises(ValueError, match="missing factor level"):
        build_categorical_factorial_matrix(frame, ["A", "B", "C"])


def test_four_and_five_factors_use_the_same_pairwise_expansion():
    for count, expected_predictors in ((4, 32), (5, 50)):
        factors = [f"F{i}" for i in range(count)]
        frame = pd.DataFrame(
            [dict(zip(factors, values)) for values in product((0, 1, 2), repeat=count)]
        )
        result = build_categorical_factorial_matrix(frame, factors)
        assert result.model_df == expected_predictors
        assert result.matrix.shape == (3**count, expected_predictors + 1)
