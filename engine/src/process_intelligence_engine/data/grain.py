"""Optional hierarchical grain and filtering helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SUPPORTED_GRAIN_FIELDS = frozenset({
    "product_id", "lot_id", "machine_id", "station_id", "process_step", "subgroup_id",
})


@dataclass(frozen=True)
class DataFilter:
    field: str
    value: Any

    def validate(self, columns: set[str]) -> None:
        if self.field not in SUPPORTED_GRAIN_FIELDS:
            raise ValueError(f"Unsupported grain field: {self.field}")
        if self.field not in columns:
            raise ValueError(f"Grain field not found: {self.field}")


def apply_grain_filter(frame, filters: list[DataFilter] | None = None):
    """Return a filtered copy; never mutate the registered source frame."""
    result = frame.copy()
    for item in filters or []:
        item.validate(set(result.columns))
        result = result[result[item.field].astype(str) == str(item.value)]
    return result.copy()
