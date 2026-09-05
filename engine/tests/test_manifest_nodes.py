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

def test_node_data_mapping_fields_update():
    eng = _engine()
    node = eng.create_process_node("A", "aoi")
    nid = node["process_node_id"]
    updated = eng.update_process_node(nid, {
        "input_data_sources": ["ds1", "ds2"],
        "output_data_sources": ["ds3"],
        "in_control_parameters": ["temp", "speed"],
        "out_quality_outputs": ["width", "height"],
        "machine_mapping": ["M1"],
    })
    assert updated["input_data_sources"] == ["ds1", "ds2"]
    assert updated["output_data_sources"] == ["ds3"]
    assert updated["in_control_parameters"] == ["temp", "speed"]
    assert updated["out_quality_outputs"] == ["width", "height"]
    assert updated["machine_mapping"] == ["M1"]

def test_manifest_association_keys_default_empty():
    eng = _engine()
    g = eng.get_flow_graph()
    assert "association_keys" in g
    assert g["association_keys"] == []

def test_manifest_set_association_keys_persists():
    eng = _engine()
    eng.set_association_keys(["barcode", "serial_no", "batch_no"])
    g = eng.get_flow_graph()
    assert g["association_keys"] == ["barcode", "serial_no", "batch_no"]

def test_manifest_association_keys_survive_reload():
    import json
    eng = _engine()
    eng.set_association_keys(["work_order"])
    # 重載 manifest 物件
    from process_intelligence_engine.project.manifest import ProjectManifest
    with open(eng._manifest_path, "r", encoding="utf-8") as f:
        d = json.load(f)
    m2 = ProjectManifest.from_dict(d)
    assert m2.association_keys == ["work_order"]
