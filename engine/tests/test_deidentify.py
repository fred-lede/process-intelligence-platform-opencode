"""Tests for cloud upload de-identification strategy overrides."""
import pandas as pd

from process_intelligence_engine.data.deidentify import (
    _DEID_ENGINE as deid,
    apply_deidentification,
)


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "temperature": [230.5, 241.0, 255.2],
            "operator": ["Alice", "Bob", "Carol"],
            "ok_flag": ["OK", "NG", "OK"],
        }
    )


def test_strategy_overrides_mask_with_hash():
    df = _sample_df()
    preview = deid.generate_preview(
        df,
        "ds1",
        sensitive_columns=["operator"],
        strategy_overrides={"operator": "hash"},
    )
    assert preview.mask_strategies["operator"] == "hash"
    out = apply_deidentification(df, preview)
    # hash strategy produces 8-char hex strings
    for val in out["operator"]:
        assert len(val) == 8
        assert all(c in "0123456789abcdef" for c in val)


def test_strategy_overrides_mask_with_masked():
    df = _sample_df()
    preview = deid.generate_preview(
        df,
        "ds1",
        sensitive_columns=["temperature"],
        strategy_overrides={"temperature": "masked"},
    )
    assert preview.mask_strategies["temperature"] == "masked"
    out = apply_deidentification(df, preview)
    assert (out["temperature"] == "MASKED").all()


def test_strategy_overrides_noise_on_numeric_transmitted():
    df = _sample_df()
    preview = deid.generate_preview(
        df,
        "ds1",
        strategy_overrides={"temperature": "noise"},
        noise_std=0.5,
    )
    assert preview.noise_config["temperature"]["method"] == "gaussian"
    assert preview.noise_config["temperature"]["std"] == 0.5
    out = apply_deidentification(df, preview, seed=7)
    assert pd.api.types.is_float_dtype(out["temperature"])


def test_noise_on_non_numeric_is_ignored():
    df = _sample_df()
    preview = deid.generate_preview(
        df,
        "ds1",
        sensitive_columns=["operator"],
        strategy_overrides={"operator": "noise"},
    )
    assert preview.mask_strategies["operator"] == "hash"
    assert "operator" not in preview.noise_config


def test_noise_masked_column_gets_noise():
    df = _sample_df()
    preview = deid.generate_preview(
        df,
        "ds1",
        sensitive_columns=["temperature"],
        strategy_overrides={"temperature": "noise"},
        noise_std=0.5,
    )
    out = apply_deidentification(df, preview, seed=3)
    # column present, numeric, and differs from original (noise applied)
    assert "temperature" in out.columns
    assert pd.api.types.is_float_dtype(out["temperature"])
    assert (out["temperature"] != df["temperature"]).any()
