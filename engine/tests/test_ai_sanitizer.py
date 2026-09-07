from process_intelligence_engine.ai.sanitizer import sanitize_context


def test_sanitizer_masks_identifiers_and_keeps_numbers_raw():
    preview = sanitize_context(
        {"operator": "Ada", "station": "Line-A", "temperature": 150.2}, {}
    )

    assert preview.payload["operator"] == "MASKED"
    assert preview.payload["station"] == "MASKED"
    assert preview.payload["temperature"] == 150.2


def test_bucketed_policy_removes_exact_value():
    preview = sanitize_context({"temperature": 150.2}, {}, "bucketed")

    assert preview.payload["temperature"] != 150.2
