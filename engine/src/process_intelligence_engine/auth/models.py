"""Auth and audit data models."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class UserRole(str, Enum):
    ADMIN = "admin"
    ENGINEER = "engineer"
    VIEWER = "viewer"


class AuditAction(str, Enum):
    LOGIN = "login"
    LOGOUT = "logout"
    IMPORT_DATA = "import_data"
    EXPORT_REPORT = "export_report"
    FIT_MODEL = "fit_model"
    APPROVE_MODEL = "approve_model"
    REJECT_MODEL = "reject_model"
    CHANGE_SETTING = "change_setting"


@dataclass
class User:
    username: str
    role: UserRole
    created_at: datetime = field(default_factory=datetime.now)
    is_active: bool = True


@dataclass
class AuditRecord:
    id: str
    timestamp: datetime
    username: str
    action: AuditAction
    target: str  # what was acted upon
    details: dict[str, Any] = field(default_factory=dict)
    ip_address: str = ""
