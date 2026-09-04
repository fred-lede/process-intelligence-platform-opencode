"""Tests for auth module."""
import pytest
from datetime import datetime

from process_intelligence_engine.auth.models import UserRole, AuditAction
from process_intelligence_engine.auth.manager import AuthManager


def test_default_admin_exists():
    mgr = AuthManager()
    users = mgr.get_users()
    admin = [u for u in users if u["username"] == "admin"]
    assert len(admin) == 1
    assert admin[0]["role"] == "admin"


def test_register_user():
    mgr = AuthManager()
    user = mgr.register_user("engineer1", UserRole.ENGINEER)
    assert user.username == "engineer1"
    assert user.role == UserRole.ENGINEER


def test_duplicate_user_raises():
    mgr = AuthManager()
    mgr.register_user("testuser", UserRole.ENGINEER)
    with pytest.raises(ValueError, match="already exists"):
        mgr.register_user("testuser", UserRole.VIEWER)


def test_authenticate():
    mgr = AuthManager()
    mgr.register_user("testuser", UserRole.ENGINEER)
    user = mgr.authenticate("testuser", "password")
    assert user is not None
    assert user.username == "testuser"


def test_authenticate_invalid():
    mgr = AuthManager()
    user = mgr.authenticate("nonexistent", "password")
    assert user is None


def test_permission_admin_all_access():
    mgr = AuthManager()
    mgr.authenticate("admin", "pass")
    assert mgr.has_permission(AuditAction.APPROVE_MODEL)
    assert mgr.has_permission(AuditAction.FIT_MODEL)


def test_permission_engineer():
    mgr = AuthManager()
    mgr.register_user("eng", UserRole.ENGINEER)
    mgr.authenticate("eng", "pass")
    assert mgr.has_permission(AuditAction.FIT_MODEL)
    assert not mgr.has_permission(AuditAction.APPROVE_MODEL)


def test_permission_viewer():
    mgr = AuthManager()
    mgr.register_user("viewer", UserRole.VIEWER)
    mgr.authenticate("viewer", "pass")
    assert not mgr.has_permission(AuditAction.FIT_MODEL)
    assert mgr.has_permission(AuditAction.EXPORT_REPORT)


def test_register_reviewer_role():
    mgr = AuthManager()
    user = mgr.register_user("reviewer1", UserRole.REVIEWER)
    assert user.username == "reviewer1"
    assert user.role == UserRole.REVIEWER


def test_audit_log_captured():
    mgr = AuthManager()
    mgr.authenticate("admin", "pass")
    mgr._log_audit(AuditAction.FIT_MODEL, "model_123", {"type": "doe_linear"})
    log = mgr.get_audit_log()
    assert len(log) >= 2  # login + fit_model
    assert log[-1]["action"] == "fit_model"
    assert log[-1]["target"] == "model_123"


def test_logout_clears_current_user():
    mgr = AuthManager()
    mgr.authenticate("admin", "pass")
    assert mgr.current_user is not None
    mgr.logout()
    assert mgr.current_user is None
