# v0.4.0 可信分析鏈 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the trustworthy analysis chain (version chain, phase gates, report evidence package, model governance, anomaly source tracking, experiment loop closure) for the Process Intelligence Platform.

**Architecture:** The system adds a central `VersionChain` manager that tracks entity relationships with append-only JSONL persistence. Each analysis module (modeling, simulation, experiment) registers entities through this chain. Phase gates control analysis progress at the module level. Reports reference chain data to produce traceable evidence packages. Model governance adds pre-fit checks and DOE/AI discrepancy detection.

**Tech Stack:** Python 3.11, NumPy, pandas, scikit-learn, JSONL file I/O, Tauri IPC (JSON-RPC over stdin/stdout), existing test infrastructure (pytest)

---

## File Structure

### New Files
- `engine/src/process_intelligence_engine/versioning/__init__.py`
- `engine/src/process_intelligence_engine/versioning/chain.py` — VersionChain manager
- `engine/src/process_intelligence_engine/gates/__init__.py`
- `engine/src/process_intelligence_engine/gates/manager.py` — Phase gate manager
- `engine/src/process_intelligence_engine/modeling/governance.py` — Model governance rules
- `engine/tests/test_versioning_chain.py`
- `engine/tests/test_gates.py`
- `engine/tests/test_governance.py`
- `engine/tests/test_experiment_verdict.py`

### Modified Files
- `engine/src/process_intelligence_engine/main.py` — Add imports, instantiate managers, register IPC handlers
- `engine/src/process_intelligence_engine/reporting/models.py` — Add chain_trace, source_labels, gate_summary, approval_record, unconfirmed_items, extrapolation_summary
- `engine/src/process_intelligence_engine/reporting/html.py` — Add evidence summary block + 3 appendix sections
- `engine/src/process_intelligence_engine/analysis/anomalies.py` — Add register_anomaly_event function
- `engine/src/process_intelligence_engine/modeling/fitters.py` — Add VIF check, perfect separation detection, calibration check helpers
- `engine/src/process_intelligence_engine/prediction.py` — Add tolerance-aware prediction interval
- `src/lib/engine.ts` — Add TypeScript types + API wrappers for all new endpoints
- `src/features/project/ProjectOverview.tsx` — Add "Analysis Phase" Card
- `src/features/report/Report.tsx` — Update to pass chain data + gate status
- `src/features/settings/Settings.tsx` — Add anomaly source selector UI
- `src/i18n/{en,zh-TW,es-MX}.json` — Add all new i18n keys

---

## Phase A: Version Chain Infrastructure

### Task A1: Create versioning module with EntityRecord, LinkRecord, ClaimRecord

**Files:**
- Create: `engine/src/process_intelligence_engine/versioning/__init__.py`
- Create: `engine/src/process_intelligence_engine/versioning/chain.py`
- Create: `engine/tests/test_versioning_chain.py`

- [ ] **Step 1: Write the failing test**

```python
# engine/tests/test_versioning_chain.py
import pytest
from process_intelligence_engine.versioning.chain import (
    VersionChain,
    EntityRecord,
    LinkRecord,
    ClaimRecord,
)


def test_register_entity_creates_record():
    chain = VersionChain("/tmp/test-project", "user1")
    entity_id = chain.register_entity(
        entity_type="dataset",
        project_id="proj-001",
        metadata={"source_file": "data.csv", "row_count": 45},
        created_by="user1",
    )
    assert entity_id.startswith("ds-")
    entity = chain.get_entity(entity_id)
    assert entity.entity_type == "dataset"
    assert entity.project_id == "proj-001"
    assert entity.metadata["source_file"] == "data.csv"
    assert entity.version == 1


def test_register_entity_increments_version():
    chain = VersionChain("/tmp/test-project", "user1")
    id1 = chain.register_entity("dataset", "proj-001", {"a": 1}, "user1")
    id2 = chain.register_entity("dataset", "proj-001", {"a": 2}, "user1")
    e1 = chain.get_entity(id1)
    e2 = chain.get_entity(id2)
    assert e1.version == 1
    assert e2.version == 2


def test_add_link_creates_connection():
    chain = VersionChain("/tmp/test-project", "user1")
    ds_id = chain.register_entity("dataset", "proj-001", {"a": 1}, "user1")
    md_id = chain.register_entity("model", "proj-001", {"type": "doe_linear"}, "user1")
    chain.add_link(ds_id, md_id, "uses_dataset", "statistically_supported", "user1")
    trace = chain.get_trace(md_id)
    assert len(trace["incoming_links"]) == 1
    assert trace["incoming_links"][0]["relation"] == "uses_dataset"


def test_add_claim_creates_claim_record():
    chain = VersionChain("/tmp/test-project", "user1")
    entity_id = chain.register_entity("model", "proj-001", {"type": "doe_linear"}, "user1")
    claim_id = chain.add_claim(
        entity_id=entity_id,
        claim_type="coefficient_significant",
        text="x1 coefficient is statistically significant (p<0.001)",
        source_entity_ids=[entity_id],
        origin_source="stat_sig",
        evidence_status="statistically_supported",
        confidence=0.95,
    )
    assert claim_id.startswith("cl-")
    claims = chain.get_claims(entity_id)
    assert len(claims) == 1
    assert claims[0]["text"] == "x1 coefficient is statistically significant (p<0.001)"


def test_get_chain_summary_returns_all_entities():
    chain = VersionChain("/tmp/test-project", "user1")
    id1 = chain.register_entity("dataset", "proj-001", {"a": 1}, "user1")
    id2 = chain.register_entity("model", "proj-001", {"type": "doe_linear"}, "user1")
    summary = chain.get_chain_summary()
    assert len(summary) == 2
    assert summary[0]["entity_id"] == id1
    assert summary[1]["entity_id"] == id2


def test_persist_and_reload():
    import tempfile, os
    chain_dir = tempfile.mkdtemp()
    chain = VersionChain(chain_dir, "user1")
    id1 = chain.register_entity("dataset", "proj-001", {"a": 1}, "user1")
    chain.add_link(id1, id1, "uses_dataset", "unverified", "user1")
    chain.save()
    # Reload from disk
    chain2 = VersionChain(chain_dir, "user1")
    chain2.load()
    assert chain2.get_entity(id1).entity_type == "dataset"


def test_entity_with_multiple_parent_ids():
    chain = VersionChain("/tmp/test-project", "user1")
    p1 = chain.register_entity("dataset", "proj-001", {"a": 1}, "user1")
    p2 = chain.register_entity("anomaly", "proj-001", {"type": "spec"}, "user1")
    child = chain.register_entity(
        "model", "proj-001", {"type": "doe_linear"}, "user1",
        parent_ids=[p1, p2],
    )
    entity = chain.get_entity(child)
    assert p1 in entity.parent_ids
    assert p2 in entity.parent_ids


def test_get_trace_returns_full_graph():
    chain = VersionChain("/tmp/test-project", "user1")
    ds = chain.register_entity("dataset", "proj-001", {"a": 1}, "user1")
    md = chain.register_entity("model", "proj-001", {"type": "doe_linear"}, "user1")
    sim = chain.register_entity("simulation", "proj-001", {"seed": 42}, "user1")
    chain.add_link(ds, md, "uses_dataset", "unverified", "user1")
    chain.add_link(md, sim, "simulated_by", "unverified", "user1")
    trace = chain.get_trace(sim)
    assert trace["entity_id"] == sim
    assert len(trace["outgoing_links"]) == 1
    assert trace["outgoing_links"][0]["to_id"] == md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python -m pytest tests/test_versioning_chain.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'process_intelligence_engine.versioning'"

- [ ] **Step 3: Create versioning/__init__.py**

Create `engine/src/process_intelligence_engine/versioning/__init__.py`:
```python
from .chain import VersionChain, EntityRecord, LinkRecord, ClaimRecord

