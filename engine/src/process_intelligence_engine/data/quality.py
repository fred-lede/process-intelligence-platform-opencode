"""Data quality checks.

Implements the Phase 1 quality checks from the spec (§10.1), each issue
carries a status, severity, human-readable message and machine-checkable
detail fields. The report is deterministic for a given input.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import re

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


_UNIT_SUFFIX_RE = re.compile(r"([a-zA-Z°]+)$")
_INPUT_OUT_OF_RANGE_MAD_FACTOR = 8.0


def _is_numeric_str(s: object) -> bool:
    """Return whether a string value can be parsed as a number."""
    if not isinstance(s, str):
        return False
    try:
        float(s.strip().replace(",", ""))
        return True
    except ValueError:
        return False


def _extract_unit_suffix(s: object) -> str | None:
    """Extract a trailing alphabetic/degree unit suffix from a string value."""
    if not isinstance(s, str):
        return None
    m = _UNIT_SUFFIX_RE.search(s.strip())
    return m.group(1).lower() if m else None


def _has_spec(limit: object) -> bool:
    return limit is not None and not (isinstance(limit, float) and limit != limit)


def _is_string_like(series: pd.Series) -> bool:
    """Return whether a series holds string (object or 'str') values."""
    return bool(
        pd.api.types.is_object_dtype(series)
        or (
            hasattr(pd.api.types, "is_string_dtype")
            and pd.api.types.is_string_dtype(series)
        )
    )


def _check_invalid_format(df: pd.DataFrame, issues: list[QualityIssue]) -> None:
    """Flag string columns whose values have inconsistent parseability.

    Detects columns where the majority of values parse as numbers (or a
    consistent date) but a minority use an invalid format, e.g. '12.5' vs
    '12.5mm' or 'ab12'.
    """
    for col in df.columns:
        series = df[col].dropna()
        if series.empty or not _is_string_like(series):
            continue
        as_str = [str(v) for v in series]
        numeric = [v for v in as_str if _is_numeric_str(v)]
        non_numeric = [v for v in as_str if not _is_numeric_str(v)]
        # Only act when format is genuinely inconsistent: both kinds present
        # and the minority is non-trivial but not the whole column.
        if not numeric or not non_numeric:
            continue
        minority = min(numeric, non_numeric, key=len)
        if len(minority) / len(as_str) < 0.5:
            examples = minority[:3]
            issues.append(
                QualityIssue(
                    check=QualityCheck.INVALID_FORMAT,
                    column=str(col),
                    severity=QualityStatus.WARNING,
                    message=(
                        f"Column '{col}' mixes valid and invalid formats "
                        f"({len(non_numeric)} non-numeric value(s), e.g. "
                        f"{', '.join(repr(e) for e in examples)})."
                    ),
                    detail={
                        "numeric_count": len(numeric),
                        "non_numeric_count": len(non_numeric),
                        "examples": examples,
                    },
                )
            )


def _check_unit_mixing(df: pd.DataFrame, issues: list[QualityIssue]) -> None:
    """Flag string columns carrying more than one distinct unit suffix."""
    for col in df.columns:
        series = df[col].dropna()
        if series.empty or not _is_string_like(series):
            continue
        suffixes: set[str] = set()
        for v in series:
            suffix = _extract_unit_suffix(str(v))
            if suffix:
                suffixes.add(suffix)
        if len(suffixes) > 1:
            issues.append(
                QualityIssue(
                    check=QualityCheck.UNIT_MIXING,
                    column=str(col),
                    severity=QualityStatus.WARNING,
                    message=(
                        f"Column '{col}' mixes units: "
                        f"{', '.join(sorted(suffixes))}."
                    ),
                    detail={"units": sorted(suffixes)},
                )
            )


def _check_input_out_of_range(
    df: pd.DataFrame,
    issues: list[QualityIssue],
    input_columns: list[str],
    input_ranges: dict[str, tuple[float | None, float | None]] | None = None,
) -> None:
    """Flag input values outside an engineering-reasonable range.

    When `input_ranges` is provided (column -> (low, high); None = unbounded)
    it is used directly. Otherwise a generous statistical bound
    (median ± 8*MAD) approximates engineering plausibility.
    """
    input_ranges = input_ranges or {}
    for col in input_columns or df.columns:
        if col not in df.columns or not pd.api.types.is_numeric_dtype(df[col]):
            continue
        series = df[col].dropna().astype(float)
        if len(series) < 3:
            continue
        lo, hi = input_ranges.get(str(col), (None, None))
        if lo is None and hi is None:
            median = float(series.median())
            mad = float((series - median).abs().median() * 1.4826)
            if mad == 0:
                continue
            lo = median - _INPUT_OUT_OF_RANGE_MAD_FACTOR * mad
            hi = median + _INPUT_OUT_OF_RANGE_MAD_FACTOR * mad
        out = series[(series < (lo if lo is not None else series.min() - 1)) |
                     (series > (hi if hi is not None else series.max() + 1))]
        if out.empty:
            continue
        issues.append(
            QualityIssue(
                check=QualityCheck.INPUT_OUT_OF_RANGE,
                column=str(col),
                severity=QualityStatus.WARNING,
                message=(
                    f"Column '{col}' has {len(out)} value(s) outside the "
                    f"engineering range [{lo if lo is not None else '-inf'}, "
                    f"{hi if hi is not None else 'inf'}]."
                ),
                detail={
                    "out_of_range_count": int(len(out)),
                    "range_lower": lo,
                    "range_upper": hi,
                },
            )
        )


def _check_missing_spec(
    df: pd.DataFrame,
    issues: list[QualityIssue],
    output_columns: list[str],
    spec: dict[str, dict] | None = None,
) -> None:
    """Flag output columns that lack a lower and upper specification limit."""
    spec = spec or {}
    for col in output_columns:
        if col not in df.columns:
            continue
        limits = spec.get(str(col), {})
        lsl = limits.get("lsl")
        usl = limits.get("usl")
        if _has_spec(lsl) or _has_spec(usl):
            continue
        issues.append(
            QualityIssue(
                check=QualityCheck.MISSING_SPEC,
                column=str(col),
                severity=QualityStatus.WARNING,
                message=f"Column '{col}' is an output but has no spec limits set.",
                detail={"lsl": lsl, "usl": usl},
            )
        )


def run_quality_checks(
    df: pd.DataFrame,
    categorical_columns: list[str] | None = None,
    quality_columns: list[str] | None = None,
    datetime_columns: list[str] | None = None,
    batch_columns: list[str] | None = None,
    input_columns: list[str] | None = None,
    output_columns: list[str] | None = None,
    input_ranges: dict[str, tuple[float | None, float | None]] | None = None,
    spec: dict[str, dict] | None = None,
) -> QualityReport:
    """Run the Phase 1 quality checks.

    Args:
        df: The dataframe being assessed.
        categorical_columns: column names to treat as categorical.
        quality_columns: column names holding OK/NG style outcome labels.
        datetime_columns: column names holding timestamps.
        batch_columns: column names holding batch identifiers.
        input_columns: column names treated as process inputs. If empty,
            all numeric columns are scanned by the out-of-range heuristic.
        output_columns: column names treated as outputs, used for spec checks.
        input_ranges: optional (low, high) engineering ranges per input column;
            None means unbounded. Omitted columns fall back to the statistical
            heuristic.
        spec: optional per-output-column spec dicts, e.g.
            {"thickness": {"lsl": 1.5, "usl": 1.8, "target": 1.65}}.

    Returns:
        A QualityReport.
    """
    categorical_columns = categorical_columns or []
    quality_columns = quality_columns or []
    datetime_columns = datetime_columns or []
    batch_columns = batch_columns or []
    input_columns = input_columns or []
    output_columns = output_columns or []

    issues: list[QualityIssue] = []
    _check_missing(df, issues)
    _check_duplicates(df, issues)
    _check_constant(df, issues)
    _check_outliers(df, issues, categorical_columns)
    _check_time_order(df, issues, datetime_columns)
    _check_unbalanced_okng(df, issues, quality_columns)
    _check_batch_imbalance(df, issues, batch_columns)
    _check_invalid_format(df, issues)
    _check_unit_mixing(df, issues)
    _check_input_out_of_range(df, issues, input_columns, input_ranges)
    _check_missing_spec(df, issues, output_columns, spec)

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