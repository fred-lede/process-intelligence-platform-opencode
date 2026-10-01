"""Method-level authorisation policy for the engine IPC surface.

The engine exposes one dispatch entry point (``main.handle_request``) with 126
methods. Roles were previously recorded but never consulted, so every method —
including user management, settings mutation and cloud upload — was reachable
by anyone who could speak the protocol.

Classification rule (keep this rule when adding a method)
--------------------------------------------------------
* ``PUBLIC``   — callable before any session exists.
* ``VIEWER``   — neither persists engine state nor calls an external service.
                 Read-only queries and pure computation belong here.
* ``ENGINEER`` — persists state (datasets, models, reports, projects, chain
                 links, gates, experiments) or performs network egress
                 (AI providers, provider connectivity tests).
* ``REVIEWER`` — approval decisions and the time-series risk-use gates.
* ``ADMIN``    — user/audit management, settings mutation, gate reset, cloud
                 upload, and deletion of governed artefacts.

``test_auth_policy.py`` asserts that every method dispatched by
``handle_request`` appears in exactly one set, so a newly added method cannot
silently inherit a permissive default.
"""

from __future__ import annotations

from .models import UserRole

# Rank used to compare roles. A method's required role is a *minimum*.
ROLE_RANK: dict[UserRole, int] = {
    UserRole.VIEWER: 0,
    UserRole.ENGINEER: 1,
    UserRole.REVIEWER: 2,
    UserRole.ADMIN: 3,
}

PUBLIC_METHODS: frozenset[str] = frozenset({
    "engine/ping",
    "engine/health",
    "auth/login",
    "auth/current",
})

# No persistence and no external calls: safe for a read-only role.
VIEWER_METHODS: frozenset[str] = frozenset({
    "auth/logout",
    "data/datasets",
    "data/detect_fields",
    "data/quality",
    "data/readiness",
    "data/distribution",
    "data/series",
    "data/grr",
    "analysis/detect_anomalies",
    "analysis/package",
    "modeling/list",
    "modeling/doe/generate",
    "modeling/doe/contour",
    "modeling/interactions/compute",
    "modeling/shap/explain",
    "modeling/time_series/explain",
    "modeling/extrapolation/check",
    "modeling/validation/analyze",
    "modeling/validation/full",
    "modeling/stats",
    "modeling/profiler/recommend",
    "modeling/sensitivity",
    "modeling/governance/check",
    "modeling/governance/recommend",
    "modeling/governance/doe_ai_compare",
    "spec/suggest",
    "report/list",
    "report/export",
    "ai/models",
    "ai/health",
    "settings/get",
    # Read-only hardware/driver diagnostic: persists nothing and makes no network egress
    # (nvidia-smi is a local subprocess), so VIEWER by the classification rule above.
    "system/device_probe",
    "experiment/list",
    "experiment/get",
    "experiment/suggest_next",
    "experiment/impact",
    "approval/status",
    "approval/records",
    "spc/analyze",
    "spc/multi_dataset_analyze",
    "spc/batch_analyze",
    "spc/capability",
    "monte_carlo/run",
    "prediction/predict",
    "prediction/model_info",
    "prediction/scenario/list",
    "copula/joint",
    "features/time_series",
    "features/time_series/model",
    "features/time_series/predict",
    "features/time_series/windows",
    "features/time_series/validation",
    "features/time_series/validation_gate",
    "features/time_series/experiment_validation",
    "features/time_series/retrain_compare",
    "features/consecutive_exceedance",
    "project/manifest",
    "project/settings",
    "project/dirs",
    "project/source-dirs",
    "project/scan",
    "project/datasets",
    "project/process-groups",
    "project/process-group-templates",
    "project/process-nodes",
    "project/flow-graph",
    "versioning/chain/summary",
    "versioning/chain/trace",
    "gates/status",
    "gates/summary",
    "gates/history",
})

# Persist state or reach the network.
ENGINEER_METHODS: frozenset[str] = frozenset({
    "data/import",
    "analysis/anomaly/register",
    "modeling/fit",
    "modeling/governance/fit_with_check",
    "modeling/transition",
    "report/generate",
    "ai/chat",
    "assistant/respond",
    "assistant/cloud_preview",
    "assistant/cloud_consent",
    "assistant/draft/execute",
    "settings/test_connection",
    "experiment/record",
    "experiment/record_with_verdict",
    "validation/experiment/create",
    "approval/submit",
    "prediction/scenario/save",
    "prediction/scenario/delete",
    "features/time_series/fit",
    "features/time_series/hybrid",
    "features/time_series/load",
    "features/time_series/sequence_simulation",
    "project/create",
    "project/open",
    "project/save_session",
    "project/save_ui_state",
    "project/dataset/register",
    "project/dataset/update",
    "project/process-group/create",
    "project/process-group/update",
    "project/process-group/delete",
    "project/process-node/create",
    "project/process-node/update",
    "project/process-node/delete",
    "project/flow-validate",
    "versioning/chain/link",
    "gates/confirm",
})

# Approval decisions and risk-use gates.
REVIEWER_METHODS: frozenset[str] = frozenset({
    "approval/approve",
    "approval/reject",
    "features/time_series/retrain_review",
    "features/time_series/risk_use_gate",
    "features/time_series/risk_use_approve",
})

# User/audit management, settings mutation, egress, governed-artefact deletion.
ADMIN_METHODS: frozenset[str] = frozenset({
    "auth/register",
    "users/list",
    "audit/log",
    "settings/update",
    "gates/reset",
    "cloud/preview",
    "cloud/upload",
    "cloud/records",
    "modeling/delete",
    "report/delete",
})

_MINIMUM_ROLE: dict[str, UserRole] = {}
for _methods, _role in (
    (VIEWER_METHODS, UserRole.VIEWER),
    (ENGINEER_METHODS, UserRole.ENGINEER),
    (REVIEWER_METHODS, UserRole.REVIEWER),
    (ADMIN_METHODS, UserRole.ADMIN),
):
    for _method in _methods:
        if _method in _MINIMUM_ROLE:
            raise RuntimeError(f"method classified twice: {_method}")
        _MINIMUM_ROLE[_method] = _role


def is_public(method: str) -> bool:
    """True when the method may be called before any session exists."""
    return method in PUBLIC_METHODS


def required_role(method: str) -> UserRole | None:
    """Minimum role needed to call ``method``.

    Returns ``None`` for public methods. Raises ``KeyError`` for an
    unclassified method: failing closed is deliberate, because a permissive
    default is exactly the hole this module exists to close.
    """
    if is_public(method):
        return None
    return _MINIMUM_ROLE[method]


def role_satisfies(role: UserRole, minimum: UserRole) -> bool:
    """True when ``role`` ranks at least as high as ``minimum``."""
    return ROLE_RANK[role] >= ROLE_RANK[minimum]


def classified_methods() -> frozenset[str]:
    """All methods with an explicit classification (including public ones)."""
    return frozenset(PUBLIC_METHODS) | frozenset(_MINIMUM_ROLE)
