"""Auth and audit management.

Session model
-------------
The engine runs as a child process of the desktop app, so the machine owner is
trusted by construction. When nobody has logged in, the effective user is an
implicit *local principal* whose role comes from
``PROCESS_INTELLIGENCE_LOCAL_ROLE`` (default: admin). That keeps the app usable
without a login screen while still making the role model real: logging in as a
restricted account genuinely reduces what the session may do, and every
non-public method is checked against ``auth.policy`` before it runs.
"""
from __future__ import annotations
import hashlib
import hmac
import os
import secrets
import uuid
from datetime import datetime
from typing import Any, Optional

from . import policy
from .models import User, UserRole, AuditRecord, AuditAction

#: Username reported for the implicit machine-owner session.
LOCAL_PRINCIPAL_USERNAME = "local"

#: Default password for the seeded ``admin`` account. Documented on purpose:
#: the local principal is already an admin, so this grants no extra privilege —
#: it exists so ``auth/login`` has a real credential to verify against.
DEFAULT_ADMIN_PASSWORD = "admin"

_PBKDF2_ITERATIONS = 200_000
_SALT_BYTES = 16


def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    """Return ``(salt_hex, digest_hex)`` for ``password``."""
    salt = salt or secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return salt.hex(), digest.hex()


class AuthManager:
    """User store, session state and audit logging."""

    def __init__(self, local_role: UserRole | None = None):
        self._users: dict[str, User] = {}
        self._passwords: dict[str, tuple[str, str]] = {}
        self._audit_log: list[AuditRecord] = []
        self._current_user: Optional[str] = None
        self._local_role = local_role or _configured_local_role()

        self.register_user("admin", UserRole.ADMIN, DEFAULT_ADMIN_PASSWORD)

    # ------------------------------------------------------------------ users

    def register_user(self, username: str, role: UserRole, password: str) -> User:
        """Create a user. A password is mandatory: credential-less accounts
        were previously accepted by ``authenticate()`` for any non-empty
        string, which made every password valid for every user."""
        if not username or not username.strip():
            raise ValueError("username is required")
        if not password:
            raise ValueError("password is required")
        if username in self._users:
            raise ValueError(f"User {username} already exists")
        user = User(username=username, role=role)
        self._users[username] = user
        self._passwords[username] = _hash_password(password)
        self._log_audit(AuditAction.LOGIN, "user_register", {"role": role.value})
        return user

    def set_password(self, username: str, password: str) -> None:
        if username not in self._users:
            raise KeyError(f"Unknown user: {username}")
        if not password:
            raise ValueError("password is required")
        self._passwords[username] = _hash_password(password)
        self._log_audit(AuditAction.CHANGE_SETTING, "password_changed", {"username": username})

    def authenticate(self, username: str, password: str) -> Optional[User]:
        """Verify credentials against the stored hash."""
        stored = self._passwords.get(username)
        user = self._users.get(username)
        if stored is None or user is None or not password or not user.is_active:
            self._log_audit(AuditAction.LOGIN, "auth_failed", {"username": username})
            return None
        salt_hex, digest_hex = stored
        _, candidate = _hash_password(password, bytes.fromhex(salt_hex))
        if not hmac.compare_digest(candidate, digest_hex):
            self._log_audit(AuditAction.LOGIN, "auth_failed", {"username": username})
            return None
        self._current_user = username
        self._log_audit(AuditAction.LOGIN, "auth", {"username": username})
        return user

    def logout(self) -> None:
        if self._current_user:
            self._log_audit(AuditAction.LOGOUT, "auth", {"username": self._current_user})
            self._current_user = None

    # ---------------------------------------------------------------- session

    @property
    def session_user(self) -> Optional[User]:
        """The explicitly logged-in user, or ``None`` for the local session."""
        return self._users.get(self._current_user) if self._current_user else None

    @property
    def current_user(self) -> Optional[User]:
        """Effective user: the logged-in account, else the local principal."""
        return self.session_user or self._local_principal()

    @property
    def is_local_session(self) -> bool:
        return self.session_user is None

    def _local_principal(self) -> User:
        principal = self._users.get(LOCAL_PRINCIPAL_USERNAME)
        if principal is None:
            principal = User(username=LOCAL_PRINCIPAL_USERNAME, role=self._local_role)
            self._users[LOCAL_PRINCIPAL_USERNAME] = principal
        return principal

    # --------------------------------------------------------- authorization

    def require(self, method: str) -> None:
        """Raise ``PermissionError`` unless the session may call ``method``."""
        minimum = policy.required_role(method)
        if minimum is None:
            return
        user = self.current_user
        if user is None:
            raise PermissionError(f"Not authenticated for {method!r}")
        if not user.is_active:
            raise PermissionError(f"User {user.username!r} is inactive")
        if not policy.role_satisfies(user.role, minimum):
            raise PermissionError(
                f"Role {user.role.value!r} may not call {method!r}; "
                f"{minimum.value!r} or higher is required"
            )

    def has_permission(self, action: AuditAction) -> bool:
        """Action-level check kept for callers that reason in audit actions."""
        user = self.current_user
        if not user:
            return False
        if user.role == UserRole.ADMIN:
            return True
        if user.role in (UserRole.ENGINEER, UserRole.REVIEWER):
            allowed = (
                AuditAction.IMPORT_DATA, AuditAction.EXPORT_REPORT,
                AuditAction.FIT_MODEL, AuditAction.CHANGE_SETTING,
            )
            if user.role == UserRole.REVIEWER:
                allowed += (AuditAction.APPROVE_MODEL, AuditAction.REJECT_MODEL)
            return action in allowed
        # VIEWER can only read
        return action in (AuditAction.EXPORT_REPORT,)

    # ------------------------------------------------------------------ audit

    def _log_audit(self, action: AuditAction, target: str, details: dict = None) -> None:
        record = AuditRecord(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            username=self._current_user or LOCAL_PRINCIPAL_USERNAME,
            action=action,
            target=target,
            details=details or {},
        )
        self._audit_log.append(record)

    def get_audit_log(self, limit: int = 100) -> list[dict]:
        return [
            {
                "id": r.id,
                "timestamp": r.timestamp.isoformat(),
                "username": r.username,
                "action": r.action.value,
                "target": r.target,
                "details": r.details,
            }
            for r in self._audit_log[-limit:]
        ]

    def get_users(self) -> list[dict]:
        return [
            {
                "username": u.username,
                "role": u.role.value,
                "created_at": u.created_at.isoformat(),
                "is_active": u.is_active,
            }
            for u in self._users.values()
        ]


def _configured_local_role() -> UserRole:
    raw = os.environ.get("PROCESS_INTELLIGENCE_LOCAL_ROLE", UserRole.ADMIN.value)
    try:
        return UserRole(raw.strip().lower())
    except ValueError:
        raise ValueError(
            f"PROCESS_INTELLIGENCE_LOCAL_ROLE must be one of "
            f"{[r.value for r in UserRole]}, got {raw!r}"
        )
