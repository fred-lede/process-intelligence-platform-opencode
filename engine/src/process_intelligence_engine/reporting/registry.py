"""In-memory registry of generated reports (for the Approval tab).

Tracks every successful report/generate so the frontend can list
generated reports and submit them for review.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any


class ReportRegistry:
    """In-memory registry of generated report records."""

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def register(
        self,
        project_name: str,
        operator: str = "Unknown",
        output_format: str = "html",
    ) -> str:
        report_id = str(uuid.uuid4())
        rec = {
            "report_id": report_id,
            "project_name": project_name,
            "operator": operator,
            "format": output_format,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._records[report_id] = rec
        return report_id

    def list(self) -> list[dict]:
        with self._lock:
            return sorted(self._records.values(), key=lambda r: r["timestamp"], reverse=True)

    def _clear(self) -> None:
        """Test helper: wipe all records."""
        with self._lock:
            self._records.clear()


_REPORT_REGISTRY = ReportRegistry()
