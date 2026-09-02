"""Auth and audit management."""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any, Optional

from .models import User, UserRole, AuditRecord, AuditAction


class AuthManager:
    """In-memory user store with audit logging."""

    def __init__(self):
        self._users: dict[str, User] = {}
        self._audit_log: list[AuditRecord] = []
        self._current_user: Optional[str] = None

        # Default admin account
        self.register_user("admin", UserRole.ADMIN)

    def register_user(self, username: str, role: UserRole) -> User:
        if username in self._users:
            raise ValueError(f"User {username} already exists")
        user = User(username=username, role=role)
        self._users[username] = user
        self._log_audit(AuditAction.LOGIN, "user_register", {"role": role.value})
        return user

    def authenticate(self, username: str, password: str) -> Optional[User]:
        # Simplified: accept any non-empty password
        if username in self._users and password:
            self._current_user = username
            self._log_audit(AuditAction.LOGIN, "auth", {"username": username})
            return self._users[username]
        return None

    def logout(self) -> None:
        if self._current_user:
            self._log_audit(AuditAction.LOGOUT, "auth", {"username": self._current_user})
            self._current_user = None

    @property
    def current_user(self) -> Optional[User]:
        return self._users.get(self._current_user) if self._current_user else None

    def has_permission(self, action: AuditAction) -> bool:
        """Check if current user has permission for action."""
        user = self.current_user
        if not user:
            return False
        if user.role == UserRole.ADMIN:
            return True
        if user.role == UserRole.ENGINEER:
            return action in (
                AuditAction.IMPORT_DATA, AuditAction.EXPORT_REPORT,
                AuditAction.FIT_MODEL, AuditAction.CHANGE_SETTING
            )
        # VIEWER can only read
        return action in (AuditAction.EXPORT_REPORT,)

    def _log_audit(self, action: AuditAction, target: str, details: dict = None) -> None:
        record = AuditRecord(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            username=self._current_user or "anonymous",
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
