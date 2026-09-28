"""The authorisation policy must stay in lockstep with the dispatcher.

Without this, a newly added method would fail closed (good) but silently — the
first sign would be a user-facing error. These tests make the gap visible at
test time instead.
"""
import re
from pathlib import Path

from process_intelligence_engine import main
from process_intelligence_engine.auth import policy

_METHOD_CALL = re.compile(r'if method == "([^"]+)"')
_METHOD_GROUP = re.compile(r"if method in \(([^)]*)\)")
_QUOTED = re.compile(r'"([^"]+)"')


def _dispatched_methods() -> set[str]:
    source = Path(main.__file__).read_text(encoding="utf-8")
    methods = set(_METHOD_CALL.findall(source))
    for group in _METHOD_GROUP.findall(source):
        methods |= set(_QUOTED.findall(group))
    return methods


def _classification_groups() -> dict[str, set[str]]:
    return {
        "public": set(policy.PUBLIC_METHODS),
        "viewer": set(policy.VIEWER_METHODS),
        "engineer": set(policy.ENGINEER_METHODS),
        "reviewer": set(policy.REVIEWER_METHODS),
        "admin": set(policy.ADMIN_METHODS),
    }


def test_dispatcher_surface_is_discoverable():
    # Guards the extraction itself: if handle_request is refactored into a
    # table, this test must be updated rather than silently matching nothing.
    assert len(_dispatched_methods()) > 100


def test_every_dispatched_method_is_classified():
    missing = sorted(_dispatched_methods() - policy.classified_methods())
    assert missing == [], f"methods with no policy entry: {missing}"


def test_policy_has_no_stale_entries():
    stale = sorted(policy.classified_methods() - _dispatched_methods())
    assert stale == [], f"policy entries with no dispatch site: {stale}"


def test_classification_groups_are_disjoint():
    seen: dict[str, str] = {}
    for name, methods in _classification_groups().items():
        for method in methods:
            assert method not in seen, f"{method} is in both {seen[method]} and {name}"
            seen[method] = name


def test_public_methods_need_no_role():
    for method in policy.PUBLIC_METHODS:
        assert policy.required_role(method) is None


def test_non_public_methods_require_at_least_viewer():
    for method in policy.classified_methods() - policy.PUBLIC_METHODS:
        assert policy.required_role(method) == policy._MINIMUM_ROLE[method]


def test_admin_tier_covers_the_sensitive_surface():
    # Named explicitly so that loosening one of these is a deliberate edit.
    for method in (
        "auth/register",
        "users/list",
        "audit/log",
        "settings/update",
        "gates/reset",
        "cloud/upload",
        "modeling/delete",
    ):
        assert policy._MINIMUM_ROLE[method].value == "admin", method


def test_reviewer_tier_covers_approvals():
    for method in ("approval/approve", "approval/reject"):
        assert policy._MINIMUM_ROLE[method].value == "reviewer", method
