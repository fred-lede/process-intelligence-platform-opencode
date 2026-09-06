"""Append-only version chain with JSONL persistence.

Tracks cross-entity relationships with content hashes and evidence status.
"""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class EntityRecord:
    entity_id: str
    entity_type: str
    project_id: str
    version: int
    metadata: dict
    parent_ids: list[str]
    created_at: str
    created_by: str
    content_hash: str
    parameters_hash: str | None
    schema_version: str
    tags: list[str]
    evidence_status: str


@dataclass
class LinkRecord:
    from_id: str
    to_id: str
    relation: str
    evidence_status: str
    created_by: str
    created_at: str
    revoked_at: str | None = None


@dataclass
class ClaimRecord:
    claim_id: str
    entity_id: str
    claim_type: str
    text: str
    source_entity_ids: list[str]
    origin_source: str
    evidence_status: str
    confidence: float | None
    valid_range: dict | None


class VersionChain:
    """Central version chain manager with JSONL persistence.

    Entities, links and claims are append-only event log records.
    _version_counters are keyed by (project_id, entity_type) for
    per-project isolation and persisted separately so app restarts
    preserve monotonic sequence numbers.

    Mutation operations (register_entity, add_link, add_claim) append
    to their respective JSONL files. save() writes a full snapshot
    (used at shutdown or on-demand). This hybrid approach supports:
    - append-only audit trail for normal operations
    - full-state rebuild via save()/load() for recovery
    """

    SCHEMA_VERSION = "1.0.0"
    PREFIX_MAP = {
        "dataset": "ds",
        "model": "md",
        "simulation": "sim",
        "report": "rep",
        "experiment": "exp",
        "anomaly": "ano",
        "claim": "cl",
        "gate": "gt",
    }

    def __init__(self, project_root: str, operator: str = "anonymous") -> None:
        self._project_root = Path(project_root)
        self._operator = operator
        self._entities: dict[str, EntityRecord] = {}
        self._links: list[LinkRecord] = []
        self._claims: dict[str, list[ClaimRecord]] = {}
        # Counter keyed by (project_id, entity_type) for per-project isolation
        self._version_counters: dict[tuple[str, str], int] = {}
        self._lock = threading.Lock()

    def _prefix(self, entity_type: str) -> str:
        return self.PREFIX_MAP.get(entity_type, "ent")

    def _compute_hash(self, data: dict) -> str:
        raw = json.dumps(data, sort_keys=True, default=str).encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    def _entities_path(self) -> Path:
        return self._project_root / "registry" / "version_chain.jsonl"

    def _links_path(self) -> Path:
        return self._project_root / "registry" / "links.jsonl"

    def _claims_path(self) -> Path:
        return self._project_root / "registry" / "claims.jsonl"

    def _counters_path(self) -> Path:
        return self._project_root / "registry" / "version_counters.json"

    def _persist_counters(self) -> None:
        path = self._counters_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Serialize tuple keys as "project_id:entity_type" strings
        serializable = {f"{k[0]}||{k[1]}": v for k, v in self._version_counters.items()}
        path.write_text(json.dumps(serializable))

    def _load_counters(self) -> None:
        path = self._counters_path()
        if path.exists():
            try:
                raw = json.loads(path.read_text())
                self._version_counters = {}
                for key, val in raw.items():
                    parts = key.split("||", 1)
                    if len(parts) == 2:
                        self._version_counters[(parts[0], parts[1])] = val
            except (json.JSONDecodeError, OSError):
                self._version_counters = {}

    def register_entity(
        self,
        entity_type: str,
        project_id: str,
        metadata: dict,
        created_by: str = "",
        parent_ids: list[str] | None = None,
        content_hash: str = "",
        parameters_hash: str | None = None,
    ) -> str:
        with self._lock:
            prefix = self._prefix(entity_type)
            counter_key = (project_id, entity_type)
            self._version_counters.setdefault(counter_key, 0)
            self._version_counters[counter_key] += 1
            ver = self._version_counters[counter_key]
            entity_id = f"{prefix}-{uuid.uuid4().hex[:8]}"
            record = EntityRecord(
                entity_id=entity_id,
                entity_type=entity_type,
                project_id=project_id,
                version=ver,
                metadata=metadata,
                parent_ids=parent_ids or [],
                created_at=datetime.now(timezone.utc).isoformat(),
                created_by=created_by or self._operator,
                content_hash=content_hash or self._compute_hash(metadata),
                parameters_hash=parameters_hash,
                schema_version=self.SCHEMA_VERSION,
                tags=[],
                evidence_status="unverified",
            )
            self._entities[entity_id] = record
            path = self._entities_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a") as f:
                f.write(json.dumps(asdict(record), default=str) + "\n")
            self._persist_counters()
            return entity_id

    def get_entity(self, entity_id: str) -> EntityRecord:
        if entity_id not in self._entities:
            raise KeyError(f"Unknown entity_id: {entity_id}")
        return self._entities[entity_id]

    def add_link(
        self,
        from_id: str,
        to_id: str,
        relation: str,
        evidence_status: str = "unverified",
        created_by: str = "",
    ) -> None:
        if from_id not in self._entities:
            raise KeyError(f"Unknown from_id: {from_id}")
        if to_id not in self._entities:
            raise KeyError(f"Unknown to_id: {to_id}")
        link = LinkRecord(
            from_id=from_id,
            to_id=to_id,
            relation=relation,
            evidence_status=evidence_status,
            created_by=created_by or self._operator,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._links.append(link)
        path = self._links_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(asdict(link), default=str) + "\n")

    def add_claim(
        self,
        entity_id: str,
        claim_type: str,
        text: str,
        source_entity_ids: list[str],
        origin_source: str,
        evidence_status: str = "unverified",
        confidence: float | None = None,
    ) -> str:
        claim_id = f"cl-{uuid.uuid4().hex[:8]}"
        claim = ClaimRecord(
            claim_id=claim_id,
            entity_id=entity_id,
            claim_type=claim_type,
            text=text,
            source_entity_ids=source_entity_ids,
            origin_source=origin_source,
            evidence_status=evidence_status,
            confidence=confidence,
            valid_range=None,
        )
        self._claims.setdefault(entity_id, []).append(claim)
        path = self._claims_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            record = asdict(claim)
            record["entity_id"] = entity_id
            f.write(json.dumps(record, default=str) + "\n")
        return claim_id

    def get_claims(self, entity_id: str) -> list[dict]:
        return [asdict(c) for c in self._claims.get(entity_id, [])]

    def get_trace(self, entity_id: str) -> dict:
        if entity_id not in self._entities:
            raise KeyError(f"Unknown entity_id: {entity_id}")
        entity = self._entities[entity_id]
        incoming = [
            asdict(l) for l in self._links
            if l.to_id == entity_id and l.revoked_at is None
        ]
        outgoing = [
            asdict(l) for l in self._links
            if l.from_id == entity_id and l.revoked_at is None
        ]
        claims = self.get_claims(entity_id)
        return {
            "entity_id": entity_id,
            "entity_type": entity.entity_type,
            "project_id": entity.project_id,
            "version": entity.version,
            "metadata": entity.metadata,
            "parent_ids": entity.parent_ids,
            "evidence_status": entity.evidence_status,
            "incoming_links": incoming,
            "outgoing_links": outgoing,
            "claims": claims,
            "created_at": entity.created_at,
            "created_by": entity.created_by,
        }

    def get_chain_summary(self) -> list[dict]:
        result = []
        for eid, entity in self._entities.items():
            result.append({
                "entity_id": eid,
                "entity_type": entity.entity_type,
                "project_id": entity.project_id,
                "version": entity.version,
                "evidence_status": entity.evidence_status,
                "created_at": entity.created_at,
                "created_by": entity.created_by,
            })
        result.sort(key=lambda x: (x["entity_type"], x["version"]))
        return result

    def save(self) -> None:
        """Persist full in-memory state (used at shutdown or on-demand).

        Replaces all JSONL files with the current in-memory snapshot.
        Normal operation relies on append-only writes per mutation.
        """
        self._project_root.mkdir(parents=True, exist_ok=True)
        entities_path = self._entities_path()
        links_path = self._links_path()
        claims_path = self._claims_path()
        for path in (entities_path, links_path, claims_path):
            path.parent.mkdir(parents=True, exist_ok=True)
        with open(entities_path, "w") as f:
            for e in self._entities.values():
                f.write(json.dumps(asdict(e), default=str) + "\n")
        with open(links_path, "w") as f:
            for l in self._links:
                f.write(json.dumps(asdict(l), default=str) + "\n")
        with open(claims_path, "w") as f:
            for eid, claims in self._claims.items():
                for c in claims:
                    record = asdict(c)
                    record["entity_id"] = eid
                    f.write(json.dumps(record, default=str) + "\n")
        self._persist_counters()

    def load(self) -> None:
        """Restore full in-memory state from JSONL files.

        Recovers entities, links, claims and version counters so that
        app restarts preserve monotonic version numbers.
        """
        entities_path = self._entities_path()
        links_path = self._links_path()
        claims_path = self._claims_path()
        self._entities.clear()
        self._links.clear()
        self._claims.clear()
        if entities_path.exists():
            for line in entities_path.read_text().splitlines():
                if line.strip():
                    d = json.loads(line)
                    self._entities[d["entity_id"]] = EntityRecord(**d)
        if links_path.exists():
            for line in links_path.read_text().splitlines():
                if line.strip():
                    d = json.loads(line)
                    self._links.append(LinkRecord(**d))
        if claims_path.exists():
            for line in claims_path.read_text().splitlines():
                if line.strip():
                    d = json.loads(line)
                    self._claims.setdefault(d["entity_id"], []).append(ClaimRecord(**d))
        self._load_counters()
        # Reconstruct counters from durable entities, including pre-v0.4.2 logs.
        for entity in self._entities.values():
            key = (entity.project_id, entity.entity_type)
            self._version_counters[key] = max(self._version_counters.get(key, 0), entity.version)
