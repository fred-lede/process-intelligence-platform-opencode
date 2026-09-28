"""Tests for cloud upload de-identification.

These assert *protective properties* rather than output formatting. The
previous suite pinned the weak behaviour (an 8-character digest), so it would
have failed the moment the masking was actually strengthened — the opposite of
what a security test should do.
"""
from hashlib import sha256

import numpy as np
import pandas as pd
import pytest

from process_intelligence_engine.data.deidentify import (
    _DEID_ENGINE as deid,
    PSEUDONYM_HEX_CHARS,
    PSEUDONYM_KEY_ENV,
    Pseudonymiser,
    apply_deidentification,
    canonical_frame_hash,
)


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "temperature": [230.5, 241.0, 255.2],
            "operator": ["Alice", "Bob", "Carol"],
            "ok_flag": ["OK", "NG", "OK"],
        }
    )


# ------------------------------------------------------------- pseudonymiser

def test_pseudonym_is_keyed_not_a_truncated_plain_hash():
    key = b"0123456789abcdef"
    token = Pseudonymiser(key=key).token("Alice")
    bare_hash = sha256(b"Alice").hexdigest()[:8]

    assert token != bare_hash
    assert token != sha256(b"Alice").hexdigest()
    # 32 hex chars = 128 bits; 8 chars (32 bits) is enumerable for the
    # low-cardinality identifiers this module targets.
    assert len(token) == PSEUDONYM_HEX_CHARS == 32


def test_pseudonyms_differ_between_keys():
    a = Pseudonymiser(key=b"aaaaaaaaaaaaaaaa").token("Alice")
    b = Pseudonymiser(key=b"bbbbbbbbbbbbbbbb").token("Alice")
    assert a != b


def test_pseudonyms_are_stable_for_the_same_key():
    key = b"0123456789abcdef"
    assert Pseudonymiser(key=key).token("Alice") == Pseudonymiser(key=key).token("Alice")
    assert Pseudonymiser(key=key).token("Alice") != Pseudonymiser(key=key).token("Bob")


def test_pseudonyms_are_stable_across_instances_via_the_project_key_file(tmp_path):
    first = Pseudonymiser(project_root=tmp_path)
    second = Pseudonymiser(project_root=tmp_path)
    assert first.stable and second.stable
    assert first.token("Alice") == second.token("Alice")
    assert first.key_id == second.key_id
    assert (tmp_path / ".pseudonym_key").is_file()


def test_short_keys_are_rejected():
    with pytest.raises(ValueError, match="at least 16 bytes"):
        Pseudonymiser(key=b"tooshort")


def test_malformed_key_from_the_environment_is_rejected(monkeypatch):
    monkeypatch.setenv(PSEUDONYM_KEY_ENV, "not-a-hex-key")
    with pytest.raises(ValueError, match="hex"):
        Pseudonymiser()


def test_missing_key_reports_that_pseudonyms_are_not_stable():
    ephemeral = Pseudonymiser()
    assert ephemeral.stable is False


# ------------------------------------------------------------------- masking

def test_pseudonymised_columns_do_not_leak_the_original_values():
    df = _sample_df()
    preview = deid.generate_preview(
        df, "ds1", sensitive_columns=["operator"], strategy_overrides={"operator": "hash"},
    )
    out = apply_deidentification(df, preview)
    assert not set(out["operator"]) & set(df["operator"])
    for value in df["operator"]:
        assert value not in "".join(out["operator"].astype(str))


def test_excluded_columns_are_absent_from_the_payload():
    df = _sample_df()
    preview = deid.generate_preview(df, "ds1", excluded_columns=["operator"])
    out = apply_deidentification(df, preview)
    assert "operator" not in out.columns
    assert "operator" not in preview.transmitted_columns