__all__ = ["VersionChain", "EntityRecord", "LinkRecord", "ClaimRecord"]
```

- [ ] **Step 4: Create versioning/chain.py**

Create `engine/src/process_intelligence_engine/versioning/chain.py`:
```python
"""Append-only version chain with JSONL persistence.

Tracks cross-entity relationships with content hashes and evidence status.
"""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
    evidence_status: str  # unverified | statistically_supported | experimentally_confirmed


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
    origin_source: str  # historical_observation | engineering_input | ai_estimate | user_override | stat_sig | exp_confirmed
    evidence_status: str
    confidence: float | None
    valid_range: dict | None


class VersionChain:
    """Central version chain manager with JSONL persistence."""

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
        self._locks: dict[str, threading.Lock] = {}
        self._version_counters: dict[str, int] = {}
        self._lock = threading.Lock()

    def _prefix(self, entity_type: str) -> str:
        return self.PREFIX_MAP.get(entity_type, "ent")

    def _compute_hash(self, data: dict) -> str:
        raw = json.dumps(data, sort_keys=True, default=str).encode()
        return hashlib.sha256(raw).hexdigest()[:16]

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
            self._version_counters.setdefault(entity_type, 0)
            self._version_counters[entity_type] += 1
            ver = self._version_counters[entity_type]
            entity_id = f"{prefix}-{uuid.uuid4().hex[:8]}"
            if content_hash:
                content_hash = self._compute_hash(metadata)
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
        self._project_root.mkdir(parents=True, exist_ok=True)
        entities_path = self._project_root / "registry" / "version_chain.jsonl"
        links_path = self._project_root / "registry" / "links.jsonl"
        claims_path = self._project_root / "registry" / "claims.jsonl"
        entities_path.parent.mkdir(parents=True, exist_ok=True)
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

    def load(self) -> None:
        entities_path = self._project_root / "registry" / "version_chain.jsonl"
        links_path = self._project_root / "registry" / "links.jsonl"
        claims_path = self._project_root / "registry" / "claims.jsonl"
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd engine && python -m pytest tests/test_versioning_chain.py -v`
Expected: All 8 tests PASS

- [ ] **Step 6: Commit**

```bash
git add engine/src/process_intelligence_engine/versioning/ engine/tests/test_versioning_chain.py
git commit -m "feat(versioning): add VersionChain with JSONL persistence"
```

---

### Task A2: Integrate VersionChain into main.py handlers

**Files:**
- Modify: `engine/src/process_intelligence_engine/main.py` (add import, instantiate, register)
- Modify: `engine/src/process_intelligence_engine/reporting/registry.py` (add chain_id to report registration)
- Modify: `engine/src/process_intelligence_engine/modeling/registry.py` (add chain_id to model registration)

- [ ] **Step 1: Write failing tests for chain integration**

```python
# engine/tests/test_versioning_chain.py (append)
def test_handle_data_import_registers_dataset():
    """Verify data/import handler registers dataset in version chain."""
    import tempfile, pathlib
    tmp = tempfile.mkdtemp()
    csv = pathlib.Path(tmp) / "test.csv"
    csv.write_text("x,y\n1,2\n3,4\n5,6\n")
    chain = VersionChain(tmp, "testuser")
    from process_intelligence_engine.main import REGISTRY, _handle_data_import
    result = _handle_data_import({"file_path": str(csv), "project_root": tmp})
    dataset_id = result["dataset_id"]
    # Should have registered in chain
    summary = chain.get_chain_summary()
    assert any(e["entity_type"] == "dataset" for e in summary)


def test_handle_modeling_fit_registers_model():
    """Verify modeling/fit handler registers model in version chain."""
    import tempfile, pathlib
    tmp = tempfile.mkdtemp()
    csv = pathlib.Path(tmp) / "test.csv"
    csv.write_text("x,y\n1,2\n3,4\n5,6\n7,8\n9,10\n")
    chain = VersionChain(tmp, "testuser")
    from process_intelligence_engine.main import REGISTRY, MODEL_REGISTRY, _handle_modeling_fit, _handle_data_import
    import_result = _handle_data_import({"file_path": str(csv), "project_root": tmp})
    dataset_id = import_result["dataset_id"]
    result = _handle_modeling_fit({
        "dataset_id": dataset_id,
        "model_type": "doe_linear",
        "target": "y",
        "inputs": ["x"],
    })
    model_id = result["model_id"]
    summary = chain.get_chain_summary()
    assert any(e["entity_id"] == model_id for e in summary)
```

- [ ] **Step 2: Add VersionChain singleton to main.py**

Add after line 148 (`REGISTRY = DatasetRegistry()`):
```python
# Version chain for cross-entity traceability (v0.4.0)
_VERSION_CHAIN = VersionChain("/tmp/default-project", "anonymous")
```

- [ ] **Step 3: Register dataset entity on data/import**

Find `_handle_data_import` and add chain registration at the end (before return):
```python
# Register in version chain
dataset_entity_id = _VERSION_CHAIN.register_entity(
    entity_type="dataset",
    project_id=params.get("project_root", "default"),
    metadata={
        "source_file": params.get("file_path", ""),
        "row_count": len(df),
        "column_count": len(df.columns),
    },
    created_by=operator,
)
return {**result, "chain_entity_id": dataset_entity_id}
```

- [ ] **Step 4: Register model entity on modeling/fit**

Find `_handle_modeling_fit` and add chain registration after `MODEL_REGISTRY.register(fit)`:
```python
model_entity_id = _VERSION_CHAIN.register_entity(
    entity_type="model",
    project_id=params.get("project_root", "default"),
    metadata={
        "model_type": model_type,
        "dataset_id": dataset_id,
        "target": params.get("target", ""),
        "inputs": params.get("inputs", []),
        "n_train": int(fit.n_train) if hasattr(fit, 'n_train') else 0,
        "n_test": int(fit.n_test) if hasattr(fit, 'n_test') else 0,
    },
    created_by=operator,
)
fit.chain_entity_id = model_entity_id
return {**result, "chain_entity_id": model_entity_id}
```

- [ ] **Step 5: Run tests**

Run: `cd engine && python -m pytest tests/test_versioning_chain.py -v`
Expected: All tests PASS

- [ ] **Step 6: Add IPC handlers for chain API**

Add at the end of main.py handler dispatch (before `if __name__ == "__main__"`):
```python
# Version chain handlers (v0.4.0)
elif method == "versioning/chain/summary":
    result = _VERSION_CHAIN.get_chain_summary()
