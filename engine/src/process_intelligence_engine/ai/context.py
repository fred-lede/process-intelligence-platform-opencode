"""Build the minimal, project-scoped evidence context for the assistant."""
from __future__ import annotations

import json

from process_intelligence_engine.versioning.chain import VersionChain


MAX_LOCAL_SUMMARY_BYTES = 32 * 1024
APPROVED_SUMMARY_KEYS = frozenset(
    {
        "selected_dataset_id",
        "selected_model_id",
        "selected_simulation_id",
        "selected_report_id",
        "selected_experiment_id",
        "selected_gate_id",
        "selected_entity_ids",
        "dataset_summary",
        "model_summary",
        "gate_summary",
        "report_summary",
        "evidence_ids",
        "evidence_status",
    }
)
_PROHIBITED_SUMMARY_KEYS = frozenset({"raw_rows", "dataframe"})


def _ensure_summary_is_bounded(page_summary: dict) -> None:
    serialized = json.dumps(page_summary, default=str).encode("utf-8")
    if len(serialized) > MAX_LOCAL_SUMMARY_BYTES:
        raise ValueError("Assistant context exceeds the local summary limit")

    def contains_prohibited_value(value: object) -> bool:
        if isinstance(value, dict):
            return any(
                str(key).lower() in _PROHIBITED_SUMMARY_KEYS
                or contains_prohibited_value(item)
                for key, item in value.items()
            )
        if isinstance(value, (list, tuple)):
            return any(contains_prohibited_value(item) for item in value)
        return False

    if contains_prohibited_value(page_summary):
        raise ValueError("Assistant context exceeds the local summary limit")


def build_assistant_context(
    project_id: str,
    page: str,
    page_summary: dict,
    chain: VersionChain,
) -> dict:
    """Return only current-project evidence and explicitly approved page fields."""
    _ensure_summary_is_bounded(page_summary)
    evidence = [
        {
            "entity_id": item["entity_id"],
            "entity_type": item["entity_type"],
            "project_id": item["project_id"],
            "version": item["version"],
            "evidence_status": item["evidence_status"],
        }
        for item in chain.get_chain_summary()
        if item["project_id"] == project_id
    ]
    statuses = {item["evidence_status"] for item in evidence}
    evidence_status = statuses.pop() if len(statuses) == 1 else "unverified"
    return {
        "project_id": project_id,
        "page": page,
        "page_summary": {
            key: value for key, value in page_summary.items() if key in APPROVED_SUMMARY_KEYS
        },
        "evidence": evidence,
        "evidence_status": evidence_status,
    }
