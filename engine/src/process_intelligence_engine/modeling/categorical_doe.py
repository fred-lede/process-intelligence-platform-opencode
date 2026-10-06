"""Design matrices and validation for three-level categorical factorial DOE."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, product
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class CategoricalDesignMatrix:
    matrix: np.ndarray
    term_names: list[str]
    levels: dict[str, list[Any]]
    model_df: int
    residual_df: int
    term_factors: dict[str, tuple[str, ...]]


class CategoricalFactorialRegressor:
    def __init__(self, factors: list[str], levels: dict[str, list[Any]], coefficients: np.ndarray):
        self.factors = list(factors)
        self.levels = levels
        self.coefficients = np.asarray(coefficients, dtype=float)

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        for factor in self.factors:
            unseen = set(frame[factor].dropna().tolist()) - set(self.levels[factor])
            if unseen:
                raise ValueError(f"unseen factor level for {factor}: {sorted(unseen)!r}")
        # Reuse fitted level order by constructing the matrix against all fitted levels.
        columns = [np.ones(len(frame), dtype=float)]
        encoded = {}
        for factor in self.factors:
            encoded[factor] = []
            for level in self.levels[factor][1:]:
                values = (frame[factor].to_numpy() == level).astype(float)
                encoded[factor].append(values)
                columns.append(values)
        for left, right in combinations(self.factors, 2):
            for left_values in encoded[left]:
                for right_values in encoded[right]:
                    columns.append(left_values * right_values)
        return np.column_stack(columns) @ self.coefficients


def _levels(df: pd.DataFrame, factors: list[str]) -> dict[str, list[Any]]:
    if not factors:
        raise ValueError("at least one factor is required")
    missing = [factor for factor in factors if factor not in df.columns]
    if missing:
        raise ValueError(f"missing factor column: {missing[0]}")
    result: dict[str, list[Any]] = {}
    for factor in factors:
        if df[factor].isna().any():
            raise ValueError(f"missing factor level: {factor}")
        values = sorted(df[factor].unique().tolist())
        if len(values) < 2:
            raise ValueError(f"factor must have at least two levels: {factor}")
        result[factor] = values
    return result


def validate_categorical_factorial_design(df: pd.DataFrame, factors: list[str]) -> dict:
    levels = _levels(df, factors)
    observed = [tuple(row[factor] for factor in factors) for _, row in df[factors].iterrows()]
    counts = pd.Series(observed).value_counts()
    expected = set(product(*(levels[factor] for factor in factors)))
    observed_set = set(observed)
    duplicate = [list(key) for key, count in counts.items() if count > 1]
    missing = [list(key) for key in sorted(expected - observed_set)]
    status = "warning" if duplicate or missing else "ready"
    return {
        "status": status,
        "row_count": len(df),
        "expected_combinations": len(expected),
        "observed_combinations": len(observed_set),
        "duplicate_combinations": duplicate,
        "missing_combinations": missing,
        "levels": levels,
    }


def build_categorical_factorial_matrix(
    df: pd.DataFrame,
    factors: list[str],
    include_two_factor_interactions: bool = True,
    include_three_factor_interaction: bool = False,
) -> CategoricalDesignMatrix:
    levels = _levels(df, factors)
    columns = [np.ones(len(df), dtype=float)]
    terms = ["1"]
    term_factors: dict[str, tuple[str, ...]] = {"1": ()}

    # Reference-level treatment coding: one column per non-reference level.
    encoded: dict[str, list[tuple[str, np.ndarray]]] = {}
    for factor in factors:
        encoded[factor] = []
        for level in levels[factor][1:]:
            name = f"{factor}[{level}]"
            values = (df[factor].to_numpy() == level).astype(float)
            encoded[factor].append((name, values))
            columns.append(values)
            terms.append(name)
            term_factors[name] = (factor,)

    if include_two_factor_interactions:
        for left, right in combinations(factors, 2):
            for left_name, left_values in encoded[left]:
                for right_name, right_values in encoded[right]:
                    name = f"{left}:{right}:{left_name.split('[', 1)[1][:-1]}:{right_name.split('[', 1)[1][:-1]}"
                    columns.append(left_values * right_values)
                    terms.append(name)
                    term_factors[name] = (left, right)

    if include_three_factor_interaction and len(factors) >= 3:
        for names in product(*(encoded[factor] for factor in factors)):
            term_names = [item[0] for item in names]
            name = ":".join(factor for factor in factors) + ":" + ":".join(
                item.split("[", 1)[1][:-1] for item in term_names
            )
            values = np.ones(len(df), dtype=float)
            for _, item_values in names:
                values *= item_values
            columns.append(values)
            terms.append(name)
            term_factors[name] = tuple(factors)

    matrix = np.column_stack(columns)
    return CategoricalDesignMatrix(
        matrix=matrix,
        term_names=terms,
        levels=levels,
        model_df=matrix.shape[1] - 1,
        residual_df=len(df) - matrix.shape[1],
        term_factors=term_factors,
    )
