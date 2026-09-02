"""Test auth and audit IPC handlers."""

import pytest

from process_intelligence_engine.main import handle_request, AUTH_MANAGER


def test_auth_login_success():
    result = handle_request("auth/login", {"username": "admin", "password": "any"})
    assert result["success"] is True
    assert result["username"] == "admin"
    assert result["role"] == "admin"


def test_auth_login_invalid_credentials():
    result = handle_request("auth/login", {"username": "nobody", "password": "x"})
    assert result["success"] is False
    assert "error" in result


def test_auth_current_user_after_login():
    handle_request("auth/login", {"username": "admin", "password": "x"})
    result = handle_request("auth/current", {})
    assert result["username"] == "admin"
    assert result["role"] == "admin"


def test_auth_logout_clears_session():
    handle_request("auth/login", {"username": "admin", "password": "x"})
    handle_request("auth/logout", {})
    result = handle_request("auth/current", {})
    assert result["username"] is None
    assert result["role"] is None


def test_auth_register_and_list_users():
    handle_request("auth/register", {"username": "newuser", "role": "viewer"})
    result = handle_request("users/list", {})
    usernames = {u["username"] for u in result["users"]}
    assert "newuser" in usernames


def test_auth_register_invalid_role_raises():
    with pytest.raises(ValueError, match="Invalid role"):
        handle_request("auth/register", {"username": "bad", "role": "bogus"})


def test_audit_log_returns_entries():
    handle_request("auth/login", {"username": "admin", "password": "x"})
    result = handle_request("audit/log", {"limit": 10})
    assert isinstance(result["log"], list)
    assert all("id" in entry and "timestamp" in entry for entry in result["log"])
