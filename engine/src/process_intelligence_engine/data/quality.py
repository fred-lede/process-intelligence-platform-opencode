"""Data quality checks.

Implements the Phase 1 quality checks from the spec (§10.1), each issue
carries a status, severity, human-readable message and machine-checkable
detail fields. The report is deterministic for a given input.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import pandas as pd

UNBALANCED_OKNG_RATIO_THRESHOLD = 0.25


class QualityStatus(str, Enum):
    """Overall issue severity."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class QualityCheck(str, Enum):
    MISSING_VALUE = "missing_value"
    DUPLICATE = "duplicate"
    INVALID_FORMAT = "invalid_format"
    UNIT_MIXING = "unit_mixing"
    CONSTANT_COLUMN = "constant_column"
    EXTREME_OUTLIER = "extreme_outlier"
    OUTLIER = "outlier"
    TIME_ORDER = "time_order"
    BATCH_IMBALANCE = "batch_imbalance"
    UNBALANCED_OKNG = "unbalanced_okng"
    INPUT_OUT_OF_RANGE = "input_out_of_range"
    MISSING_SPEC = "missing_spec"


@dataclass
class QualityIssue:
    check: QualityCheck
    column: str | None
    severity: QualityStatus
    message: str
    detail: dict = field(default_factory=dict)


@dataclass
class QualityReport:
    row_count: int
    column_count: int
    issues: list[QualityIssue] = field(default_factory=list)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    def issues_by_severity(self) -> dict[QualityStatus, int]:
        counts = {s: 0 for s in QualityStatus}
        for i in self.issues:
            if i.severity in counts:
                counts[i.severity] += 1
        return counts


def _classify_outlier(value: float, median: float, mad: float) -> str:
    """Classify an extreme value into the spec's four categories.

    Heuristic Phase 1: distance from median in MAD units guides the
    classification, defaulting to 'undetermined'.
    """
    if mad == 0:
        return "possible_measurement_error"
    z = abs(value - median) / (1.4826 * mad)
    if z >= 10:
        return "possible_measurement_error"
    if z >= 5:
        return "possible_process_anomaly"
    return "undetermined"


def _check_missing(df: pd.DataFrame, issues: list[QualityIssue]) -> None:
    for col in df.columns:
        missing = int(df[col].isna().sum())
        if missing == 0:
            continue
        rate = missing / max(df.shape[0], 1)
        severity = QualityStatus.CRITICAL if rate > 0.5 else QualityStatus.WARNING
        issues.append(
            QualityIssue(
                check=QualityCheck.MISSING_VALUE,
                column=str(col),
                severity=severity,
                message=f"Column '{col}' has {missing} missing values ({rate:.1%}).",
                detail={"missing_count": missing, "missing_rate": rate},
            )
        )


def _check_duplicates(df: pd.DataFrame, issues: list[QualityIssue]) -> None:
    dupes = int(df.duplicated().sum())
    if dupes > 0:
        issues.append(
            QualityIssue(
                check=QualityCheck.DUPLICATE,
                column=None,
                severity=QualityStatus.WARNING,
                message=f"Found {dupes} fully duplicated row(s).",
                detail={"duplicate_count": dupes},
            )
        )


def _check_constant(df: pd.DataFrame, issues: list[QualityIssue]) -> None:
    for col in df.columns:
        if df[col].nunique(dropna=True) <= 1:
            issues.append(
                QualityIssue(
                    check=QualityCheck.CONSTANT_COLUMN,
                    column=str(col),
                    severity=QualityStatus.WARNING,
                    message=f"Column '{col}' is constant — carries no analytical information.",
                    detail={"unique_values": int(df[col].nunique(dropna=True))},
                )
            )


def _check_outliers(
    df: pd.DataFrame,
    issues: list[QualityIssue],
    categorical_columns: list[str],
) -> None:
    numeric_columns = [
        str(c) for c in df.columns
        if pd.api.types.is_numeric_dtype(df[c]) and str(c) not in categorical_columns
    ]
    for col in numeric_columns:
        series = df[col].dropna().astype(float)
        if len(series) < 5:
            continue
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        outliers = series[(series < lower) | (series > upper)]
        if outliers.empty:
            continue
        median = float(series.median())
        mad = float((series - median).abs().median())
        classifications = {
            "possible_measurement_error": 0,
            "possible_process_anomaly": 0,
            "true_extreme_event": 0,
            "undetermined": 0,
        }
        for v in outliers:
            classifications[_classify_outlier(float(v), median, mad)] += 1
        issues.append(
            QualityIssue(
                check=QualityCheck.OUTLIER,
                column=str(col),
                severity=QualityStatus.WARNING,
                message=(
                    f"Column '{col}' has {len(outliers)} potential outlier(s) "
                    f"({len(outliers) / len(series):.1%})."
                ),
                detail={
                    "outlier_count": int(len(outliers)),
                    "outlier_lower": float(lower),
                    "outlier_upper": float(upper),
                    "classification": max(classifications, key=classifications.get) or "undetermined",
                },
            )
        )


