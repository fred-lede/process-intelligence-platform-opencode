"""Analysis phase gate manager.

Controls the not_started -> pending_confirmation -> confirmed state machine
per module. Each confirmation is bound to an entity_id and entity_version,
scoped by project_id for multi-project isolation. State persists to JSONL.
"""
from __future__ import annotations

import json
import threading
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
            )
        self._load()

    def _gate_key(self, module: str) -> str:
        return f"{self._project_id}:{module}"

    def _gates_path(self) -> Path:
        return self._project_root / "registry" / "gates.jsonl"

    def _load(self) -> None:
        path = self._gates_path()
        if not path.exists():
            return
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

    def _save(self) -> None:
        if not self._project_root:
            return
        path = self._gates_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            for rec in self._gates.values():
                if rec.project_id == self._project_id:
                    f.write(json.dumps(asdict(rec), default=str) + "\n")

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
            self._save()
            return {"new_status": "confirmed"}

    def reset(self, module: str, reason: str = "") -> dict:
        with self._lock:
            gate = self._gates[module]
            gate.status = "pending_confirmation"
            gate.reset_reason = reason
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
