import pytest

from process_intelligence_engine.data.field_detector import (
    DetectedField,
    FieldRole,
    detect_fields,
)


def _mk_simple_series_factory():
    """Build fake column data as list of lists (rows) for detection."""


def _detect(name: str, values: list):
    """Helper: build a fake single-column dataset and detect."""
    # Pass through: we give detection the column name + values directly.
    return detect_fields([{"name": name, "values": values}])[0]


def test_temperature_column_detected_as_numeric_input():
    field = _detect("temperature", ["230.1", "241.3", "255.0", "238.9"])
    assert field.role == FieldRole.INPUT
    assert field.data_type == "continuous"
    assert field.confidence >= 0.5


def test_ok_flag_column_detected_as_quality_label():
    field = _detect("ok_flag", ["OK", "NG", "OK", "NG"])
    assert field.role == FieldRole.QUALITY_LABEL


def test_barcode_column_detected_as_identifier():
    field = _detect("barcode", ["AAA001", "AAA002", "AAA003"])
    assert field.role == FieldRole.IDENTIFIER
    assert field.data_type == "text"


def test_serial_number_detected_as_identifier():
    field = _detect("serial_no", ["SN-10293", "SN-10294"])
    assert field.role == FieldRole.IDENTIFIER


def test_binary_ng_column_detected_as_quality():
    field = _detect("NG", ["1", "0", "0", "1", "0"])
    assert field.role == FieldRole.QUALITY_LABEL


def test_timestamp_column_detected_as_timestamp():
    field = _detect("date_time", ["2026-09-01 10:30:00", "2026-09-01 10:31:00"])
    assert field.role == FieldRole.TIMESTAMP


def test_category_column_detected():
    field = _detect("machine", ["line1", "line2", "line1", "line3"])
    assert field.role == FieldRole.CATEGORY


def test_operator_column_detected_as_metadata():
    field = _detect("operator", ["john", "mary"])
    assert field.role == FieldRole.METADATA


def test_material_batch_with_sensitive_words():
    # "材料批號" style sensitive identifier
    field = _detect("material_lot", ["LOT-01", "LOT-02"])
    assert field.role == FieldRole.IDENTIFIER


def test_each_field_has_detection_reason():
    field = _detect("temperature", ["230.1", "241.3", "255.0"])
    assert isinstance(field.reason, list)
    assert len(field.reason) > 0


def test_unknown_column_falls_back_to_metadata():
    field = _detect("foo_xyz", ["a", "b", "c"])
    # Low-confidence fallback; role should be something safe (metadata)
    assert field.confidence < 0.5
    assert field.role in {FieldRole.METADATA, FieldRole.INPUT}


def test_multiple_columns_preserve_order():
    fields = detect_fields(
        [
            {"name": "barcode", "values": ["A", "B"]},
            {"name": "temperature", "values": ["1.0", "2.0"]},
        ]
    )
    assert [f.name for f in fields] == ["barcode", "temperature"]
    assert isinstance(fields[0], DetectedField)