elif method == "versioning/chain/trace":
    result = _VERSION_CHAIN.get_trace(params["entity_id"])
elif method == "versioning/chain/link":
    _VERSION_CHAIN.add_link(
        params["from_id"], params["to_id"],
        params["relation"],
        params.get("evidence_status", "unverified"),
        params.get("created_by", _VERSION_CHAIN._operator),
    )
    result = {"success": True}
```

- [ ] **Step 7: Commit**

```bash
git add engine/src/process_intelligence_engine/main.py engine/tests/test_versioning_chain.py
git commit -m "feat(versioning): integrate VersionChain into main handlers"
```

---

### Task A3: Add version chain tests to main handler suite

- [ ] **Step 1: Add tests to test_main_handlers.py**

```python
def test_version_chain_summary_after_import(tmp_path):
    csv = tmp_path / "test.csv"
    csv.write_text("x,y\n1,2\n3,4\n5,6\n")
    handle_request("versioning/chain/summary", {})  # warm up
    result = handle_request("data/import", {"file_path": str(csv)})
    did = result["dataset_id"]
    summary = handle_request("versioning/chain/summary", {})
    assert any(e["entity_type"] == "dataset" for e in summary["summary"])
```

- [ ] **Step 2: Run and commit**

```bash
cd engine && python -m pytest tests/test_main_handlers.py::test_version_chain_summary_after_import -v
git add engine/tests/test_main_handlers.py
git commit -m "test: add version chain integration tests to handler suite"
```

---

## Phase B: Analysis Phase Gates

### Task B1: Create gates manager module

**Files:**
- Create: `engine/src/process_intelligence_engine/gates/__init__.py`
- Create: `engine/src/process_intelligence_engine/gates/manager.py`
- Create: `engine/tests/test_gates.py`

- [ ] **Step 1: Write the failing test**

```python
# engine/tests/test_gates.py
import pytest
from process_intelligence_engine.gates.manager import GateManager, GateStatus


def test_initial_status_is_not_started():
    gm = GateManager()
    status = gm.get_status("modeling")
    assert status == "not_started"


def test_confirm_transition():
    gm = GateManager()
    result = gm.confirm(
        module="modeling",
        entity_id="md-abc123",
        entity_version=1,
        confirmed_by="fred",
        comment="Model approved",
    )
    assert result["new_status"] == "confirmed"
    assert gm.get_status("modeling") == "confirmed"


def test_confirm_with_wrong_version_invalidates():
    gm = GateManager()
    gm.confirm("modeling", "md-old", 1, "fred", "")
    # New model registered with same module but different version
    gm.confirm("modeling", "md-new", 2, "fred", "")
    status = gm.get_status("modeling")
    assert status == "confirmed"  # Latest version takes over


def test_reset_to_pending():
    gm = GateManager()
    gm.confirm("modeling", "md-abc", 1, "fred", "")
    gm.reset("modeling", "fred changed inputs")
    assert gm.get_status("modeling") == "pending_confirmation"


def test_summary_reports_all_modules():
    gm = GateManager()
    gm.confirm("modeling", "md-1", 1, "fred", "")
    gm.confirm("monte_carlo", "sim-1", 1, "fred", "")
    summary = gm.get_summary()
    assert summary["modeling"] == "confirmed"
    assert summary["monte_carlo"] == "confirmed"
    assert summary["data_import"] == "not_started"


def test_confirm_requires_entity_id():
    gm = GateManager()
    with pytest.raises(ValueError):
        gm.confirm("modeling", "", 1, "fred", "")
```

- [ ] **Step 2: Create gates/__init__.py**

```python
from .manager import GateManager, GateStatus