def test_duplicate_column_names_are_rejected():
    # df[col] would return a DataFrame for a duplicated name, silently turning
    # the masking step into a no-op.
    df = pd.DataFrame(
        np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]),
        columns=["temperature", "temperature", "yield"],
    )
    with pytest.raises(ValueError, match="duplicate column name"):
        deid.generate_preview(df, "ds1", sensitive_columns=["temperature"])


def test_nullable_string_columns_are_pseudonymised_not_dropped():
    # Regression: `dtype in ("object", "string")` is False for pd.StringDtype(),
    # so such columns silently fell through to a constant replacement.
    df = _sample_df()
    df["operator"] = df["operator"].astype("string")
    preview = deid.generate_preview(df, "ds1", sensitive_columns=["operator"])
    assert preview.mask_strategies["operator"] == "hash"
    out = apply_deidentification(df, preview)
    assert out["operator"].nunique() == 3
    assert "MASKED" not in set(out["operator"].astype(str))


# --------------------------------------------------------------------- noise

def test_noise_ratio_scales_to_each_column():
    rng = np.random.default_rng(0)
    n = 500
    df = pd.DataFrame({
        "small": rng.uniform(0, 1, n),            # unit scale
        "large": rng.normal(10_000, 50, n),       # large scale, different unit
    })
    preview = deid.generate_preview(df, "ds1", noise_ratio=0.05)
    out = apply_deidentification(df, preview)

    for col in ("small", "large"):
        observed = float(np.std(out[col].to_numpy() - df[col].to_numpy(), ddof=1))
        original = float(np.std(df[col].to_numpy(), ddof=1))
        assert observed / original == pytest.approx(0.05, rel=0.2), col

    # An absolute sigma would have destroyed `small` and left `large` untouched;
    # assert the two columns received very different absolute noise.
    sigma_small = preview.noise_config["small"]["sigma"]
    sigma_large = preview.noise_config["large"]["sigma"]
    assert sigma_large > 100 * sigma_small


def test_absolute_noise_that_is_negligible_is_reported():
    rng = np.random.default_rng(1)
    df = pd.DataFrame({"large": rng.normal(10_000, 50, 300)})
    preview = deid.generate_preview(
        df, "ds1", strategy_overrides={"large": "noise"}, noise_std=0.001,
    )
    assert any("negligible" in w for w in preview.warnings)


def test_noise_strategy_with_zero_sigma_is_reported():
    rng = np.random.default_rng(2)
    df = pd.DataFrame({"serial_no": rng.normal(100, 5, 50)})
    preview = deid.generate_preview(
        df, "ds1", sensitive_columns=["serial_no"], strategy_overrides={"serial_no": "noise"},
    )
    assert any("transmitted unchanged" in w for w in preview.warnings)


def test_noise_on_non_numeric_falls_back_to_pseudonyms_with_a_warning():
    df = _sample_df()
    preview = deid.generate_preview(
        df, "ds1", sensitive_columns=["operator"], strategy_overrides={"operator": "noise"},
    )
    assert preview.mask_strategies["operator"] == "hash"
    assert "operator" not in preview.noise_config
    assert any("non-numeric" in w for w in preview.warnings)


def test_unknown_strategy_override_is_rejected():
    with pytest.raises(ValueError, match="Unsupported mask strategy"):
        deid.generate_preview(
            _sample_df(), "ds1", sensitive_columns=["operator"],
            strategy_overrides={"operator": "scramble"},
        )


# ------------------------------------------------------------- hash integrity

def test_preview_hash_describes_the_applied_frame():
    # The audited hash must match the payload the transform actually produces.
    # Previously preview and apply were separate implementations with different
    # RNG streams, so the recorded hash described neither.
    df = _sample_df()
    preview = deid.generate_preview(df, "ds1", sensitive_columns=["operator"], noise_ratio=0.1)
    out = apply_deidentification(df, preview)
    assert canonical_frame_hash(out) == preview.upload_hash


