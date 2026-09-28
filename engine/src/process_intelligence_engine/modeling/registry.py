"""Immutable model version registry + status machine (spec 12.5).

State flow: draft -> pending_validation -> validated -> approved; any state
may go to retired. Immutability: register() assigns a strictly monotonic,
never-reused version number so no model version is ever overwritten.

Reads are snapshots
-------------------
``get()`` / ``list`` accessors return a copy of the model's *metadata*
(inputs, metrics, coefficients, status, ...) so a caller cannot reach into the
stored record and set ``status = "approved"`` or rewrite coefficients, which
would bypass the state machine entirely. The fitted estimator itself is shared
on purpose: it is only ever used for ``.predict()``, and deep-copying a forest
on every access would be prohibitively expensive in the handlers that iterate
over every model.

Mutating a stored model goes through ``transition()`` (validated against the
state graph) or ``restore_status()`` (project replay only).
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import replace

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

# A model may only be removed outright while it carries no approval weight.
# Anything further along the chain is retired instead, so the record of what
# was once approved survives.
DELETABLE_STATUS = ("draft", "retired")


class InvalidStatusTransition(Exception):
    pass


class ModelRegistry:
    """In-memory, thread-safe registry of fitted models with immutable versions."""

    def __init__(self) -> None:
        self._models: dict[str, ModelFit] = {}
        self._lock = threading.Lock()
        self._version_counter = 0

    # ------------------------------------------------------------------ writes

    def register(self, fit: ModelFit) -> str:
        """Add a new model version.

        Note: this assigns model_id/version/status on ``fit`` in place, so the
        caller's object becomes the registered record. Callers rely on reading
        the assigned ``model_id`` afterwards.
        """
        with self._lock:
            self._version_counter += 1
            fit.model_id = str(uuid.uuid4())
            fit.version = self._version_counter
            fit.status = "draft"
            self._models[fit.model_id] = fit
            return fit.model_id

    def restore(self, fit: ModelFit) -> None:
        """Restore only after the session loader verifies deterministic replay."""
        with self._lock:
            if not fit.model_id or fit.model_id in self._models or fit.status not in VALID_STATUS:
                raise ValueError("Invalid restored model")
            self._models[fit.model_id] = fit
            self._version_counter = max(self._version_counter, fit.version)

    def transition(self, model_id: str, new_status: str) -> ModelFit:
        """Move a model along the state graph and return a snapshot of it."""
        with self._lock:
            if new_status not in VALID_STATUS:
                raise ValueError(f"Unknown status: {new_status}")
            stored = self._stored(model_id)
            if new_status not in TRANSITIONS.get(stored.status, set()):
                raise InvalidStatusTransition(
                    f"Cannot transition {stored.status} -> {new_status}"
                )
            stored.status = new_status
            return self._snapshot(stored)

    def restore_status(self, model_id: str, status: str) -> ModelFit:
        """Set a persisted status during project replay.

        The loader restores a status that was already recorded when the project
        was saved, and that status is not necessarily reachable by a single
        legal transition from "draft". This is the only sanctioned way to set a
        status outside the state graph; IPC handlers must use ``transition()``.
        """
        with self._lock:
            if status not in VALID_STATUS:
                raise ValueError(f"Unknown status: {status}")
            stored = self._stored(model_id)
            stored.status = status
            return self._snapshot(stored)

    def delete(self, model_id: str) -> None:
        """Remove a model. Refused once it carries approval weight."""
        with self._lock:
            stored = self._stored(model_id)
            if stored.status not in DELETABLE_STATUS:
                raise InvalidStatusTransition(
                    f"Cannot delete a model in status {stored.status!r}; "
                    f"only {', '.join(DELETABLE_STATUS)} models can be removed. "
                    f"Retire it instead so the approval history survives."
                )
            del self._models[model_id]

    # ------------------------------------------------------------------- reads

    def get(self, model_id: str) -> ModelFit:
        """Snapshot of the model; mutating it does not affect the registry."""
        with self._lock:
            return self._snapshot(self._stored(model_id))

    def _get_unlocked(self, model_id: str) -> ModelFit:
        """Snapshot accessor. Assumes the caller holds (or does not need) the lock."""
        return self._snapshot(self._stored(model_id))

    def list_ids(self) -> list[str]:
        with self._lock:
            return sorted(self._models.keys())

    # ---------------------------------------------------------------- internal

    def _stored(self, model_id: str) -> ModelFit:
        """The live record. Internal: callers here mutate it deliberately."""
        if model_id not in self._models:
            raise KeyError(f"Unknown model_id: {model_id}")
        return self._models[model_id]

    @staticmethod
    def _snapshot(fit: ModelFit) -> ModelFit:
        """Copy the metadata, share the estimator.

        Deep-copying ``fit.model`` would be correct but far too slow for the
        handlers that walk every registered model; the estimator is only ever
        read through ``.predict()``, so sharing it is safe.
        """
        return replace(
            fit,
            inputs=list(fit.inputs),
            metrics=dict(fit.metrics),
            coefficients=dict(fit.coefficients) if fit.coefficients is not None else None,
            selected_inputs=(
                list(fit.selected_inputs) if fit.selected_inputs is not None else None
            ),
        )
