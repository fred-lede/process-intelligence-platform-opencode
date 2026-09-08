import pandas as pd
import pytest

from process_intelligence_engine.data.grain import DataFilter, apply_grain_filter


def test_filter_returns_copy_without_mutating_source():
    source = pd.DataFrame({"lot_id": ["L1", "L2"], "value": [1, 2]})
    result = apply_grain_filter(source, [DataFilter("lot_id", "L1")])
    assert result["value"].tolist() == [1]
    assert len(source) == 2


def test_unknown_field_is_rejected():
    with pytest.raises(ValueError, match="Unsupported grain field"):
        apply_grain_filter(pd.DataFrame({"lot_id": ["L1"]}), [DataFilter("carrier_id", "C1")])


def test_missing_supported_field_is_rejected():
    with pytest.raises(ValueError, match="Grain field not found"):
        apply_grain_filter(pd.DataFrame({"value": [1]}), [DataFilter("lot_id", "L1")])