@pytest.mark.parametrize("kwargs", [
    # (a) an excluded column: the old preview hashed a frame that still carried
    #     the excluded column (as "EXCLUDED") while the payload dropped it.
    {"excluded_columns": ["ok_flag"]},
    # (b) noise on a masked column: the old preview only noised transmitted
    #     columns, the old apply noised everything in the config.
    {"sensitive_columns": ["temperature"],
     "strategy_overrides": {"temperature": "noise"}, "noise_std": 0.5},
    # (c) a non-default seed: the old apply_masking defaulted to seed 42
    #     regardless of the seed the preview was built with.
    {"sensitive_columns": ["operator"], "noise_std": 0.5, "seed": 7},
])
def test_preview_hash_matches_apply_across_divergence_cases(kwargs):
    df = _sample_df()
    preview = deid.generate_preview(df, "ds1", **kwargs)
    out = apply_deidentification(df, preview)
    assert canonical_frame_hash(out) == preview.upload_hash


def test_repeated_previews_are_reproducible():
    df = _sample_df()
    a = deid.generate_preview(df, "ds1", sensitive_columns=["operator"], noise_ratio=0.1, seed=7)
    b = deid.generate_preview(df, "ds1", sensitive_columns=["operator"], noise_ratio=0.1, seed=7)
    assert a.upload_hash == b.upload_hash
    # The seed governs the noise; a different seed must change the payload for
    # a dataset that actually receives noise.
    c = deid.generate_preview(df, "ds1", sensitive_columns=["operator"], noise_ratio=0.1, seed=8)
    assert a.upload_hash != c.upload_hash


def test_canonical_hash_is_deterministic_and_numpy_independent():
    frame = pd.DataFrame({"a": np.array([1, 2, 3], dtype=np.int64),
                          "b": np.array([1.5, np.nan, 3.5], dtype=np.float64)})
    assert canonical_frame_hash(frame) == canonical_frame_hash(frame.copy())
    # Same values expressed as plain Python objects must hash identically.
    plain = pd.DataFrame({"a": [1, 2, 3], "b": [1.5, None, 3.5]})
    assert canonical_frame_hash(frame) == canonical_frame_hash(plain)


# ------------------------------------------------------- strategy overrides

def test_strategy_overrides_mask_with_hash():
    df = _sample_df()
    preview = deid.generate_preview(
        df, "ds1", sensitive_columns=["operator"], strategy_overrides={"operator": "hash"},
    )
    assert preview.mask_strategies["operator"] == "hash"
    out = apply_deidentification(df, preview)
    for val in out["operator"]:
        assert len(val) == PSEUDONYM_HEX_CHARS
        assert all(c in "0123456789abcdef" for c in val)


def test_strategy_overrides_mask_with_masked():
    df = _sample_df()
    preview = deid.generate_preview(
        df, "ds1", sensitive_columns=["temperature"], strategy_overrides={"temperature": "masked"},
    )
    assert preview.mask_strategies["temperature"] == "masked"
    out = apply_deidentification(df, preview)
    assert (out["temperature"] == "MASKED").all()


def test_strategy_overrides_noise_on_numeric_transmitted():
    df = _sample_df()
    preview = deid.generate_preview(
        df, "ds1", strategy_overrides={"temperature": "noise"}, noise_std=0.5,
    )
    assert preview.noise_config["temperature"]["method"] == "gaussian"
    assert preview.noise_config["temperature"]["sigma"] == 0.5
    out = apply_deidentification(df, preview, seed=7)
    assert pd.api.types.is_float_dtype(out["temperature"])


def test_noise_masked_column_gets_noise():
    df = _sample_df()
    preview = deid.generate_preview(
        df, "ds1", sensitive_columns=["temperature"],
        strategy_overrides={"temperature": "noise"}, noise_std=0.5,
    )
    out = apply_deidentification(df, preview, seed=3)
    assert "temperature" in out.columns
    assert pd.api.types.is_float_dtype(out["temperature"])
    assert (out["temperature"] != df["temperature"]).any()
