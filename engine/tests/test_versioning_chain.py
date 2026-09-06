import pytest
import tempfile
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
    assert summary == sorted(summary, key=lambda x: (x["entity_type"], x["version"]))


def test_persist_and_reload():
    chain_dir = tempfile.mkdtemp()
    chain = VersionChain(chain_dir, "user1")
    id1 = chain.register_entity("dataset", "proj-001", {"a": 1}, "user1")
    chain.add_link(id1, id1, "uses_dataset", "unverified", "user1")
    chain.save()
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
    assert len(trace["incoming_links"]) == 1
    assert trace["incoming_links"][0]["from_id"] == md


def test_handle_data_import_registers_dataset():
    """Verify data/import handler registers dataset in version chain."""
    import tempfile
    import pathlib
    tmp = tempfile.mkdtemp()
    csv = pathlib.Path(tmp) / "test.csv"
    csv.write_text("x,y\n1,2\n3,4\n5,6\n")
    from process_intelligence_engine.main import _VERSION_CHAIN, _handle_import
    result = _handle_import({"file_path": str(csv)})
    dataset_id = result["dataset_id"]
    summary = _VERSION_CHAIN.get_chain_summary()
    assert any(e["entity_type"] == "dataset" for e in summary)
    assert result.get("chain_entity_id", "").startswith("ds-")
