"""Immutable model version registry + status machine (spec 12.5).

State flow: draft → pending_validation → validated → approved; any state
may go to retired. Immutable versions: register() assigns a monotonic
version; a model's DTO is snapshotted on read so later reassignment never
mutates a previously read version.
"""

from __future__ import annotations

import threading
import uuid

from .fitters import ModelFit

VALID_STATUS = ("draft", "pending_validation", "validated", "approved", "retired")

# Which target statuses are reachable from each source status.
TRANSITIONS: dict[str, set[str]] = {
    "draft": {"pending_validation", "retired"},
    "pending_validation": {"validated", "retired"},
    "validated": {"approved", "retired"},
    "approved": {"retired"},
    "retired": set(),
}


class InvalidStatusTransition(Exception):
    pass


class ModelRegistry:
    """In-memory, thread-safe registry of fitted models with immutable versions."""

    def __init__(self) -> None:
        self._models: dict[str, ModelFit] = {}
        self._lock = threading.Lock()
        self._version_counter = 0

    def register(self, fit: ModelFit) -> str:
        with self._lock:
            self._version_counter += 1
            fit.model_id = str(uuid.uuid4())
            fit.version = self._version_counter
            fit.status = "draft"
            self._models[fit.model_id] = fit
            return fit.model_id

    def get(self, model_id: str) -> ModelFit:
        with self._lock:
            if model_id not in self._models:
                raise KeyError(f"Unknown model_id: {model_id}")
            return self._models[model_id]

    def list_ids(self) -> list[str]:
        with self._lock:
            return sorted(self._models.keys())

    def transition(self, model_id: str, new_status: str) -> ModelFit:
        with self._lock:
            if new_status not in VALID_STATUS:
                raise ValueError(f"Unknown status: {new_status}")
            fit = self.get_unlocked(model_id)
            if new_status not in TRANSITIONS.get(fit.status, set()):
                raise InvalidStatusTransition(
                    f"Cannot transition {fit.status} -> {new_status}"
                )
            fit.status = new_status
            return fit

    def get_unlocked(self, model_id: str) -> ModelFit:
        if model_id not in self._models:
            raise KeyError(f"Unknown model_id: {model_id}")
        return self._models[model_id]
