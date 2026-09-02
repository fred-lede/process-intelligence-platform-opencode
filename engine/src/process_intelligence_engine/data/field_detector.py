"""Automatic field role and data type detection.

Uses a deterministic, explainable rule engine: column names are normalized
and scored against known patterns, combined with value-level evidence
(numeric fraction, cardinality, datetime parsing, OK/NG labels).

Rules are ordered so more specific roles (quality_label, timestamp,
identifier) outrank generic ones (input, category, metadata).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class FieldRole(str, Enum):
    IDENTIFIER = "identifier"
    INPUT = "input"
    OUTPUT = "output"
    QUALITY_LABEL = "quality_label"
    CATEGORY = "category"
    TIMESTAMP = "timestamp"
    METADATA = "metadata"
    SENSITIVE = "sensitive"
    EXCLUDED = "excluded"


@dataclass
class DetectedField:
    name: str
    role: FieldRole
    data_type: str
    confidence: float
    reason: list[str] = field(default_factory=list)


# --- Name-based patterns (matched case-insensitively after normalization) ---

IDENTIFIER_PATTERNS = [
    r"\b(barcode|serial.?no|serial_number|s\\?n|part_id|board_id|panel_id|panel|lot|wip.?id|assy.?no|sequence?)\b",
    r"\b(料號|序號|批號|條碼|流水號|工單|板號)\b",
]

TIMESTAMP_PATTERNS = [
    r"\b(date.?time|time|date|timestamp|datetime|時間|日期|時間戳)\b",
]

QUALITY_PATTERNS = [
    r"\b(ok.?flag|pass.?fail|test.?result|ng|result|判定|結果|良否|pass)\b",
    r"\b(ok|ng)\s*(flag|code)?$",
]

METADATA_PATTERNS = [
    r"\b(operator|technician|employee|user|工程師|操作員|人員)\b",
    r"\b(note|remark|comment|remark|備註|說明|注)\b",
]

MACHINE_PATTERNS = [
    r"\b(machine|equipment|裝置|設備|機台|station|工位|線別|line)\b",
]

SENSITIVE_PATTERNS = [
    r"\b(imei|iccid|phone|email|identity|身份證|電話|信箱|serial|序號|barcode|條碼)\b",
]

INPUT_NAME_HINTS = [
    r"\b(temp|temperature|pressure|speed|velocity|flow|current|voltage|power|force|torque|angle|position|thickness|溫度|壓力|速度|流量|電流|電壓|力量|扭矩|孔徑)\b",
]


def _normalize(name: str) -> str:
    return re.sub(r"\s+", " ", name.lower().strip().replace("_", " ").replace("-", " "))


def _match_any(name: str, patterns: list[str]) -> bool:
    return any(re.search(p, name, re.IGNORECASE) for p in patterns)


def _parse_value(v: str) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_datetime(v: str) -> datetime | None:
    if not isinstance(v, str):
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(v.strip(), fmt)
        except (ValueError, AttributeError):
            continue
    return None


def _column_statistics(values: list) -> dict:
    """Compute value-level statistics for a column."""
    non_null = [v for v in values if v is not None and str(v).strip() != ""]
    str_values = [str(v).strip() for v in non_null if v is not None]
    numeric_count = sum(1 for v in str_values if _parse_value(v) is not None)
    datetime_count = sum(1 for v in str_values if _parse_datetime(v) is not None)
    upper_values = {v.upper() for v in str_values}

    return {
        "non_null": len(non_null),
        "total": len(values),
        "unique": len(set(str_values)),
        "numeric_fraction": numeric_count / max(len(str_values), 1),
        "datetime_fraction": datetime_count / max(len(str_values), 1),
        "upper_set": upper_values,
    }


def detect_fields(columns: list[dict]) -> list[DetectedField]:
    """Detect role and type for each column.

    Args:
        columns: list of {"name": str, "values": list} — values are the
            column's cell values (raw strings/numbers).

    Returns:
        A DetectedField per input column, in order.
    """
    results: list[DetectedField] = []

    for col in columns:
        name = str(col["name"])
        values = col.get("values", [])
        stats = _column_statistics(values)
        normalized = _normalize(name)
        reasons: list[str] = []

        # Value-level evidence
        numeric = stats["numeric_fraction"] >= 0.9
        datetimeish = stats["datetime_fraction"] >= 0.9
        unique_fraction = stats["unique"] / max(stats["non_null"], 1)

        # --- Role decision (priority order) ---

        # 1. Quality label: OK/NG/1-0 binary outcome columns
        upper = stats["upper_set"]
        if upper.issubset({"OK", "NG", "PASS", "FAIL", "1", "0", "TRUE", "FALSE"}) and len(upper) <= 2 and stats["non_null"] > 0:
            results.append(
                DetectedField(
                    name=name,
                    role=FieldRole.QUALITY_LABEL,
                    data_type="binary",
                    confidence=0.9,
                    reason=["column values match a binary OK/NG outcome set"],
                )
            )
            continue

        # 2. Timestamp by name + parseable values
        if datetimeish and _match_any(normalized, TIMESTAMP_PATTERNS):
            results.append(
                DetectedField(
                    name=name,
                    role=FieldRole.TIMESTAMP,
                    data_type="datetime",
                    confidence=0.9,
                    reason=["name suggests timestamp and values parse as datetimes"],
                )
            )
            continue

        # 3. Identifier: high cardinality + name pattern
        if unique_fraction >= 0.9 and _match_any(normalized, IDENTIFIER_PATTERNS):
            results.append(
                DetectedField(
                    name=name,
                    role=FieldRole.IDENTIFIER,
                    data_type="text",
                    confidence=0.85,
                    reason=["high-cardinality column whose name matches an identifier pattern"],
                )
            )
            continue

        if unique_fraction >= 0.95 and stats["non_null"] > 10 and not numeric and not datetimeish:
            results.append(
                DetectedField(
                    name=name,
                    role=FieldRole.IDENTIFIER,
                    data_type="text",
                    confidence=0.7,
                    reason=["near-unique text values consistent with an identifier/sequence key"],
                )
            )
            continue

        # 4. Machine / station category
        if _match_any(normalized, MACHINE_PATTERNS):
            results.append(
                DetectedField(
                    name=name,
                    role=FieldRole.CATEGORY,
                    data_type="categorical",
                    confidence=0.75,
                    reason=["name matches a machine/equipment/station pattern"],
                )
            )
            continue

        # 5. Operator / free text => metadata
        if _match_any(normalized, METADATA_PATTERNS):
            results.append(
                DetectedField(
                    name=name,
                    role=FieldRole.METADATA,
                    data_type="text",
                    confidence=0.7,
                    reason=["name matches operator/notes metadata pattern"],
                )
            )
            continue

        # 6. Numeric columns => input (or candidate output; Phase 1 defaults to input)
        if numeric:
            results.append(
                DetectedField(
                    name=name,
                    role=FieldRole.INPUT,
                    data_type="continuous",
                    confidence=0.7,
                    reason=["column is numeric; no output/spec signal found, defaulting to input"],
                )
            )
            continue

        # 7. Low-cardinality categorical => category
        if unique_fraction <= 0.5 and stats["non_null"] > 0:
            results.append(
                DetectedField(
                    name=name,
                    role=FieldRole.CATEGORY,
                    data_type="categorical",
                    confidence=0.6,
                    reason=["low-cardinality categorical values"],
                )
            )
            continue

        # 8. Fallback: generic metadata, low confidence
        results.append(
            DetectedField(
                name=name,
                role=FieldRole.METADATA,
                data_type="text",
                confidence=0.2,
                reason=["no strong signal; defaulted to metadata"],
            )
        )

    return results


__all__ = ["DetectedField", "FieldRole", "detect_fields"]