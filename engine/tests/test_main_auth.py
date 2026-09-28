"""Test auth and audit IPC handlers, including authorisation enforcement."""

import pytest

from process_intelligence_engine.auth.manager import DEFAULT_ADMIN_PASSWORD
from process_intelligence_engine.main import handle_request, AUTH_MANAGER


@pytest.fixture(autouse=True)
def _clean_session():
    """The engine exposes one global session; keep tests from leaking into
    each other by returning to the local principal around every test."""
    AUTH_MANAGER.logout()
    yield
    AUTH_MANAGER.logout()


def _login(username, password):
    return handle_request("auth/login", {"username": username, "password": password})


def test_auth_login_success():
    result = _login("admin", DEFAULT_ADMIN_PASSWORD)
    assert result["success"] is True
    assert result["username"] == "admin"
    assert result["role"] == "admin"


def test_auth_login_wrong_password_fails():
    # Regression: any non-empty password used to authenticate any user.
    result = _login("admin", "definitely-not-the-password")
    assert result["success"] is False
    assert "error" in result


def test_auth_login_empty_password_fails():
    result = _login("admin", "")
    assert result["success"] is False


def test_auth_login_invalid_credentials():
    result = _login("nobody", "x")
    assert result["success"] is False
    assert "error" in result


def test_auth_current_user_reports_local_session_before_login():
    result = handle_request("auth/current", {})
    assert result["username"] == "local"
    assert result["role"] == "admin"
    assert result["is_local_session"] is True


def test_auth_current_user_after_login():
    _login("admin", DEFAULT_ADMIN_PASSWORD)
    result = handle_request("auth/current", {})
    assert result["username"] == "admin"
    assert result["role"] == "admin"
    assert result["is_local_session"] is False


def test_auth_logout_returns_to_local_principal():
    _login("admin", DEFAULT_ADMIN_PASSWORD)
    handle_request("auth/logout", {})
    result = handle_request("auth/current", {})
    assert result["username"] == "local"
    assert result["is_local_session"] is True


def test_auth_register_and_list_users():
    handle_request("auth/register", {
        "username": "newuser", "role": "viewer", "password": "pw-newuser",
    })
    result = handle_request("users/list", {})
    usernames = {u["username"] for u in result["users"]}
    assert "newuser" in usernames


def test_auth_register_requires_a_password():
    with pytest.raises(ValueError, match="password is required"):
        handle_request("auth/register", {"username": "nopass", "role": "viewer"})


def test_auth_register_invalid_role_raises():
    with pytest.raises(ValueError, match="Invalid role"):
        handle_request("auth/register", {
            "username": "bad", "role": "bogus", "password": "pw",
        })


def test_auth_register_admin_needs_explicit_confirmation():
    with pytest.raises(ValueError, match="confirm_admin"):
        handle_request("auth/register", {
            "username": "second-admin", "role": "admin", "password": "pw",
        })
    result = handle_request("auth/register", {
        "username": "second-admin", "role": "admin", "password": "pw",
        "confirm_admin": True,
    })
    assert result["role"] == "admin"


def test_audit_log_returns_entries():
    _login("admin", DEFAULT_ADMIN_PASSWORD)
    result = handle_request("audit/log", {"limit": 10})
    assert isinstance(result["log"], list)
    assert all("id" in entry and "timestamp" in entry for entry in result["log"])


# ------------------------------------------------------------- enforcement

def test_viewer_is_refused_privileged_methods():
    handle_request("auth/register", {
        "username": "ro-viewer", "role": "viewer", "password": "pw",
    })
    _login("ro-viewer", "pw")

    # Read-only computation still works for a viewer.
    handle_request("modeling/list", {})

    for method, params in (
        ("data/import", {"file_path": "/nope.csv"}),
        ("users/list", {}),
        ("audit/log", {}),
        ("settings/update", {}),
        ("cloud/upload", {}),
    ):
        with pytest.raises(PermissionError):
            handle_request(method, params)


def test_engineer_cannot_approve():
    handle_request("auth/register", {
        "username": "an-engineer", "role": "engineer", "password": "pw",
    })
    _login("an-engineer", "pw")
    with pytest.raises(PermissionError):
        handle_request("approval/approve", {"model_id": "x", "approver": "an-engineer"})
    with pytest.raises(PermissionError):
        handle_request("modeling/delete", {"model_id": "x"})


def test_reviewer_can_reach_approval_policy():
    handle_request("auth/register", {
        "username": "a-reviewer", "role": "reviewer", "password": "pw",
    })
    _login("a-reviewer", "pw")
    # The approval handler itself may reject the arguments; what matters is
    # that authorisation passed rather than raising PermissionError.
    with pytest.raises(Exception) as excinfo:
        handle_request("approval/approve", {"model_id": "does-not-exist"})
    assert not isinstance(excinfo.value, PermissionError)


def test_local_session_keeps_the_app_usable_without_login():
    # The default local principal is an admin, so the desktop app works with
    # no login screen while enforcement is still active underneath.
    assert AUTH_MANAGER.is_local_session
    handle_request("users/list", {})
    handle_request("audit/log", {})
