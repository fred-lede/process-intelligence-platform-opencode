"""Analysis phase gate manager.

Controls the not_started -> pending_confirmation -> confirmed state machine
per module. Each confirmation is bound to an entity_id and entity_version.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


VALID_TRANSITIONS = {
    "not_started": {"pending_confirmation"},
    "pending_confirmation": {"confirmed", "not_started"},
    "confirmed": {"pending_confirmation"},
}


@dataclass
class GateRecord:
    module: str
    entity_id: str
    entity_version: int
    status: str
    confirmed_by: str
    confirmed_at: str
    reset_reason: str = ""
    comment: str = ""


class GateManager:
    """Manages per-module analysis phase gates."""

    ALL_MODULES = [
        "data_import", "process_define", "modeling",
        "spc", "monte_carlo", "prediction", "validation",
    ]

    def __init__(self) -> None:
        self._gates: dict[str, GateRecord] = {}
        self._lock = threading.Lock()
        for mod in self.ALL_MODULES:
            self._gates[mod] = GateRecord(
                module=mod,
                entity_id="",
                entity_version=0,
                status="not_started",
                confirmed_by="",
                confirmed_at="",
            )

    def get_status(self, module: str) -> str:
        with self._lock:
            return self._gates.get(module, GateRecord(
                module=module, entity_id="", entity_version=0,
                status="not_started", confirmed_by="", confirmed_at="",
            )).status

    def confirm(
        self,
        module: str,
        entity_id: str,
        entity_version: int,
        confirmed_by: str,
        comment: str = "",
    ) -> dict:
        if not entity_id:
            raise ValueError("entity_id is required")
        with self._lock:
            gate = self._gates[module]
            if gate.entity_version != entity_version:
                gate.status = "pending_confirmation"
                gate.entity_id = entity_id
                gate.entity_version = entity_version
            gate.status = "confirmed"
            gate.confirmed_by = confirmed_by
            gate.confirmed_at = datetime.now(timezone.utc).isoformat()
            gate.comment = comment
            return {"new_status": "confirmed"}

    def reset(self, module: str, reason: str = "") -> dict:
        with self._lock:
            gate = self._gates[module]
            gate.status = "pending_confirmation"
            gate.reset_reason = reason
            return {"new_status": "pending_confirmation"}

    def get_summary(self) -> dict[str, str]:
        with self._lock:
            return {mod: self._gates[mod].status for mod in self.ALL_MODULES}

    def get_details(self, module: str) -> dict[str, Any]:
        with self._lock:
            gate = self._gates.get(module)
            if gate is None:
                return {"module": module, "status": "not_started"}
            return {
                "module": gate.module,
                "status": gate.status,
                "entity_id": gate.entity_id,
                "entity_version": gate.entity_version,
                "confirmed_by": gate.confirmed_by,
                "confirmed_at": gate.confirmed_at,
                "reset_reason": gate.reset_reason,
                "comment": gate.comment,
            }

    def are_all_confirmed(self, modules: list[str] | None = None) -> bool:
        with self._lock:
            mods = modules or self.ALL_MODULES
            return all(self._gates[m].status == "confirmed" for m in mods if m in self._gates)
