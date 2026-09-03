"""Approval workflow for models and reports.

Supports the Reviewer role defined in spec section 20.
"""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from process_intelligence_engine.auth.models import UserRole

VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"pending_review"},
    "pending_review": {"approved", "rejected", "retired"},
    "approved": {"retired"},
    "rejected": {"draft", "retired"},
    "retired": set(),
}


@dataclass
class ApprovalRecord:
    """Tracks who approved/rejected a model or report."""

    record_id: str
    resource_type: str  # "model" | "report"
    resource_id: str
    action: str  # "submit_for_review" | "approve" | "reject" | "retire"
    reviewer: str
    reviewer_role: str
    comments: str
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "action": self.action,
            "reviewer": self.reviewer,
            "reviewer_role": self.reviewer_role,
            "comments": self.comments,
            "timestamp": self.timestamp,
        }


class ApprovalWorkflow:
    """In-memory approval workflow engine."""

    def __init__(self) -> None:
        self._records: dict[str, ApprovalRecord] = {}
        self._statuses: dict[str, str] = {}  # resource_key -> current status
        self._lock = threading.Lock()

    def submit_for_review(
        self,
        resource_type: str,
        resource_id: str,
        reviewer: str,
        reviewer_role: str,
        comments: str = "",
    ) -> dict:
        key = f"{resource_type}:{resource_id}"
        with self._lock:
            current = self._statuses.get(key, "draft")
            if current != "draft":
                raise ValueError(
                    f"Resource {key} is in status '{current}', not 'draft'. Cannot submit for review."
                )
            self._statuses[key] = "pending_review"
            rec = ApprovalRecord(
                record_id=str(uuid.uuid4()),
                resource_type=resource_type,
                resource_id=resource_id,
                action="submit_for_review",
                reviewer=reviewer,
                reviewer_role=reviewer_role,
                comments=comments,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            self._records[rec.record_id] = rec
            return {"record_id": rec.record_id, "new_status": "pending_review"}

    def approve(
        self,
        resource_type: str,
        resource_id: str,
        reviewer: str,
        reviewer_role: str,
        comments: str = "",
    ) -> dict:
        key = f"{resource_type}:{resource_id}"
        with self._lock:
            current = self._statuses.get(key)
            if current not in ("pending_review", None):
                raise ValueError(
                    f"Resource {key} is in status '{current}', cannot approve."
                )
            if reviewer_role not in ("reviewer", "admin"):
                raise ValueError("Only Reviewer or Admin can approve.")
            self._statuses[key] = "approved"
            rec = ApprovalRecord(
                record_id=str(uuid.uuid4()),
                resource_type=resource_type,
                resource_id=resource_id,
                action="approve",
                reviewer=reviewer,
                reviewer_role=reviewer_role,
                comments=comments,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            self._records[rec.record_id] = rec
            return {"record_id": rec.record_id, "new_status": "approved"}

    def reject(
        self,
        resource_type: str,
        resource_id: str,
        reviewer: str,
        reviewer_role: str,
        comments: str = "",
    ) -> dict:
        key = f"{resource_type}:{resource_id}"
        with self._lock:
            current = self._statuses.get(key)
            if current != "pending_review":
                raise ValueError(
                    f"Resource {key} is in status '{current}', cannot reject."
                )
            if reviewer_role not in ("reviewer", "admin"):
                raise ValueError("Only Reviewer or Admin can reject.")
            self._statuses[key] = "rejected"
            rec = ApprovalRecord(
                record_id=str(uuid.uuid4()),
                resource_type=resource_type,
                resource_id=resource_id,
                action="reject",
                reviewer=reviewer,
                reviewer_role=reviewer_role,
                comments=comments,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            self._records[rec.record_id] = rec
            return {"record_id": rec.record_id, "new_status": "rejected"}

    def get_status(self, resource_type: str, resource_id: str) -> str:
        key = f"{resource_type}:{resource_id}"
        with self._lock:
            return self._statuses.get(key, "draft")

    def list_records(
        self,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> list[dict]:
        with self._lock:
            result = []
            for rec in self._records.values():
                if resource_type and rec.resource_type != resource_type:
                    continue
                if resource_id and rec.resource_id != resource_id:
                    continue
                result.append(rec.to_dict())
            return result


APPROVAL_WORKFLOW = ApprovalWorkflow()
