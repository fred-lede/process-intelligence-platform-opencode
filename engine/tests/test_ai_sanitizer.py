import pytest

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


def test_bucketed_policy_uses_deterministic_ten_unit_range():
    preview = sanitize_context({"temperature": 150.2}, {}, "bucketed")

    assert preview.payload["temperature"] == "150-160"


def test_standardized_policy_rejects_missing_or_zero_parameters():
    with pytest.raises(ValueError, match="nonzero mean and standard deviation"):
        sanitize_context({"temperature": 150.2}, {}, "standardized")

    with pytest.raises(ValueError, match="nonzero mean and standard deviation"):
        sanitize_context(
            {"temperature": 150.2},
            {"temperature.mean": "100", "temperature.std": "0"},
            "standardized",
        )


@pytest.mark.parametrize(
    ("mean", "standard_deviation"),
    [
        ("nan", "10"),
        ("inf", "10"),
        ("-inf", "10"),
        ("100", "nan"),
        ("100", "inf"),
        ("100", "-inf"),
        ("100", "-10"),
    ],
)
def test_standardized_policy_rejects_nonfinite_or_nonpositive_parameters(
    mean, standard_deviation
):
    with pytest.raises(ValueError, match="nonzero mean and standard deviation"):
        sanitize_context(
            {"temperature": 150.2},
            {"temperature.mean": mean, "temperature.std": standard_deviation},
            "standardized",
        )


def test_standardized_policy_uses_explicit_nonzero_parameters():
    preview = sanitize_context(
        {"temperature": 150.0},
        {"temperature.mean": "100", "temperature.std": "10"},
        "standardized",
    )

    assert preview.payload["temperature"] == 5.0


def test_sanitizer_masks_identifier_keys_recursively():
    preview = sanitize_context(
        {"batch": {"operator": "Ada"}, "history": [{"serial": "SN-1"}]}, {}
    )

    assert preview.payload == {
        "batch": {"operator": "MASKED"},
        "history": [{"serial": "MASKED"}],
    }
    assert preview.masked_fields == ["batch.operator", "history[0].serial"]
