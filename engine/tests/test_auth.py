"""Tests for the auth module.

These encode the security model, so they deliberately assert the *negative*
cases: a wrong password must fail, a credential-less account must be
rejected, and a restricted role must be refused on a privileged method.
"""
import pytest
from datetime import datetime

from process_intelligence_engine.auth.models import UserRole, AuditAction
from process_intelligence_engine.auth.manager import AuthManager, LOCAL_PRINCIPAL_USERNAME


def test_default_admin_exists():
    mgr = AuthManager()
    users = mgr.get_users()
    admin = [u for u in users if u["username"] == "admin"]
    assert len(admin) == 1
    assert admin[0]["role"] == "admin"


def test_local_principal_is_the_effective_user_without_login():
    mgr = AuthManager()
    assert mgr.is_local_session
    assert mgr.session_user is None
    user = mgr.current_user
    assert user is not None
    assert user.username == LOCAL_PRINCIPAL_USERNAME
    assert user.role == UserRole.ADMIN


def test_local_role_is_configurable():
    mgr = AuthManager(local_role=UserRole.VIEWER)
    principal = mgr.current_user
    assert principal is not None
    assert principal.role == UserRole.VIEWER
    # A viewer local principal must not be able to administer users.
    with pytest.raises(PermissionError):
        mgr.require("users/list")


def test_register_user_requires_a_password():
    mgr = AuthManager()
    with pytest.raises(ValueError, match="password is required"):
        mgr.register_user("engineer1", UserRole.ENGINEER, "")


def test_register_user():
    mgr = AuthManager()
    user = mgr.register_user("engineer1", UserRole.ENGINEER, "s3cret")
    assert user.username == "engineer1"
    assert user.role == UserRole.ENGINEER


def test_duplicate_user_raises():
    mgr = AuthManager()
    mgr.register_user("testuser", UserRole.ENGINEER, "s3cret")
    with pytest.raises(ValueError, match="already exists"):
        mgr.register_user("testuser", UserRole.VIEWER, "other")


def test_authenticate_with_correct_password():
    mgr = AuthManager()
    mgr.register_user("testuser", UserRole.ENGINEER, "correct-horse")
    user = mgr.authenticate("testuser", "correct-horse")
    assert user is not None
    assert user.username == "testuser"
    assert not mgr.is_local_session


def test_authenticate_rejects_wrong_password():
    # Regression: any non-empty password used to be accepted for any user.
    mgr = AuthManager()
    mgr.register_user("testuser", UserRole.ENGINEER, "correct-horse")
    assert mgr.authenticate("testuser", "wrong") is None
    assert mgr.authenticate("testuser", "") is None
    # A failed attempt must not establish a session.
    assert mgr.is_local_session


def test_authenticate_invalid():
    mgr = AuthManager()
    user = mgr.authenticate("nonexistent", "password")
    assert user is None


def test_passwords_are_not_stored_in_plaintext():
    mgr = AuthManager()
    mgr.register_user("testuser", UserRole.ENGINEER, "correct-horse")
    stored = str(mgr._passwords)  # noqa: SLF001 - asserting on storage on purpose
    assert "correct-horse" not in stored


def test_permission_admin_all_access():
    mgr = AuthManager()
    mgr.authenticate("admin", "admin")
    assert mgr.has_permission(AuditAction.APPROVE_MODEL)
    assert mgr.has_permission(AuditAction.FIT_MODEL)


def test_permission_engineer():
    mgr = AuthManager()
    mgr.register_user("eng", UserRole.ENGINEER, "pw")
    mgr.authenticate("eng", "pw")
    assert mgr.has_permission(AuditAction.FIT_MODEL)
    assert not mgr.has_permission(AuditAction.APPROVE_MODEL)


def test_permission_viewer():
    mgr = AuthManager()
    mgr.register_user("viewer", UserRole.VIEWER, "pw")
    mgr.authenticate("viewer", "pw")
    assert not mgr.has_permission(AuditAction.FIT_MODEL)
    assert mgr.has_permission(AuditAction.EXPORT_REPORT)


def test_register_reviewer_role():
    mgr = AuthManager()
    user = mgr.register_user("reviewer1", UserRole.REVIEWER, "pw")
    assert user.username == "reviewer1"
    assert user.role == UserRole.REVIEWER


def test_audit_log_captured():
    mgr = AuthManager()
    mgr.authenticate("admin", "admin")
    mgr._log_audit(AuditAction.FIT_MODEL, "model_123", {"type": "doe_linear"})
    log = mgr.get_audit_log()
    assert len(log) >= 2  # login + fit_model
    assert log[-1]["action"] == "fit_model"
    assert log[-1]["target"] == "model_123"


def test_logout_returns_to_the_local_principal():
    mgr = AuthManager()
    mgr.register_user("viewer", UserRole.VIEWER, "pw")
    mgr.authenticate("viewer", "pw")
    session = mgr.session_user
    assert session is not None and session.username == "viewer"
    mgr.logout()
    assert mgr.session_user is None
    # The machine owner's implicit role resumes; the session is never anonymous.
    principal = mgr.current_user
    assert principal is not None
    assert principal.username == LOCAL_PRINCIPAL_USERNAME
    assert principal.role == UserRole.ADMIN


# --------------------------------------------------------------------- require

def test_require_allows_public_methods_without_a_session():
    mgr = AuthManager()
    for method in ("engine/ping", "engine/health", "auth/login", "auth/current"):
        mgr.require(method)  # must not raise


def test_require_enforces_reader_versus_writer():
    mgr = AuthManager()
    mgr.register_user("viewer", UserRole.VIEWER, "pw")
    mgr.authenticate("viewer", "pw")
    mgr.require("spc/analyze")            # pure computation is allowed
    with pytest.raises(PermissionError):
        mgr.require("data/import")        # persisting state is not
    with pytest.raises(PermissionError):
        mgr.require("users/list")
    with pytest.raises(PermissionError):
        mgr.require("cloud/upload")


def test_require_separates_reviewer_from_engineer():
    mgr = AuthManager()
    mgr.register_user("eng", UserRole.ENGINEER, "pw")
    mgr.register_user("rev", UserRole.REVIEWER, "pw")

    mgr.authenticate("eng", "pw")
    mgr.require("modeling/fit")
    with pytest.raises(PermissionError):
        mgr.require("approval/approve")

    mgr.authenticate("rev", "pw")
    mgr.require("approval/approve")


def test_require_rejects_unclassified_methods():
    # Failing closed: a method with no policy entry must not be callable.
    mgr = AuthManager()
    with pytest.raises(KeyError):
        mgr.require("some/method-that-does-not-exist")
