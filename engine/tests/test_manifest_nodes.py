import tempfile, os
from process_intelligence_engine.project.manifest import ProjectEngine

def _engine():
    root = tempfile.mkdtemp()
    eng = ProjectEngine()
    eng.create_project(root, name="Test", operator="t")
    return eng

def test_node_has_x_y_defaults():
    eng = _engine()
    node = eng.create_process_node("A", "aoi")
    assert node["x"] == 0.0
    assert node["y"] == 0.0

def test_node_create_accepts_x_y():
    eng = _engine()
    node = eng.create_process_node("A", "aoi", x=100.0, y=-50.0)
    assert node["x"] == 100.0
    assert node["y"] == -50.0

def test_node_update_x_y_persists():
    eng = _engine()
    node = eng.create_process_node("A", "aoi")
    nid = node["process_node_id"]
    updated = eng.update_process_node(nid, {"x": 200.0, "y": 80.0})
    assert updated["x"] == 200.0
    assert updated["y"] == 80.0

def test_from_dict_old_data_without_x_y_defaults_zero():
    from process_intelligence_engine.project.manifest import ProcessNode
    n = ProcessNode.from_dict({"process_node_id": "1", "display_name": "A", "node_type": "aoi"})
    assert n.x == 0.0
    assert n.y == 0.0
