"""Project manifest: on-disk filesystem structure (spec 11A).

Manages the project root directory, source data directories, process groups,
process nodes, and a persistent project manifest JSON file.

Directory structure:
    <project_root>/
    ├─ source_data/              # read-only raw input
    │  ├─ <process-group-1>/
    │  ├─ <process-group-2>/
    ├─ registry/                 # dataset / field / source registration
    ├─ curated_data/             # standardized data (does not modify originals)
    ├─ analysis_data/            # distribution, time features, model datasets
    ├─ models/                   # immutable DOE / AI / Hybrid model versions
    ├─ simulations/              # Monte Carlo settings and results
    ├─ experiments/              # validation experiment plans and results
    ├─ reports/                  # drafts and approved reports
    ├─ audit/                    # audit and cloud upload records
    └─ project_manifest.json     # project settings and version index
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

ManifestVersion = Literal["1.0.0"]

_DIR_TEMPLATES = {
    "source_data": "source_data",
    "registry": "registry",
    "curated_data": "curated_data",
    "analysis_data": "analysis_data",
    "models": "models",
    "simulations": "simulations",
    "experiments": "experiments",
    "reports": "reports",
    "audit": "audit",
}

_PROCESS_GROUP_TEMPLATES = [
    {"name": "SMT", "description": "Surface Mount Technology"},
    {"name": "PressFit", "description": "Press-Fit assembly"},
    {"name": "FATP", "description": "Final Assembly Test and Pack"},
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DatasetRegistration:
    dataset_id: str
    source_path: str
    source_file: str
    format: str  # xlsx | xls | csv | parquet
    row_count: int
    column_count: int
    time_range: dict[str, str] | None = None
    partition_keys: list[str] = field(default_factory=list)
    schema_version: str = "1.0.0"
    checksum: str = ""
    quality_status: str = "unknown"  # unknown | good | degraded | poor
    sensitive_columns: list[str] = field(default_factory=list)
    cloud_transfer_policy: str = "off"  # off | preview | approved
    registered_at: str = ""
    curated_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items()}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DatasetRegistration":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class ProcessGroup:
    process_group_id: str
    display_name: str
    directory_name: str
    description: str
    input_templates: list[str] = field(default_factory=list)
    output_templates: list[str] = field(default_factory=list)
    quality_label_templates: list[str] = field(default_factory=list)
    unit_profile: dict[str, str] = field(default_factory=dict)
    active: bool = True
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items()}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ProcessGroup":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class ProcessNode:
    process_node_id: str
    display_name: str
    node_type: str  # e.g. "laser_marking", "smt_printer", "reflow", "aoi", ...
    sequence_or_edges: list[dict[str, str]] = field(default_factory=list)
    input_data_sources: list[str] = field(default_factory=list)
    output_data_sources: list[str] = field(default_factory=list)
    in_control_parameters: list[str] = field(default_factory=list)
    out_quality_outputs: list[str] = field(default_factory=list)
    machine_mapping: list[str] = field(default_factory=list)
    rework_policy: str = "default"  # default | rework | scrap | hold
    x: float = 0.0
    y: float = 0.0
    active: bool = True
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items()}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ProcessNode":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class ProjectManifest:
    project_id: str
    project_name: str
    operator: str
    version: ManifestVersion
    created_at: str
    updated_at: str
    project_root: str  # absolute path to project root
    source_data_dirs: list[str] = field(default_factory=list)
    process_groups: list[ProcessGroup] = field(default_factory=list)
    process_nodes: list[ProcessNode] = field(default_factory=list)
    datasets: list[DatasetRegistration] = field(default_factory=list)
    models: list[dict[str, Any]] = field(default_factory=list)
    simulations: list[dict[str, Any]] = field(default_factory=list)
    experiments: list[dict[str, Any]] = field(default_factory=list)
    reports: list[dict[str, Any]] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items()}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ProjectManifest":
        obj = cls(**{
            k: v for k, v in d.items()
            if k in cls.__dataclass_fields__
        })
        # Re-construct nested dataclasses
        obj.process_groups = [
            ProcessGroup.from_dict(g) for g in d.get("process_groups", [])
        ]
        obj.process_nodes = [
            ProcessNode.from_dict(n) for n in d.get("process_nodes", [])
        ]
        obj.datasets = [
            DatasetRegistration.from_dict(ds) for ds in d.get("datasets", [])
        ]
        return obj


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ProjectEngine:
    """On-disk project manifest management."""

    def __init__(self, project_root: str | None = None) -> None:
        self._root = Path(project_root or "").resolve()
        self._manifest: ProjectManifest | None = None
        self._manifest_path = self._root / "project_manifest.json" if project_root else Path()

    # -- helpers ------------------------------------------------------------

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _checksum_file(self, path: str) -> str:
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
        except OSError:
            pass
        return h.hexdigest()

    def _ensure_dirs(self) -> None:
        if not self._root:
            return
        for dirname in _DIR_TEMPLATES.values():
            (self._root / dirname).mkdir(parents=True, exist_ok=True)

    def _ensure_project(self) -> None:
        """Auto-create a default project if none exists."""
        import tempfile
        if not self._root or not self._manifest:
            tmp = Path(tempfile.gettempdir()) / "process_intelligence_platform"
            tmp.mkdir(parents=True, exist_ok=True)
            self._root = tmp
            self._manifest_path = self._root / "project_manifest.json"
            self._manifest = None
            self._load()
            self._ensure_dirs()

    def _load(self) -> ProjectManifest:
        if self._manifest is not None:
            return self._manifest
        if self._manifest_path.exists():
            with open(self._manifest_path, "r", encoding="utf-8") as f:
                self._manifest = ProjectManifest.from_dict(json.load(f))
        else:
            self._manifest = ProjectManifest(
                project_id=str(uuid.uuid4()),
                project_name="Untitled",
                operator="anonymous",
                version="1.0.0",
                created_at=self._now(),
                updated_at=self._now(),
                project_root=str(self._root),
            )
        return self._manifest

    def _save(self) -> None:
        if self._manifest is None or not self._manifest_path.parent.exists():
            return
        self._manifest.updated_at = self._now()
        with open(self._manifest_path, "w", encoding="utf-8") as f:
            json.dump(self._manifest.to_dict(), f, indent=2, ensure_ascii=False)

    # -- project root -------------------------------------------------------

    def create_project(self, root: str, name: str = "Untitled", operator: str = "anonymous") -> dict:
        self._root = Path(root).resolve()
        self._manifest = None
        self._manifest_path = self._root / "project_manifest.json"
        self._ensure_dirs()
        manifest = self._load()
        manifest.project_name = name
        manifest.operator = operator
        self._save()
        return {
            "project_id": manifest.project_id,
            "project_name": manifest.project_name,
            "project_root": str(self._root),
            "created_at": manifest.created_at,
        }

    def open_project(self, root: str) -> dict:
        self._root = Path(root).resolve()
        self._manifest = None
        self._manifest_path = self._root / "project_manifest.json"
        if not self._manifest_path.exists():
            raise FileNotFoundError(f"project_manifest.json not found in {root}")
        manifest = self._load()
        return {
            "project_id": manifest.project_id,
            "project_name": manifest.project_name,
            "project_root": str(self._root),
            "datasets": len(manifest.datasets),
            "process_groups": len(manifest.process_groups),
        }

    def get_manifest(self) -> dict:
        self._ensure_project()
        manifest = self._load()
        return {
            "project_id": manifest.project_id,
            "project_name": manifest.project_name,
            "project_root": str(self._root),
            "version": manifest.version,
            "created_at": manifest.created_at,
            "updated_at": manifest.updated_at,
            "source_data_dirs": manifest.source_data_dirs,
            "process_groups": [g.to_dict() for g in manifest.process_groups],
            "process_nodes": [n.to_dict() for n in manifest.process_nodes],
            "dataset_count": len(manifest.datasets),
            "model_count": len(manifest.models),
            "settings": manifest.settings,
        }

    def update_settings(self, updates: dict[str, Any]) -> dict:
        self._ensure_project()
        manifest = self._load()
        manifest.settings.update(updates)
        self._save()
        return manifest.settings

    # -- source data directories --------------------------------------------

    def add_source_dir(self, directory_name: str, absolute_path: str) -> dict:
        manifest = self._load()
        source_dir = manifest.source_data_dirs
        if absolute_path in source_dir:
            return {"added": False, "reason": "already registered"}
        source_dir.append(absolute_path)
        # Create subdirectory under source_data/
        target = self._root / "source_data" / directory_name
        target.mkdir(parents=True, exist_ok=True)
        manifest.source_data_dirs = source_dir
        self._save()
        return {"added": True, "path": absolute_path, "target": str(target)}

    def list_source_dirs(self) -> list[dict]:
        self._ensure_project()
        manifest = self._load()
        result = []
        for d in manifest.source_data_dirs:
            p = Path(d)
            result.append({
                "path": d,
                "name": p.name,
                "exists": p.exists(),
                "file_count": len([f for f in p.rglob("*") if f.is_file()]) if p.exists() else 0,
            })
        return result

    def scan_source_dir(self, directory_path: str) -> list[dict]:
        """Scan a source directory for supported files."""
        p = Path(directory_path)
        if not p.exists():
            return []
        supported_exts = {".xlsx", ".xls", ".csv", ".parquet"}
        files = []
        for fp in sorted(p.rglob("*")):
            if fp.is_file() and fp.suffix.lower() in supported_exts:
                files.append({
                    "path": str(fp),
                    "name": fp.name,
                    "size_bytes": fp.stat().st_size,
                    "format": fp.suffix.lower().lstrip("."),
                })
        return files

    # -- process groups -----------------------------------------------------

    def list_process_group_templates(self) -> list[dict]:
        return _PROCESS_GROUP_TEMPLATES

    def create_process_group(self, display_name: str, directory_name: str,
                             description: str = "",
                             input_templates: list[str] | None = None,
                             output_templates: list[str] | None = None,
                             quality_label_templates: list[str] | None = None,
                             unit_profile: dict[str, str] | None = None) -> dict:
        self._ensure_project()
        manifest = self._load()
        pg = ProcessGroup(
            process_group_id=str(uuid.uuid4()),
            display_name=display_name,
            directory_name=directory_name,
            description=description,
            input_templates=input_templates or [],
            output_templates=output_templates or [],
            quality_label_templates=quality_label_templates or [],
            unit_profile=unit_profile or {},
            active=True,
            created_at=self._now(),
        )
        manifest.process_groups.append(pg)
        self._save()
        return pg.to_dict()

    def update_process_group(self, group_id: str, updates: dict[str, Any]) -> dict:
        self._ensure_project()
        manifest = self._load()
        for g in manifest.process_groups:
            if g.process_group_id == group_id:
                for k, v in updates.items():
                    if hasattr(g, k):
                        setattr(g, k, v)
                self._save()
                return g.to_dict()
        raise ValueError(f"Process group not found: {group_id}")

    def delete_process_group(self, group_id: str) -> bool:
        self._ensure_project()
        manifest = self._load()
        before = len(manifest.process_groups)
        manifest.process_groups = [
            g for g in manifest.process_groups if g.process_group_id != group_id
        ]
        if len(manifest.process_groups) == before:
            return False
        self._save()
        return True

    # -- process nodes ------------------------------------------------------

    def create_process_node(self, display_name: str, node_type: str,
                            sequence_or_edges: list[dict] | None = None,
                            input_data_sources: list[str] | None = None,
                            rework_policy: str = "default",
                            x: float = 0.0, y: float = 0.0) -> dict:
        self._ensure_project()
        manifest = self._load()
        node = ProcessNode(
            process_node_id=str(uuid.uuid4()),
            display_name=display_name,
            node_type=node_type,
            sequence_or_edges=sequence_or_edges or [],
            input_data_sources=input_data_sources or [],
            rework_policy=rework_policy,
            x=x, y=y,
            active=True,
            created_at=self._now(),
        )
        manifest.process_nodes.append(node)
        self._save()
        return node.to_dict()

    def update_process_node(self, node_id: str, updates: dict[str, Any]) -> dict:
        self._ensure_project()
        manifest = self._load()
        for n in manifest.process_nodes:
            if n.process_node_id == node_id:
                for k, v in updates.items():
                    if hasattr(n, k):
                        setattr(n, k, v)
                self._save()
                return n.to_dict()
        raise ValueError(f"Process node not found: {node_id}")

    def delete_process_node(self, node_id: str) -> bool:
        self._ensure_project()
        manifest = self._load()
        before = len(manifest.process_nodes)
        manifest.process_nodes = [
            n for n in manifest.process_nodes if n.process_node_id != node_id
        ]
        if len(manifest.process_nodes) == before:
            return False
        self._save()
        return True

    # -- dataset registration (on-disk) -------------------------------------

    def register_dataset(self, source_path: str, dataset_id: str | None = None,
                         format: str = "csv", row_count: int = 0,
                         column_count: int = 0,
                         partition_keys: list[str] | None = None,
                         time_range: dict[str, str] | None = None,
                         quality_status: str = "unknown") -> dict:
        manifest = self._load()
        checksum = self._checksum_file(source_path)
        ds = DatasetRegistration(
            dataset_id=dataset_id or str(uuid.uuid4()),
            source_path=source_path,
            source_file=Path(source_path).name,
            format=format,
            row_count=row_count,
            column_count=column_count,
            time_range=time_range,
            partition_keys=partition_keys or [],
            checksum=checksum,
            quality_status=quality_status,
            registered_at=self._now(),
        )
        manifest.datasets.append(ds)
        self._save()
        return ds.to_dict()

    def list_datasets(self) -> list[dict]:
        self._ensure_project()
        manifest = self._load()
        return [ds.to_dict() for ds in manifest.datasets]

    def get_dataset(self, dataset_id: str) -> dict | None:
        manifest = self._load()
        for ds in manifest.datasets:
            if ds.dataset_id == dataset_id:
                return ds.to_dict()
        return None

    def update_dataset(self, dataset_id: str, updates: dict[str, Any]) -> dict | None:
        manifest = self._load()
        for ds in manifest.datasets:
            if ds.dataset_id == dataset_id:
                for k, v in updates.items():
                    if hasattr(ds, k):
                        setattr(ds, k, v)
                self._save()
                return ds.to_dict()
        return None

    # -- project data directories (get paths) -------------------------------

    def get_directories(self) -> dict[str, str]:
        self._ensure_dirs()
        return {name: str(self._root / path) for name, path in _DIR_TEMPLATES.items()}

    # -- process flow graph validation --------------------------------------

    def get_flow_graph(self) -> dict[str, Any]:
        self._ensure_project()
        manifest = self._load()
        nodes = [n.to_dict() for n in manifest.process_nodes]
        # Extract edges from all nodes
        edges: list[dict[str, Any]] = []
        node_ids = {n["process_node_id"] for n in nodes}
        for n in nodes:
            for edge in n.get("sequence_or_edges", []):
                target = edge.get("to", "")
                if target in node_ids:
                    edges.append({
                        "from": n["process_node_id"],
                        "to": target,
                        "condition": edge.get("condition", ""),
                    })
        return {"nodes": nodes, "edges": edges}

    def validate_flow_graph(self) -> dict[str, Any]:
        self._ensure_project()
        manifest = self._load()
        nodes = manifest.process_nodes
        warnings: list[str] = []
        errors: list[str] = []

        if len(nodes) == 0:
            warnings.append("No process nodes defined.")
            return {"warnings": warnings, "errors": errors, "valid": len(errors) == 0}

        node_ids = {n.process_node_id for n in nodes}
        node_types: dict[str, str] = {n.process_node_id: n.node_type for n in nodes}
        has_cycle = False

        # Check for orphan nodes (no incoming or outgoing edges)
        connected: set[str] = set()
        for n in nodes:
            for edge in n.sequence_or_edges:
                connected.add(n.process_node_id)
                connected.add(edge.get("to", ""))
        for n in nodes:
            if n.process_node_id not in connected:
                warnings.append(
                    f"Node '{n.display_name}' is disconnected (no edges)."
                )

        # Check for duplicate node types (same node_type used multiple times)
        type_counts: dict[str, int] = {}
        for n in nodes:
            type_counts[n.node_type] = type_counts.get(n.node_type, 0) + 1
        for n in nodes:
            if type_counts[n.node_type] > 1:
                warnings.append(
                    f"Node type '{n.node_type}' is used by multiple nodes."
                )

        # Check for cycles (DFS)
        adjacency: dict[str, list[str]] = {n.process_node_id: [] for n in nodes}
        for n in nodes:
            for edge in n.sequence_or_edges:
                target = edge.get("to", "")
                if target in node_ids:
                    adjacency[n.process_node_id].append(target)

        visited: set[str] = set()
        rec_stack: set[str] = set()

        def _dfs(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)
            for neighbour in adjacency.get(node_id, []):
                if neighbour not in visited:
                    if _dfs(neighbour):
                        return True
                elif neighbour in rec_stack:
                    return True
            rec_stack.discard(node_id)
            return False

        for n in nodes:
            if n.process_node_id not in visited:
                if _dfs(n.process_node_id):
                    has_cycle = True
                    break

        if has_cycle:
            errors.append("Cycle detected in process flow graph. Please remove circular edges.")

        return {
            "warnings": warnings,
            "errors": errors,
            "valid": len(errors) == 0,
            "node_count": len(nodes),
            "edge_count": sum(len(v) for v in adjacency.values()),
        }