def _check_time_order(
    df: pd.DataFrame,
    issues: list[QualityIssue],
    datetime_columns: list[str],
) -> None:
    for col in datetime_columns:
        if col not in df.columns:
            continue
        parsed = []
        for v in df[col].dropna():
            try:
                parsed.append(pd.Timestamp(str(v)).to_pydatetime())
            except (ValueError, TypeError):
                continue
        if len(parsed) < 2:
            continue
        if parsed != sorted(parsed):
            issues.append(
                QualityIssue(
                    check=QualityCheck.TIME_ORDER,
                    column=str(col),
                    severity=QualityStatus.WARNING,
                    message=f"Column '{col}' is not in chronological order.",
                    detail={"reorder_count": _count_out_of_order(parsed)},
                )
            )


def _count_out_of_order(values: list[datetime]) -> int:
    if not values:
        return 0
    count = 0
    for i in range(1, len(values)):
        if values[i] < values[i - 1]:
            count += 1
    return count


def _check_unbalanced_okng(
    df: pd.DataFrame,
    issues: list[QualityIssue],
    quality_columns: list[str],
) -> None:
    for col in quality_columns:
        if col not in df.columns:
            continue
        counts = df[col].value_counts(dropna=False)
        ok_count = counts.get("OK", 0) + counts.get("PASS", 0) + counts.get("1", 0)
        ng_count = counts.get("NG", 0) + counts.get("FAIL", 0) + counts.get("0", 0)
        total = ok_count + ng_count
        if total == 0:
            continue
        if min(ok_count, ng_count) / total < UNBALANCED_OKNG_RATIO_THRESHOLD:
            issues.append(
                QualityIssue(
                    check=QualityCheck.UNBALANCED_OKNG,
                    column=str(col),
                    severity=QualityStatus.WARNING,
                    message=(
                        f"Column '{col}' has unbalanced OK/NG ratio "
                        f"(OK={ok_count}, NG={ng_count})."
                    ),
                    detail={"ok_count": ok_count, "ng_count": ng_count},
                )
            )


def _check_batch_imbalance(
    df: pd.DataFrame,
    issues: list[QualityIssue],
    batch_columns: list[str],
) -> None:
    for col in batch_columns:
        if col not in df.columns:
            continue
        counts = df[col].value_counts(dropna=False)
        if counts.empty:
            continue
        smallest = int(counts.min())
        largest = int(counts.max())
        ratio = smallest / max(largest, 1)
        if ratio < 0.1:
            issues.append(
                QualityIssue(
                    check=QualityCheck.BATCH_IMBALANCE,
                    column=str(col),
                    severity=QualityStatus.INFO,
                    message=(
                        f"Column '{col}' has a batch imbalance "
                        f"(smallest={smallest}, largest={largest})."
                    ),
                    detail={"smallest_batch": smallest, "largest_batch": largest},
                )
            )


def run_quality_checks(
    df: pd.DataFrame,
    categorical_columns: list[str] | None = None,
    quality_columns: list[str] | None = None,
    datetime_columns: list[str] | None = None,
    batch_columns: list[str] | None = None,
) -> QualityReport:
    """Run the Phase 1 quality checks.

    Args:
        df: The dataframe being assessed.
        categorical_columns: column names to treat as categorical.
        quality_columns: column names holding OK/NG style outcome labels.
        datetime_columns: column names holding timestamps.
        batch_columns: column names holding batch identifiers.

    Returns:
        A QualityReport.
    """
    categorical_columns = categorical_columns or []
    quality_columns = quality_columns or []
    datetime_columns = datetime_columns or []
    batch_columns = batch_columns or []

    issues: list[QualityIssue] = []
    _check_missing(df, issues)
    _check_duplicates(df, issues)
    _check_constant(df, issues)
    _check_outliers(df, issues, categorical_columns)
    _check_time_order(df, issues, datetime_columns)
    _check_unbalanced_okng(df, issues, quality_columns)
    _check_batch_imbalance(df, issues, batch_columns)

    for issue in issues:
        if issue.severity == QualityStatus.CRITICAL:
            issue.message = f"[CRITICAL] {issue.message}"

    return QualityReport(
        row_count=int(df.shape[0]),
        column_count=int(df.shape[1]),
        issues=issues,
    )


__all__ = [
    "QualityStatus",
    "QualityCheck",
    "QualityIssue",
    "QualityReport",
    "run_quality_checks",
]