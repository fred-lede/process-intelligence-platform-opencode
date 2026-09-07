"""Sanitize assistant context before it is sent to a cloud provider."""
from __future__ import annotations

import hashlib
import json
import math
import re
from numbers import Real
from typing import Any, Literal

from process_intelligence_engine.ai.contracts import CloudTransferPreview


_IDENTIFIER_KEY_PATTERNS = (
    "name",
    "email",
    "phone",
    "ip",
    "path",
    "customer",
    "supplier",
    "part",
    "station",
    "line",
    "machine",
    "operator",
    "account",
    "serial",
    "lot",
)
_MASK_RULES = frozenset({"mask", "masked", "redact", "remove"})


def sanitize_context(
    context: dict,
    rules: dict[str, str],
    numeric_policy: Literal["raw", "bucketed", "standardized"] = "raw",
) -> CloudTransferPreview:
    """Return a cloud-safe preview without mutating the original context."""
    if numeric_policy not in {"raw", "bucketed", "standardized"}:
        raise ValueError("Unsupported numeric policy")

    masked_fields: list[str] = []

    def sanitize(value: Any, key: str | None = None, path: str = "") -> Any:
        if key is not None and _should_mask(key, path, rules):
            masked_fields.append(path)
            return "MASKED"
        if isinstance(value, dict):
            return {
                item_key: sanitize(
                    item_value,
                    item_key,
                    f"{path}.{item_key}" if path else item_key,
                )
                for item_key, item_value in value.items()
            }
        if isinstance(value, list):
            return [sanitize(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
        if isinstance(value, tuple):
            return tuple(sanitize(item, path=f"{path}[{index}]") for index, item in enumerate(value))
        if isinstance(value, Real) and not isinstance(value, bool):
            return _sanitize_number(value, key, path, rules, numeric_policy)
        return value

    payload = sanitize(context)
    payload_hash = hashlib.sha256(
        json.dumps(payload, default=str, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return CloudTransferPreview(
        provider="cloud",
        payload=payload,
        masked_fields=masked_fields,
        numeric_policy=numeric_policy,
        payload_hash=payload_hash,
    )


def _should_mask(key: str, path: str, rules: dict[str, str]) -> bool:
    rule = rules.get(path, rules.get(key, "")).lower()
    return rule in _MASK_RULES or any(pattern in key.lower() for pattern in _IDENTIFIER_KEY_PATTERNS)


def _sanitize_number(
    value: Real,
    key: str | None,
    path: str,
    rules: dict[str, str],
    numeric_policy: str,
) -> Real | str:
    if numeric_policy == "raw":
        return value
    if numeric_policy == "bucketed":
        lower = math.floor(value / 10) * 10
        return f"{lower:g}-{lower + 10:g}"

    mean, standard_deviation = _standardization_parameters(key, path, rules)
    if mean is None or standard_deviation is None:
        raise ValueError(
            "Standardized numeric policy requires an explicit nonzero mean and standard deviation"
        )
    return (value - mean) / standard_deviation


def _standardization_parameters(
    key: str | None, path: str, rules: dict[str, str]
) -> tuple[float | None, float | None]:
    names = (path, key) if key else (path,)
    for name in names:
        if not name:
            continue
        match = re.fullmatch(
            r"mean\s*=\s*([^,]+),\s*std\s*=\s*([^,]+)", rules.get(name, "")
        )
        if match:
            mean, standard_deviation = _nonzero_numbers(*match.groups())
            if mean is not None and standard_deviation is not None:
                return mean, standard_deviation

        mean, standard_deviation = _nonzero_numbers(
            rules.get(f"{name}.mean", ""), rules.get(f"{name}.std", "")
        )
        if mean is not None and standard_deviation is not None:
            return mean, standard_deviation
    return None, None


def _nonzero_numbers(mean_value: str, standard_deviation_value: str) -> tuple[float | None, float | None]:
    try:
        mean = float(mean_value)
        standard_deviation = float(standard_deviation_value)
    except (TypeError, ValueError):
        return None, None
    if mean == 0 or standard_deviation == 0:
        return None, None
    return mean, standard_deviation