__all__ = ["GateManager", "GateStatus"]
```

- [ ] **Step 3: Create gates/manager.py**

```python
"""Analysis phase gate manager.

Controls the not_started -> pending_confirmation -> confirmed state machine
per module. Each confirmation is bound to an entity_id and entity_version.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class GateStatus(str, Enum):
    NOT_STARTED = "not_started"
    PENDING_CONFIRMATION = "pending_confirmation"
    CONFIRMED = "confirmed"


VALID_TRANSITIONS = {
    GateStatus.NOT_STARTED: {GateStatus.PENDING_CONFIRMATION},
    GateStatus.PENDING_CONFIRMATION: {GateStatus.CONFIRMED, GateStatus.NOT_STARTED},
    GateStatus.CONFIRMED: {GateStatus.PENDING_CONFIRMATION},
}


@dataclass
class GateRecord:
    module: str
    entity_id: str
    entity_version: int
    status: str
    confirmed_by: str
    confirmed_at: str
    reset_reason: str = ""
    comment: str = ""


class GateManager:
    """Manages per-module analysis phase gates."""

    ALL_MODULES = [
        "data_import", "process_define", "modeling",
        "spc", "monte_carlo", "prediction", "validation",
    ]

    def __init__(self) -> None:
        self._gates: dict[str, GateRecord] = {}
        self._lock = threading.Lock()
        for mod in self.ALL_MODULES:
            self._gates[mod] = GateRecord(
                module=mod,
                entity_id="",
                entity_version=0,
                status=GateStatus.NOT_STARTED.value,
                confirmed_by="",
                confirmed_at="",
            )

    def get_status(self, module: str) -> str:
        with self._lock:
            return self._gates.get(module, GateRecord(
                module=module, entity_id="", entity_version=0,
                status=GateStatus.NOT_STARTED.value, confirmed_by="", confirmed_at="",
            )).status

    def confirm(
        self,
        module: str,
        entity_id: str,
        entity_version: int,
        confirmed_by: str,
        comment: str = "",
    ) -> dict:
        if not entity_id:
            raise ValueError("entity_id is required")
        with self._lock:
            gate = self._gates[module]
            # If entity_version changed, invalidate old confirmation
            if gate.entity_version != entity_version:
                gate.status = GateStatus.PENDING_CONFIRMATION.value
                gate.entity_id = entity_id
                gate.entity_version = entity_version
            gate.status = GateStatus.CONFIRMED.value
            gate.confirmed_by = confirmed_by
            gate.confirmed_at = datetime.now(timezone.utc).isoformat()
            gate.comment = comment
            return {"new_status": GateStatus.CONFIRMED.value}

    def reset(self, module: str, reason: str = "") -> dict:
        with self._lock:
            gate = self._gates[module]
            gate.status = GateStatus.PENDING_CONFIRMATION.value
            gate.reset_reason = reason
            return {"new_status": GateStatus.PENDING_CONFIRMATION.value}

    def get_summary(self) -> dict[str, str]:
        with self._lock:
            return {mod: self._gates[mod].status for mod in self.ALL_MODULES}

    def get_details(self, module: str) -> dict[str, Any]:
        with self._lock:
            gate = self._gates.get(module)
            if gate is None:
                return {"module": module, "status": GateStatus.NOT_STARTED.value}
            return {
                "module": gate.module,
                "status": gate.status,
                "entity_id": gate.entity_id,
                "entity_version": gate.entity_version,
                "confirmed_by": gate.confirmed_by,
                "confirmed_at": gate.confirmed_at,
                "reset_reason": gate.reset_reason,
                "comment": gate.comment,
            }

    def are_all_confirmed(self, modules: list[str] | None = None) -> bool:
        with self._lock:
            mods = modules or self.ALL_MODULES
            return all(self._gates[m].status == GateStatus.CONFIRMED.value for m in mods if m in self._gates)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd engine && python -m pytest tests/test_gates.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Add IPC handlers to main.py**

```python
# After existing handler imports
from process_intelligence_engine.gates.manager import GateManager

# Add singleton
GATE_MANAGER = GateManager()

# Add handlers in dispatch section
elif method == "gates/status":
    result = {"statuses": GATE_MANAGER.get_summary()}
elif method == "gates/confirm":
    result = GATE_MANAGER.confirm(
        params["module"],
        params["entity_id"],
        params["entity_version"],
        params["confirmed_by"],
        params.get("comment", ""),
    )
elif method == "gates/reset":
    result = GATE_MANAGER.reset(params["module"], params.get("reason", ""))
elif method == "gates/summary":
    result = {
        "summary": GATE_MANAGER.get_summary(),
        "all_confirmed": GATE_MANAGER.are_all_confirmed(),
        "details": {m: GATE_MANAGER.get_details(m) for m in params.get("modules", GATE_MANAGER.ALL_MODULES)},
    }
```

- [ ] **Step 6: Commit**

```bash
git add engine/src/process_intelligence_engine/gates/ engine/src/process_intelligence_engine/main.py
git commit -m "feat(gates): add phase gate manager with module-level confirmation"
```

---

## Phase C: Report Evidence Package

### Task C1: Extend ReportData with evidence chain fields

- [ ] **Step 1: Modify reporting/models.py**

Add after existing fields:
```python
    # Evidence chain (v0.4.0)
    chain_trace: dict = field(default_factory=dict)
    source_labels: dict = field(default_factory=dict)
    gate_summary: dict = field(default_factory=dict)
    approval_record: dict | None = None
    unconfirmed_items: list[str] = field(default_factory=list)
    extrapolation_summary: dict = field(default_factory=dict)
    version_chain_summary: list[dict] = field(default_factory=list)
```

- [ ] **Step 2: Commit**

```bash
git add engine/src/process_intelligence_engine/reporting/models.py
git commit -m "feat(reporting): extend ReportData with evidence chain fields"
```

---

### Task C2: Add evidence summary + appendix to HTML report

- [ ] **Step 1: Modify reporting/html.py**

Add to `_generate_html()` before sections list:
```python
def _render_evidence_summary(self) -> str:
    """Render evidence chain summary at report top."""
    ct = self.data.chain_trace or {}
    gs = self.data.gate_summary or {}
    unconfirmed = self.data.unconfirmed_items or []
    
    body = '<div class="evidence-summary">'
    body += '<h3>分析證據摘要</h3>'
    
    # Dataset info
    ds = ct.get("dataset", {})
    body += f"<p><strong>資料集:</strong> {self._e(ds.get('entity_id', 'N/A'))} | "
    body += f"版本: v{self._e(ds.get('version', 'N/A'))} | "
    body += f"筆數: {self._e(ds.get('metadata', {}).get('row_count', 'N/A'))}</p>"
    
    # Gate status
    confirmed = sum(1 for v in gs.values() if v == 'confirmed')
    total = len(gs)
    body += f"<p><strong>階段閘門:</strong> {confirmed}/{total} 已確認</p>"
    
    # Unconfirmed items
    if unconfirmed:
        body += '<p class="warning"><strong>未確認項目:</strong>'
        for item in unconfirmed[:5]:
            body += f' <span class="badge badge-warning">{self._e(item)}</span>'
        body += '</p>'
    
    body += '</div>'
    return body
```

Add to sections list in `_generate_html()`:
```python
sections = [
    self._render_evidence_summary(),  # NEW: evidence summary at top
    self._render_info(),
    # ... existing sections ...
]
```

Add after existing sections (before `_render_footer`):
```python
def _render_appendix_chain(self) -> str:
    """Appendix A: Version chain trace table."""
    chain = self.data.chain_trace or {}
    if not chain:
        return ""
    rows = []
    for step in chain.get("steps", []):
        rows.append(f"<tr><td>{self._e(step.get('step'))}</td>"
                    f"<td>{self._e(step.get('entity_id'))}</td>"
                    f"<td>{self._e(step.get('operator'))}</td>"
                    f"<td>{self._e(step.get('timestamp'))}</td>"
                    f"<td><span class='badge badge-{('success' if step.get('status')=='confirmed' else 'warning') if step.get('status') else 'info'}'>{self._e(step.get('status') or 'unverified')}</span></td></tr>")
    body = "<table><tr><th>分析步驟</th><th>實體 ID</th><th>操作者</th><th>時間</th><th>狀態</th></tr>" + "".join(rows) + "</table>"
    return f"<h3>Appendix A: 版本鏈追溯</h3>{body}" if rows else ""

def _render_appendix_labels(self) -> str:
    """Appendix B: Source label legend."""
    labels = self.data.source_labels or {
        "ai_guess": "AI 推測",
        "stat_sig": "統計顯著",
        "eng_hypothesis": "工程假設",
        "exp_confirmed": "實驗已確認",
        "unverified": "未驗證",
    }
    rows = [f"<tr><td><code>{self._e(k)}</code></td><td>{self._e(v)}</td></tr>" for k, v in labels.items()]
    body = "<table><tr><th>標籤鍵</th><th>含義</th></tr>" + "".join(rows) + "</table>"
    return f"<h3>Appendix B: 來源標籤解讀</h3>{body}"

def _render_appendix_extrapolation(self) -> str:
    """Appendix C: Extrapolation warning statistics."""
    ex = self.data.extrapolation_summary or {}
    if not ex:
        return ""
    body = f"<p><strong>訓練範圍外預測比例:</strong> {self._pct(ex.get('out_of_range_ratio'))}</p>"
    body += f"<p><strong>最大外插風險分數:</strong> {self._fmt(ex.get('max_risk_score'))}</p>"
    if ex.get("recommendation"):
        body += f"<p><strong>建議:</strong> {self._e(ex['recommendation'])}</p>"
    return f"<h3>Appendix C: 外插警告統計</h3>{body}"
```

- [ ] **Step 2: Modify main.py _handle_report_generate to populate chain data**

Find the report generation handler and add at the end before returning:
```python
# v0.4.0: Populate chain trace and gate summary
chain_trace = _VERSION_CHAIN.get_chain_summary()
gate_summary = GATE_MANAGER.get_summary()
unconfirmed = [m for m, s in gate_summary.items() if s != "confirmed"]

# Build chain trace for report
trace_steps = []
for entity in chain_trace:
    trace_steps.append({
        "step": f"{entity['entity_type']} v{entity['version']}",
        "entity_id": entity["entity_id"],
        "operator": entity.get("created_by", "anonymous"),
        "timestamp": entity.get("created_at", ""),
        "status": entity.get("evidence_status", "unverified"),
    })

report_data.chain_trace = {"steps": trace_steps}
report_data.gate_summary = gate_summary
report_data.unconfirmed_items = unconfirmed
report_data.version_chain_summary = chain_trace
```

- [ ] **Step 3: Commit**

```bash
git add engine/src/process_intelligence_engine/reporting/ engine/src/process_intelligence_engine/main.py
git commit -m "feat(reporting): add evidence package to HTML report"
```

---

## Phase D: Model Governance Rules

### Task D1: Create governance module

**Files:**
- Create: `engine/src/process_intelligence_engine/modeling/governance.py`
- Create: `engine/tests/test_governance.py`

- [ ] **Step 1: Write the failing test**

```python
# engine/tests/test_governance.py
import pytest
import pandas as pd
import numpy as np
from process_intelligence_engine.modeling.governance import (
    check_model_applicability,
    check_doeb_ai_discrepancy,
    recommend_models,
)


def test_small_sample_warns_tree_models():
    # 20 samples < 30
    df = pd.DataFrame({"x": np.random.rand(20), "y": np.random.rand(20)})
    warnings = check_model_applicability(df, target="y", inputs=["x"])
    assert any("tree" in w.lower() for w in warnings)


def test_class_imbalance_warns():
    df = pd.DataFrame({"x": np.random.rand(100), "y": ["OK"]*95 + ["NG"]*5})
    warnings = check_model_applicability(df, target="y", inputs=["x"], is_binary=True)
    assert any("imbalance" in w.lower() or "失衡" in w for w in warnings)


def test_doeb_ai_discrepancy_small_diff():
    result = check_doeb_ai_discrepancy(
        doe_r2=0.85, ai_r2=0.88,
        ai_pred=[1.0, 2.0, 3.0],
        doe_pred=[1.05, 2.02, 2.98],
        scale=1.0,
    )
    assert result["needs_review"] == False


def test_doeb_ai_discrepancy_large_diff():
    result = check_doeb_ai_discrepancy(
        doe_r2=0.50, ai_r2=0.90,
        ai_pred=[1.0, 2.0, 3.0],
        doe_pred=[1.5, 2.8, 4.0],
        scale=1.0,
    )
    assert result["needs_review"] == True
    assert "人工審查" in result["recommendation"] or "manual review" in result["recommendation"].lower()


def test_recommend_models_small_sample():
    recs = recommend_models(n_samples=30, n_features=3, is_binary_target=False, has_nonlinearity=False, need_interpretability=True)
    assert "doe_linear" in recs


def test_recommend_models_large_sample_no_interpretability():
    recs = recommend_models(n_samples=500, n_features=10, is_binary_target=False, has_nonlinearity=True, need_interpretability=False)
    assert "xgboost" in recs or "lightgbm" in recs
    assert "doe_linear" not in recs
```

- [ ] **Step 2: Create governance.py**

```python
"""Model governance: applicability checks, DOE vs AI comparison, model recommendation."""
from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Any


def check_model_applicability(
    df: pd.DataFrame,
    target: str,
    inputs: list[str],
    is_binary: bool = False,
) -> list[str]:
    """Run pre-fit applicability checks. Returns list of warning strings."""
    warnings = []
    n = len(df)
    
    # Minimum sample check
    if n < 30:
        warnings.append(f"樣本數不足 ({n} < 30)，tree models 不建議使用")
    
    # Class imbalance check
    if is_binary:
        target_vals = df[target]
        if target_vals.dtype == 'object':
            counts = target_vals.value_counts()
            if len(counts) == 2:
                ratio = counts.max() / max(counts.min(), 1)
                if ratio > 4:
                    warnings.append(f"類別失衡 (比例 {ratio:.1f}:1)，logistic 回歸效果可能不可信")
    
    # Constant column check
    for col in inputs:
        if col in df.columns and df[col].nunique() == 1:
            warnings.append(f"欄位 {col} 為常數，將被自動排除")
    
    # VIF check (multicollinearity)
    if len(inputs) >= 2:
        try:
            X = df[inputs].apply(pd.to_numeric, errors='coerce')
            X = X.dropna()
            if len(X) >= 10:
                # Simple correlation-based VIF approximation
                for i, col_i in enumerate(inputs):
                    if col_i not in X.columns:
                        continue
                    others = [c for c in inputs if c != col_i and c in X.columns]
                    if others:
                        from sklearn.linear_model import LinearRegression
                        lr = LinearRegression()
                        lr.fit(X[others], X[col_i])
                        r2 = lr.score(X[others], X[col_i])
                        vif = 1 / (1 - r2) if r2 < 0.999 else float('inf')
                        if vif > 10:
                            warnings.append(f"多重共線性警告: {col_i} 與 {[c for c in others if c != col_i]} 高度相關 (VIF={vif:.1f})")
        except Exception:
            pass  # Skip VIF on invalid data
    
    return warnings


def check_doeb_ai_discrepancy(
    doe_r2: float,
    ai_r2: float,
    ai_pred: list[float],
    doe_pred: list[float],
    scale: float,
    mean_threshold: float = 0.15,
    max_threshold: float = 0.30,
) -> dict:
    """Check if DOE and AI predictions differ significantly."""
    if not ai_pred or not doe_pred:
        return {"needs_review": False, "recommendation": "無法比較：缺少預測資料"}
    
    normalized_diff = [
        abs(a - b) / max(scale, 1e-12)
        for a, b in zip(ai_pred, doe_pred)
    ]
    max_diff = max(normalized_diff)
    mean_diff = sum(normalized_diff) / len(normalized_diff)
    
    needs_review = max_diff > max_threshold or mean_diff > mean_threshold
    
    return {
        "needs_review": needs_review,
        "max_difference": round(max_diff, 4),
        "mean_difference": round(mean_diff, 4),
        "doe_r2": doe_r2,
        "ai_r2": ai_r2,
        "recommendation": (
            "需要人工審查，預設採 DOE 作為保守基準"
            if needs_review else "AI 模型可進入後續驗證"
        ),
    }


def recommend_models(
    n_samples: int,
    n_features: int,
    is_binary_target: bool,
    has_nonlinearity: bool,
    need_interpretability: bool,
) -> list[str]:
    """Recommend suitable model types based on data characteristics."""
    recommendations = []
    
    if is_binary_target:
        recommendations.append("logistic_regression")
        if n_samples >= 100:
            recommendations.append("xgboost")
    else:
        if n_samples < 50:
            recommendations.append("doe_linear")
            if n_features >= 2:
                recommendations.append("doe_quadratic")
        elif n_samples < 200:
            recommendations.append("doe_quadratic")
            if has_nonlinearity:
                recommendations.append("residual_hybrid")
        else:
            if need_interpretability:
                recommendations.append("doe_linear")
                recommendations.append("residual_hybrid")
            else:
                recommendations.append("xgboost")
                recommendations.append("lightgbm")
    
    if n_samples >= 100 and not need_interpretability:
        recommendations.append("random_forest")
    
    return recommendations
```

- [ ] **Step 3: Run tests**

Run: `cd engine && python -m pytest tests/test_governance.py -v`
Expected: All tests PASS

- [ ] **Step 4: Add IPC handlers to main.py**

```python
from process_intelligence_engine.modeling.governance import (
    check_model_applicability,
    check_doeb_ai_discrepancy,
    recommend_models,
)

# In dispatch section:
elif method == "modeling/governance/check":
    dataset_id = params.get("dataset_id")
    df = REGISTRY.get(dataset_id)
    warnings = check_model_applicability(
        df, params["target"], params["inputs"],
        is_binary=params.get("is_binary", False),
    )
    result = {"warnings": warnings, "can_proceed": len([w for w in warnings if "tree" in w.lower() and "不建議" in w]) == 0}
elif method == "modeling/governance/recommend":
    recs = recommend_models(
        params.get("n_samples", 0),
        params.get("n_features", 0),
        params.get("is_binary_target", False),
        params.get("has_nonlinearity", False),
        params.get("need_interpretability", True),
    )
    result = {"recommendations": recs}
elif method == "modeling/governance/doe_ai_compare":
    result = check_doeb_ai_discrepancy(
        params.get("doe_r2", 0),
        params.get("ai_r2", 0),
        params.get("ai_pred", []),
        params.get("doe_pred", []),
        params.get("scale", 1.0),
    )
```

- [ ] **Step 5: Commit**

```bash
git add engine/src/process_intelligence_engine/modeling/governance.py engine/tests/test_governance.py engine/src/process_intelligence_engine/main.py
git commit -m "feat(governance): add model applicability checks and DOE/AI comparison"
```

---

## Phase E: Anomaly Source Tracking

### Task E1: Add register_anomaly_event to anomalies.py

- [ ] **Step 1: Modify analysis/anomalies.py**

Add at end of file:
```python
def register_anomaly_event(
    chain,
    dataset_id: str,
    anomaly_id: str,
    source: str,
    confidence: float,
    user_confirmed: bool,
    operator: str,
) -> str:
    """Register an anomaly event in the version chain."""
    entity_id = chain.register_entity(
        entity_type="anomaly",
        project_id=dataset_id,
        metadata={
            "dataset_id": dataset_id,
            "anomaly_id": anomaly_id,
            "source": source,
            "confidence": confidence,
            "user_confirmed": user_confirmed,
            "operator": operator,
        },
        created_by=operator,
    )
    chain.add_link(entity_id, dataset_id, "derived_from", "unverified", operator)
    return entity_id
```

- [ ] **Step 2: Add IPC handler**

In main.py dispatch:
```python
elif method == "analysis/anomaly/register":
    from process_intelligence_engine.analysis.anomalies import register_anomaly_event
    entity_id = register_anomaly_event(
        _VERSION_CHAIN,
        params.get("dataset_id", ""),
        params["anomaly_id"],
        params.get("source", "historical_observation"),
        params.get("confidence", 0.0),
        params.get("user_confirmed", False),
        params.get("operator", "anonymous"),
    )
    result = {"entity_id": entity_id}
```

- [ ] **Step 3: Commit**

```bash
git add engine/src/process_intelligence_engine/analysis/anomalies.py engine/src/process_intelligence_engine/main.py
git commit -m "feat(anomalies): add register_anomaly_event for version chain tracking"
```

---

## Phase F: Experiment Loop Closure

### Task F1: Add verdict computation and experiment handlers

- [ ] **Step 1: Write tests**

```python
# engine/tests/test_experiment_verdict.py
import pytest
from process_intelligence_engine.main import EXPERIMENT_REGISTRY, _handle_experiment_record_with_verdict, _handle_experiment_suggest_next
from process_intelligence_engine.modeling.governance import update_model_after_experiment


def test_compute_verdict_supports():
    from process_intelligence_engine.modeling.governance import compute_experiment_verdict
    assert compute_experiment_verdict(5.0, 5.1, tolerance=0.5) == "supports"


def test_compute_verdict_does_not_support():
    from process_intelligence_engine.modeling.governance import compute_experiment_verdict
    assert compute_experiment_verdict(5.0, 7.0, tolerance=0.5) == "does_not_support"


def test_experiment_record_with_verdict():
    import tempfile, pathlib
    tmp = tempfile.mkdtemp()
    csv = pathlib.Path(tmp) / "test.csv"
    csv.write_text("x,y\n1,2\n3,4\n5,6\n")
    from process_intelligence_engine.main import REGISTRY, _handle_data_import, _handle_modeling_fit
    import_result = _handle_data_import({"file_path": str(csv), "project_root": tmp})
    dataset_id = import_result["dataset_id"]
    fit_result = _handle_modeling_fit({
        "dataset_id": dataset_id, "model_type": "doe_linear",
        "target": "y", "inputs": ["x"], "project_root": tmp,
    })
    model_id = fit_result["model_id"]
    result = _handle_experiment_record_with_verdict({
        "experiment_id": "exp-test-001",
        "model_id": model_id,
        "planned_inputs": {"x": 2.0},
        "actual_inputs": {"x": 2.0},
        "predicted_output": 4.0,
        "actual_output": 4.1,
        "tolerance": 0.5,
        "operator": "fred",
    })
    assert result["verdict"] == "supports"


def test_suggest_next_experiment_returns_list():
    import tempfile, pathlib
    tmp = tempfile.mkdtemp()
    csv = pathlib.Path(tmp) / "test.csv"
    csv.write_text("x,y\n1,2\n3,4\n5,6\n7,8\n9,10\n")
    from process_intelligence_engine.main import REGISTRY, _handle_data_import, _handle_modeling_fit
    import_result = _handle_data_import({"file_path": str(csv), "project_root": tmp})
    dataset_id = import_result["dataset_id"]
    fit_result = _handle_modeling_fit({
        "dataset_id": dataset_id, "model_type": "doe_linear",
        "target": "y", "inputs": ["x"], "project_root": tmp,
    })
    model_id = fit_result["model_id"]
    result = _handle_experiment_suggest_next({"model_id": model_id, "n_suggestions": 3})
    assert isinstance(result["suggestions"], list)
```

- [ ] **Step 2: Add compute_experiment_verdict to governance.py**

```python
def compute_experiment_verdict(
    predicted: float,
    actual: float,
    tolerance: float = 0.1,
) -> str:
    """Compute experiment verdict based on prediction error."""
    abs_error = abs(actual - predicted)
    if abs_error <= tolerance * 0.5:
        return "supports"
    elif abs_error <= tolerance:
        return "partially_supports"
    elif abs_error <= tolerance * 2:
        return "does_not_support"
    else:
        return "needs_remodel"
```

- [ ] **Step 3: Add handlers to main.py**

```python
def _handle_experiment_record_with_verdict(params: dict) -> dict:
    """Record experiment with automatic verdict computation."""
    from process_intelligence_engine.modeling.governance import compute_experiment_verdict
    predicted = float(params.get("predicted_output", 0))
    actual = float(params.get("actual_output", 0))
    tolerance = float(params.get("tolerance", 0.1))
    verdict = compute_experiment_verdict(predicted, actual, tolerance)
    
    # Record experiment normally
    exp_result = _handle_experiment_record({
        k: v for k, v in params.items()
        if k not in ("tolerance", "verdict")
    })
    
    return {
        **exp_result,
        "verdict": verdict,
        "prediction_error": abs(actual - predicted),
    }


def _handle_experiment_suggest_next(params: dict) -> dict:
    """Recommend next experiment conditions based on model uncertainty."""
    model_id = params["model_id"]
    n_suggestions = params.get("n_suggestions", 3)
    
    # Get model from registry
    try:
        model = MODEL_REGISTRY.get(model_id)
    except KeyError:
        return {"error": f"Unknown model_id: {model_id}", "suggestions": []}
    
    # Generate suggestions based on input ranges
    suggestions = []
    if hasattr(model, 'input_ranges') and model.input_ranges:
        for col, rng in model.input_ranges.items():
            suggestions.append({
                "condition": {col: rng.get("low", 0)},
                "rationale": "low_boundary",
            })
            suggestions.append({
                "condition": {col: rng.get("high", 0)},
                "rationale": "high_boundary",
            })
    
    # Always suggest center point
    if suggestions:
        center = {k: (v.get("low", 0) + v.get("high", 0)) / 2 for k, v in (model.input_ranges or {}).items()}
        if center:
            suggestions.append({"condition": center, "rationale": "center_point"})
    
    return {"suggestions": suggestions[:n_suggestions]}
```

- [ ] **Step 4: Run tests**

Run: `cd engine && python -m pytest tests/test_experiment_verdict.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add engine/src/process_intelligence_engine/modeling/governance.py engine/src/process_intelligence_engine/main.py engine/tests/test_experiment_verdict.py
git commit -m "feat(experiment): add verdict computation and next experiment recommendation"
```

---

## Frontend Integration

### Task F2: Add TypeScript types and API wrappers

**Files:**
- Modify: `src/lib/engine.ts`

- [ ] **Step 1: Add new types**

Add after existing type definitions:
```typescript
// v0.4.0 Evidence Chain
export interface ChainEntitySummary {
  entity_id: string;
  entity_type: string;
  project_id: string;
  version: number;
  evidence_status: string;
  created_at: string;
  created_by: string;
}

export interface ChainTrace {
  entity_id: string;
  entity_type: string;
  project_id: string;
  version: number;
  metadata: Record<string, any>;
  parent_ids: string[];
  evidence_status: string;
  incoming_links: ChainLink[];
  outgoing_links: ChainLink[];
  claims: ChainClaim[];
  created_at: string;
  created_by: string;
}

export interface ChainLink {
  from_id: string;
  to_id: string;
  relation: string;
  evidence_status: string;
  created_by: string;
  created_at: string;
}

export interface ChainClaim {
  claim_id: string;
  entity_id: string;
  claim_type: string;
  text: string;
  source_entity_ids: string[];
  origin_source: string;
  evidence_status: string;
  confidence: number | null;
}

// v0.4.0 Model Governance
export interface GovernanceCheckResult {
  warnings: string[];
  can_proceed: boolean;
}

export interface ModelRecommendation {
  recommendations: string[];
}

export interface DoeAiComparison {
  needs_review: boolean;
  max_difference: number;
  mean_difference: number;
  recommendation: string;
}

// v0.4.0 Experiment Verdict
export interface ExperimentVerdictResult {
  experiment_id: string;
  verdict: 'supports' | 'partially_supports' | 'does_not_support' | 'needs_remodel';
  prediction_error: number;
}

export interface NextExperimentSuggestion {
  suggestions: Array<{
    condition: Record<string, number>;
    rationale: string;
  }>;
}
```

- [ ] **Step 2: Add API functions**

Add after existing API functions:
```typescript
// v0.4.0 Version Chain
export async function getChainSummary(): Promise<ChainEntitySummary[]> {
  const result = await engineRequest('versioning/chain/summary', {});
  return result.summary || [];
}

export async function getChainTrace(entityId: string): Promise<ChainTrace> {
  return engineRequest('versioning/chain/trace', { entity_id: entityId });
}

export async function addChainLink(
  fromId: string, toId: string, relation: string,
  evidenceStatus = 'unverified', createdBy = '',
): Promise<{ success: boolean }> {
  return engineRequest('versioning/chain/link', {
    from_id: fromId, to_id: toId, relation, evidence_status: evidenceStatus, created_by: createdBy,
  });
}

// v0.4.0 Phase Gates
export async function getGateStatus(): Promise<Record<string, string>> {
  const result = await engineRequest('gates/status', {});
  return result.statuses || {};
}

export async function confirmGate(
  module: string, entityId: string, entityVersion: number,
  confirmedBy: string, comment = '',
): Promise<{ new_status: string }> {
  return engineRequest('gates/confirm', {
    module, entity_id: entityId, entity_version: entityVersion,
    confirmed_by: confirmedBy, comment,
  });
}

export async function resetGate(module: string, reason = ''): Promise<{ new_status: string }> {
  return engineRequest('gates/reset', { module, reason });
}

export async function getGateSummary(): Promise<{
  summary: Record<string, string>;
  all_confirmed: boolean;
  details: Record<string, any>;
}> {
  return engineRequest('gates/summary', { modules: [] });
}

// v0.4.0 Model Governance
export async function checkModelApplicability(
  datasetId: string, target: string, inputs: string[], isBinary = false,
): Promise<GovernanceCheckResult> {
  return engineRequest('modeling/governance/check', {
    dataset_id: datasetId, target, inputs, is_binary: isBinary,
  });
}

export async function recommendModels(
  nSamples: number, nFeatures: number, isBinaryTarget: boolean,
  hasNonlinearity: boolean, needInterpretability: boolean,
): Promise<ModelRecommendation> {
  return engineRequest('modeling/governance/recommend', {
    n_samples: nSamples, n_features: nFeatures,
    is_binary_target: isBinaryTarget, has_nonlinearity: hasNonlinearity,
    need_interpretability: needInterpretability,
  });
}

export async function compareDoeVsAi(
  doeR2: number, aiR2: number, aiPred: number[], doePred: number[], scale: number,
): Promise<DoeAiComparison> {
  return engineRequest('modeling/governance/doe_ai_compare', {
    doe_r2: doeR2, ai_r2: aiR2, ai_pred: aiPred, doe_pred: doePred, scale,
  });
}

// v0.4.0 Experiment Verdict
export async function recordExperimentWithVerdict(params: {
  experiment_id: string;
  model_id: string;
  planned_inputs: Record<string, number>;
  actual_inputs: Record<string, number>;
  predicted_output: number;
  actual_output: number;
  tolerance: number;
  operator: string;
  notes?: string;
}): Promise<ExperimentVerdictResult> {
  return engineRequest('experiment/record_with_verdict', params);
}

export async function suggestNextExperiment(modelId: string, nSuggestions = 3): Promise<NextExperimentSuggestion> {
  return engineRequest('experiment/suggest_next', { model_id: modelId, n_suggestions: nSuggestions });
}

// v0.4.0 Anomaly Source
export async function registerAnomalyEvent(params: {
  dataset_id: string;
  anomaly_id: string;
  source: string;
  confidence: number;
  user_confirmed: boolean;
  operator: string;
}): Promise<{ entity_id: string }> {
  return engineRequest('analysis/anomaly/register', params);
}
```

- [ ] **Step 3: Commit**

```bash
git add src/lib/engine.ts
git commit -m "feat(frontend): add v0.4.0 TypeScript types and API wrappers"
```

---

### Task F3: Add Analysis Phase Card to ProjectOverview

**Files:**
- Modify: `src/features/project/ProjectOverview.tsx`

- [ ] **Step 1: Add gate status display**

Import new functions:
```typescript
import { getGateSummary, confirmGate, resetGate, getChainSummary } from '@/lib/engine';
```

Add state:
```typescript
const [gateSummary, setGateSummary] = useState<Record<string, string>>({});
const [chainSummary, setChainSummary] = useState<any[]>([]);
const [loadingGates, setLoadingGates] = useState(false);
```

Add effect to load gates:
```typescript
useEffect(() => {
  getGateSummary().then(setGateSummary).catch(console.error);
  getChainSummary().then(setChainSummary).catch(console.error);
}, []);
```

Add card to render:
```tsx
<Card title={t('project.analysisPhaseTitle')} size="small">
  <Row gutter={[16, 16]}>
    {Object.entries(gateSummary).map(([module, status]) => (
      <Col key={module} span={8}>
        <Space>
          <span>{t(`gates.${module}`)}:</span>
          <Tag color={status === 'confirmed' ? 'green' : status === 'pending_confirmation' ? 'orange' : 'default'}>
            {status === 'confirmed' ? t('gates.confirmed') : status === 'pending_confirmation' ? t('gates.pending') : t('gates.notStarted')}
          </Tag>
        </Space>
      </Col>
    ))}
  </Row>
  <Divider />
  <Typography.Text type="secondary">
    {Object.values(gateSummary).filter(s => s === 'confirmed').length}/{Object.keys(gateSummary).length} {t('project.modulesConfirmed')}
  </Typography.Text>
</Card>
```

- [ ] **Step 2: Commit**

```bash
git add src/features/project/ProjectOverview.tsx
git commit -m "feat(project): add Analysis Phase status card"
```

---

### Task F4: Add i18n keys

**Files:**
- Modify: `src/i18n/en.json`, `zh-TW.json`, `es-MX.json`

- [ ] **Step 1: Add English keys**

Add to `en.json`:
```json
{
  "gates": {
    "dataImport": "Data Import",
    "processDefine": "Process Definition",
    "modeling": "Model Center",
    "spc": "SPC Control",
    "monteCarlo": "Monte Carlo",
    "prediction": "Prediction",
    "validation": "Validation Lab",
    "confirmed": "Confirmed",
    "pending": "Pending",
    "notStarted": "Not Started"
  },
  "project": {
    "analysisPhaseTitle": "Analysis Phase Status",
    "modulesConfirmed": "modules confirmed"
  },
  "evidence": {
    "chainTrace": "Version Chain Trace",
    "sourceLabels": "Source Labels",
    "extrapolationWarning": "Extrapolation Warnings",
    "evidenceSummary": "Evidence Summary"
  },
  "governance": {
    "checkApplicability": "Check Model Applicability",
    "recommendModels": "Recommend Models",
    "compareDoeVsAi": "Compare DOE vs AI",
    "smallSampleWarning": "Insufficient samples for tree models",
    "classImbalanceWarning": "Class imbalance detected",
    "multicollinearityWarning": "Multicollinearity detected"
  },
  "experiment": {
    "verdict": "Verdict",
    "supports": "Supports Model",
    "partiallySupports": "Partially Supports",
    "doesNotSupport": "Does Not Support",
    "needsRemodel": "Needs Remodeling",
    "nextSuggestions": "Next Experiment Suggestions"
  },
  "chain": {
    "entityType": "Entity Type",
    "version": "Version",
    "evidenceStatus": "Evidence Status",
    "createdBy": "Created By",
    "createdAt": "Created At",
    "links": "Links",
    "claims": "Claims"
  }
}
```

- [ ] **Step 2: Add zh-TW and es-MX translations**

Mirror the English structure with translated values.

- [ ] **Step 3: Commit**

```bash
git add src/i18n/en.json src/i18n/zh-TW.json src/i18n/es-MX.json
git commit -m "feat(i18n): add v0.4.0 evidence chain, governance, and gate keys"
```

---

## Final Integration & Validation

### Task F5: Run full test suite

- [ ] **Step 1: Run all tests**

```bash
cd engine && python -m pytest tests/ -q
```
Expected: All tests PASS (345 existing + ~47 new = 392 total)

- [ ] **Step 2: Run TypeScript check**

```bash
npx tsc --noEmit
```
Expected: EXIT 0

- [ ] **Step 3: Run build**

```bash
npm run build
```
Expected: Built successfully

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: v0.4.0 trustworthy analysis chain complete"
git push
```

---

## Summary

| Phase | Tasks | Files Created | Files Modified | Tests Added |
|---|---|---|---|---|
| A: Version Chain | A1-A3 | 3 | 2 | 9 |
| B: Phase Gates | B1 | 2 | 1 | 6 |
| C: Report Evidence | C1-C2 | 0 | 2 | 0 |
| D: Model Governance | D1 | 1 | 1 | 6 |
| E: Anomaly Tracking | E1 | 0 | 2 | 0 |
| F: Experiment Loop | F1 | 0 | 1 | 4 |
| Frontend | F2-F4 | 0 | 3 | 0 |
| Validation | F5 | 0 | 0 | 0 |
| **Total** | **15 tasks** | **6 new** | **11 modified** | **~47 new** |
