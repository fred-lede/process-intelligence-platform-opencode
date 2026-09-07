"""Structured contracts for the controlled AI assistant."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class AssistantEvidence:
    evidence_id: str
    status: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AssistantActionDraft:
    draft_id: str
    method: str
    params: dict[str, Any]
    impact: str
    expected_result: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AssistantRequest:
    message: str
    project_id: str
    page: str
    context: dict[str, Any] = field(default_factory=dict)
    provider: str = "ollama"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AssistantResponse:
    success: bool
    explanation: str
    evidence: list[AssistantEvidence] = field(default_factory=list)
    evidence_status: str = "unverified"
    recommendations: list[str] = field(default_factory=list)
    action_draft: AssistantActionDraft | None = None
    limitations: list[str] = field(default_factory=list)
    error_code: str | None = None
    provider: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CloudTransferPreview:
    provider: str
    payload: dict[str, Any]
    masked_fields: list[str] = field(default_factory=list)
    numeric_policy: str = "raw"
    payload_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
