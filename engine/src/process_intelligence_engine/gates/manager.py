"""Analysis phase gate manager.

Controls the not_started -> pending_confirmation -> confirmed state machine
per module. Each confirmation is bound to an entity_id and entity_version,
scoped by project_id for multi-project isolation. State persists to JSONL.

Each gate state change is recorded as an audit event (gate_id, event_type,
operation_id) so the full history of confirm/reset/version-change events
can be reconstructed.
"""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VALID_TRANSITIONS = {
    "not_started": {"pending_confirmation"},
    "pending_confirmation": {"confirmed", "not_started"},
    "confirmed": {"pending_confirmation"},
}


@dataclass
class GateEvent:
    """Audit event for each gate state transition."""
    event_id: str
    gate_id: str
    module: str
    project_id: str
    event_type: str  # "confirm" / "reset" / "version_changed"
    operation_id: str
    old_status: str
    new_status: str
    entity_id: str
    entity_version: int
    confirmed_by: str
    reset_reason: str
    comment: str
    timestamp: str


@dataclass
class GateRecord:
    module: str
    project_id: str
    entity_id: str
    entity_version: int
    status: str
    confirmed_by: str
    confirmed_at: str
    reset_reason: str = ""
    comment: str = ""
    gate_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class GateManager:
    """Manages per-module analysis phase gates with project scoping."""

    ALL_MODULES = [
        "data_import", "process_define", "modeling",
        "spc", "monte_carlo", "prediction", "validation",
    ]

    def __init__(self, project_root: str = "", project_id: str = "default") -> None:
        self._project_root = Path(project_root) if project_root else Path()
        self._project_id = project_id
        self._gates: dict[str, GateRecord] = {}
        self._events: list[GateEvent] = []
        self._lock = threading.Lock()
        for mod in self.ALL_MODULES:
            self._gates[mod] = GateRecord(
                module=mod,
                project_id=project_id,
                entity_id="",
                entity_version=0,
                status="not_started",
                confirmed_by="",
                confirmed_at="",
                gate_id=f"gt-{uuid.uuid4().hex[:8]}",
            )
        self._load()

    def _gate_key(self, module: str) -> str:
        return f"{self._project_id}:{module}"

    def _gates_path(self) -> Path:
        return self._project_root / "registry" / "gates.jsonl"

    def _events_path(self) -> Path:
        return self._project_root / "registry" / "gate_events.jsonl"

    def _load(self) -> None:
        path = self._gates_path()
        if path.exists():
            try:
                for line in path.read_text().splitlines():
                    if not line.strip():
                        continue
                    d = json.loads(line)
                    if d.get("project_id") != self._project_id:
                        continue
                    rec = GateRecord(**d)
                    self._gates[rec.module] = rec
            except (json.JSONDecodeError, OSError, KeyError):
                pass
        # Load event history (last event per module wins for current state)
        ev_path = self._events_path()
        if ev_path.exists():
            try:
                for line in ev_path.read_text().splitlines():
                    if not line.strip():
                        continue
                    d = json.loads(line)
                    if d.get("project_id") != self._project_id:
                        continue
                    self._events.append(GateEvent(**d))
            except (json.JSONDecodeError, OSError, KeyError):
                pass

    def _save(self) -> None:
        if not self._project_root:
            return
        path = self._gates_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            for rec in self._gates.values():
                if rec.project_id == self._project_id:
                    f.write(json.dumps(asdict(rec), default=str) + "\n")

    def _append_event(self, event: GateEvent) -> None:
        """Persist a gate event to the audit log."""
        if not self._project_root:
            return
        path = self._events_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(asdict(event), default=str) + "\n")

    def get_status(self, module: str) -> str:
        with self._lock:
            return self._gates.get(module, GateRecord(
                module=module,
                project_id=self._project_id,
                entity_id="", entity_version=0,
                status="not_started", confirmed_by="", confirmed_at="",
            )).status

    def confirm(
        self,
        module: str,
        entity_id: str,
        entity_version: int,
        confirmed_by: str,
        comment: str = "",
        operation_id: str = "",
    ) -> dict:
        if not entity_id:
            raise ValueError("entity_id is required")
        op_id = operation_id or f"op-{uuid.uuid4().hex[:8]}"
        with self._lock:
            gate = self._gates[module]
            old_status = gate.status
            if (gate.entity_id, gate.entity_version) != (entity_id, entity_version):
                gate.status = "pending_confirmation"
                gate.entity_id = entity_id
                gate.entity_version = entity_version
                # Record version change event
                evt = GateEvent(
                    event_id=f"ev-{uuid.uuid4().hex[:8]}",
                    gate_id=gate.gate_id,
                    module=module,
                    project_id=self._project_id,
                    event_type="version_changed",
                    operation_id=op_id,
                    old_status=old_status,
                    new_status="pending_confirmation",
                    entity_id=entity_id,
                    entity_version=entity_version,
                    confirmed_by="",
                    reset_reason="",
                    comment="",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                self._events.append(evt)
                self._append_event(evt)
            gate.status = "confirmed"
            gate.confirmed_by = confirmed_by
            gate.confirmed_at = datetime.now(timezone.utc).isoformat()
            gate.comment = comment
            evt2 = GateEvent(
                event_id=f"ev-{uuid.uuid4().hex[:8]}",
                gate_id=gate.gate_id,
                module=module,
                project_id=self._project_id,
                event_type="confirm",
                operation_id=op_id,
                old_status=old_status,
                new_status="confirmed",
                entity_id=entity_id,
                entity_version=entity_version,
                confirmed_by=confirmed_by,
                reset_reason="",
                comment=comment,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            self._events.append(evt2)
            self._append_event(evt2)
            self._save()
            return {"new_status": "confirmed"}

    def reset(self, module: str, reason: str = "", operation_id: str = "") -> dict:
        op_id = operation_id or f"op-{uuid.uuid4().hex[:8]}"
        with self._lock:
            gate = self._gates[module]
            old_status = gate.status
            gate.status = "pending_confirmation"
            gate.reset_reason = reason
            evt = GateEvent(
                event_id=f"ev-{uuid.uuid4().hex[:8]}",
                gate_id=gate.gate_id,
                module=module,
                project_id=self._project_id,
                event_type="reset",
                operation_id=op_id,
                old_status=old_status,
                new_status="pending_confirmation",
                entity_id=gate.entity_id,
                entity_version=gate.entity_version,
                confirmed_by=gate.confirmed_by,
                reset_reason=reason,
                comment="",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            self._events.append(evt)
            self._append_event(evt)
            self._save()
            return {"new_status": "pending_confirmation"}

    def get_summary(self) -> dict[str, str]:
        with self._lock:
            return {mod: self._gates[mod].status for mod in self.ALL_MODULES}

    def get_details(self, module: str) -> dict[str, Any]:
        with self._lock:
            gate = self._gates.get(module)
            if gate is None:
                return {"module": module, "status": "not_started", "project_id": self._project_id}
            return {
                "module": gate.module,
                "project_id": gate.project_id,
                "gate_id": gate.gate_id,
                "status": gate.status,
                "entity_id": gate.entity_id,
                "entity_version": gate.entity_version,
                "confirmed_by": gate.confirmed_by,
                "confirmed_at": gate.confirmed_at,
                "reset_reason": gate.reset_reason,
                "comment": gate.comment,
            }

    def get_history(self, module: str | None = None) -> list[dict]:
        """Return full event history, optionally filtered by module."""
        with self._lock:
            if module:
                return [asdict(e) for e in self._events if e.module == module]
            return [asdict(e) for e in self._events]

    def are_all_confirmed(self, modules: list[str] | None = None) -> bool:
        with self._lock:
            mods = modules or self.ALL_MODULES
            return all(self._gates[m].status == "confirmed" for m in mods if m in self._gates)

    def is_confirmed(self, module: str, entity_id: str, version: int) -> bool:
        """Confirmations of comparison models coexist until a reset."""
        with self._lock:
            for event in reversed(self._events):
                if event.module != module:
                    continue
                if event.event_type == "reset":
                    return False
                if event.event_type == "confirm" and event.entity_id == entity_id:
                    return event.entity_version == version
            return False
