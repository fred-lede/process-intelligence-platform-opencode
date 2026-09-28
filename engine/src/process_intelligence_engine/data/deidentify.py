"""Cloud upload de-identification (spec 11A, 24).

Before sending data to a cloud AI provider, the system must:
1. Show the user which columns will be transmitted and which are masked.
2. Require explicit confirmation before uploading.
3. Record the upload in the audit log with provider, model, columns, mask rules.

Masking strategies:
- Sensitive columns (identified by role or name) are pseudonymised (keyed
  HMAC) or replaced.
- Numerical columns can have Gaussian noise added, scaled to the column.
- Categorical columns can be replaced with anonymous tokens.

Design notes
------------
* **Pseudonyms are keyed, not plain hashes.** A truncated, unsalted SHA-256 of
  a low-cardinality identifier (an operator name, a lot number) is reversible
  by enumerating candidates, and the same value yields the same token for every
  customer forever. ``Pseudonymiser`` derives tokens with HMAC-SHA256 under a
  locally held key, so tokens are stable within a project but useless without
  the key.
* **One transformation, one hash.** ``generate_preview`` and ``apply_masking``
  share ``_transform``, and the preview's ``upload_hash`` is computed from the
  very frame the transform produces. Two parallel implementations previously
  disagreed, so the audited hash did not describe what was sent.
* **Noise is scaled to the column.** An absolute sigma applied to every column
  destroys a 0-1 column and leaves a 0-10000 column effectively untouched.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# Columns that are considered sensitive by default (by column name patterns)
SENSITIVE_PATTERNS = [
    "barcode", "serial", "serial_number", "sn", "lot", "lot_number",
    "operator", "employee", "name", "email", "phone", "address",
    "part_number", "part_num", "pn", "sku",
]

# Columns that should never be uploaded (by role)
PROHIBITED_ROLES = {"sensitive", "excluded", "identifier"}

#: Environment variable holding a hex pseudonym key (overrides the key file).
PSEUDONYM_KEY_ENV = "PROCESS_INTELLIGENCE_PSEUDONYM_KEY"

#: File created inside a project root to keep pseudonyms stable per project.
PSEUDONYM_KEY_FILENAME = ".pseudonym_key"

#: 128 bits of the HMAC digest. Truncation below this is brute-forceable for
#: the low-cardinality values this module exists to protect.
PSEUDONYM_HEX_CHARS = 32

#: Relative sigma below which added noise is reported as ineffective.
NEGLIGIBLE_NOISE_RATIO = 0.01


def _resolve_key_bytes(raw: str) -> bytes:
    try:
        key = bytes.fromhex(raw.strip())
    except ValueError as exc:
        raise ValueError(
            f"{PSEUDONYM_KEY_ENV} must be a hex string, got {raw[:8]!r}..."
        ) from exc
    if len(key) < 16:
        raise ValueError(f"{PSEUDONYM_KEY_ENV} must be at least 16 bytes (32 hex chars)")
    return key


class Pseudonymiser:
    """Derives stable, keyed pseudonyms for identifying values.

    Key resolution order:
    1. ``PROCESS_INTELLIGENCE_PSEUDONYM_KEY`` (hex).
    2. ``<project_root>/.pseudonym_key``, created with 0600 when missing.
    3. A fresh random key for this instance only.

    With (3) pseudonyms are *not* stable across processes; ``stable`` reports
    which case applies so the caller can surface that in the preview.
    """

    def __init__(self, project_root: str | Path | None = None, key: bytes | None = None):
        self._key, self.stable, self.source = self._resolve(project_root, key)

    @staticmethod
    def _resolve(project_root, key) -> tuple[bytes, bool, str]:
        if key is not None:
            if len(key) < 16:
                raise ValueError("pseudonym key must be at least 16 bytes")
            return key, True, "provided"
        env = os.environ.get(PSEUDONYM_KEY_ENV)
        if env:
            return _resolve_key_bytes(env), True, "environment"
        if project_root is not None:
            path = Path(project_root) / PSEUDONYM_KEY_FILENAME
            if path.is_file():
                return _resolve_key_bytes(path.read_text(encoding="utf-8")), True, str(path)
            generated = secrets.token_bytes(32)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(generated.hex(), encoding="utf-8")
            try:
                os.chmod(path, 0o600)
            except OSError:  # pragma: no cover - platform dependent
                pass
            return generated, True, str(path)
        return secrets.token_bytes(32), False, "ephemeral"

    @property
    def key_id(self) -> str:
        """Short public fingerprint of the key (safe to log and display)."""
        return hashlib.sha256(self._key).hexdigest()[:12]

    def token(self, value: Any) -> str:
        """Keyed pseudonym for ``value``; deterministic per key."""
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return "NULL"
        digest = hmac.new(self._key, str(value).encode("utf-8"), hashlib.sha256).hexdigest()
        return digest[:PSEUDONYM_HEX_CHARS]


def _is_textual(series: pd.Series) -> bool:
    """True for object / nullable-string / categorical columns.

    ``series.dtype in ("object", "string")`` compares a dtype *object* to a
    string, which silently fails for ``pd.StringDtype()`` and changes whether a
    column gets pseudonymised based on how pandas happened to read the file.
    """
    dtype = series.dtype
    return bool(
        pd.api.types.is_object_dtype(dtype)
        or pd.api.types.is_string_dtype(dtype)
        or isinstance(dtype, pd.CategoricalDtype)
    )


def _column(df: pd.DataFrame, col: str) -> pd.Series:
    """Fetch a single column, refusing ambiguous duplicate names.

    ``df[col]`` returns a DataFrame when the name is duplicated, which would
    otherwise turn a masking step into a silent no-op on a malformed file.
    """
    series = df[col]
    if isinstance(series, pd.DataFrame):
        raise ValueError(
            f"duplicate column name {col!r}; de-identification is ambiguous"
        )
    return series


def _jsonable(value: Any) -> Any:
    """Plain Python value, so the canonical hash does not depend on numpy."""
    if value is None or value is pd.NaT:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    return value


def canonical_frame_hash(frame: pd.DataFrame) -> str:
    """Order-independent, version-independent hash of a transformed frame.

    ``str(frame.to_dict())`` (the previous implementation) mixes numpy reprs
    and dict insertion order, so the recorded hash could not be relied on to
    describe what was transmitted.
    """
    payload = json.dumps(
        {
            "columns": [str(c) for c in frame.columns],
            "rows": [[_jsonable(v) for v in row] for row in frame.itertuples(index=False, name=None)],
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class UploadPreview:
    """Preview of what will be uploaded after de-identification."""

    dataset_id: str
    row_count: int
    total_columns: int
    transmitted_columns: list[str]
    masked_columns: list[str]
    excluded_columns: list[str]
    mask_strategies: dict[str, str]  # column -> strategy name
    noise_config: dict[str, dict]  # column -> {"sigma": float, "method": str, ...}
    upload_hash: str  # SHA-256 of the exact frame that would be transmitted
    timestamp: str
    seed: int = 42  #: seed used to build the frame the hash describes
    pseudonym_key_id: str = ""  #: fingerprint of the pseudonym key (not the key)
    pseudonyms_stable: bool = True
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "row_count": self.row_count,
            "total_columns": self.total_columns,
            "transmitted_columns": self.transmitted_columns,
            "masked_columns": self.masked_columns,
            "excluded_columns": self.excluded_columns,
            "mask_strategies": self.mask_strategies,
            "noise_config": self.noise_config,
            "upload_hash": self.upload_hash,
            "timestamp": self.timestamp,
            "seed": self.seed,
            "pseudonym_key_id": self.pseudonym_key_id,
            "pseudonyms_stable": self.pseudonyms_stable,
            "warnings": self.warnings,
        }


@dataclass
class UploadRecord:
    """Record of a confirmed cloud upload."""

    record_id: str
    operator: str
    provider: str
    model_version: str
    dataset_id: str
    row_count: int
    columns_uploaded: list[str]
    mask_rules: dict[str, str]
    noise_rules: dict[str, dict]
    upload_hash: str
    purpose: str
    timestamp: str
    pseudonym_key_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "operator": self.operator,
            "provider": self.provider,
            "model_version": self.model_version,
            "dataset_id": self.dataset_id,
            "row_count": self.row_count,
            "columns_uploaded": self.columns_uploaded,
            "mask_rules": self.mask_rules,
            "noise_rules": self.noise_rules,
            "upload_hash": self.upload_hash,
            "purpose": self.purpose,
            "timestamp": self.timestamp,
            "pseudonym_key_id": self.pseudonym_key_id,
        }


class DeidentificationEngine:
    """Engine for de-identifying data before cloud upload."""

    def __init__(self, project_root: str | Path | None = None, pseudonymiser: Pseudonymiser | None = None) -> None:
        self._upload_history: list[UploadRecord] = []
        self._pseudonymiser = pseudonymiser or Pseudonymiser(project_root=project_root)

    @property
    def pseudonymiser(self) -> Pseudonymiser:
        return self._pseudonymiser

    # ------------------------------------------------------------ strategies

    def _plan(
        self,
        df: pd.DataFrame,
        sensitive: set[str],
        excluded: set[str],
        noise_std: float,
        noise_ratio: float,
        overrides: dict[str, str],
    ) -> tuple[list[str], list[str], list[str], dict[str, str], dict[str, dict], list[str]]:
        cols = list(df.columns)
        auto_sensitive: set[str] = set()
        for col in cols:
            col_lower = str(col).lower()
            for pattern in SENSITIVE_PATTERNS:
                if pattern in col_lower:
                    auto_sensitive.add(col)
                    break

        all_sensitive = sensitive | auto_sensitive
        transmitted = [c for c in cols if c not in all_sensitive and c not in excluded]
        masked = [c for c in cols if c in all_sensitive and c not in excluded]
        excluded_final = [c for c in cols if c in excluded]

        warnings: list[str] = []

        mask_strategies: dict[str, str] = {}
        for col in masked:
            override = overrides.get(col)
            if override == "hash":
                mask_strategies[col] = "hash"
            elif override == "masked":
                mask_strategies[col] = "masked"
            elif override == "noise":
                if pd.api.types.is_numeric_dtype(_column(df, col)):
                    mask_strategies[col] = "noise"
                else:
                    # Never fall through to transmitting the raw value: keep the
                    # protective default and say so.
                    mask_strategies[col] = "hash" if _is_textual(_column(df, col)) else "replace"
                    warnings.append(
                        f"noise was requested for non-numeric column {col!r}; "
                        f"{mask_strategies[col]} applied instead"
                    )
            elif override is not None:
                raise ValueError(f"Unsupported mask strategy {override!r} for column {col!r}")
            elif _is_textual(_column(df, col)):
                mask_strategies[col] = "hash"
            else:
                # Non-textual sensitive columns still cannot be transmitted raw.
                mask_strategies[col] = "replace"

        noise_config: dict[str, dict] = {}
        for col in transmitted + masked:
            wants_noise = overrides.get(col) == "noise"
            if not wants_noise and (noise_std <= 0 and noise_ratio <= 0):
                continue
            if not pd.api.types.is_numeric_dtype(_column(df, col)):
                # A noise override on a non-numeric column was already reported
                # and downgraded in the strategy pass above.
                continue
            series = _column(df, col).dropna()
            # ddof=1 matches pandas' sample std, without the ambiguous stub type.
            column_std = (
                float(np.std(series.to_numpy(dtype=float), ddof=1))
                if len(series) > 1
                else 0.0
            )
            sigma = float(noise_std) if noise_std > 0 else float(noise_ratio) * column_std
            entry: dict[str, Any] = {
                "sigma": sigma,
                "method": "gaussian",
                "column_std": column_std,
            }
            if noise_ratio > 0 and noise_std <= 0:
                entry["ratio"] = float(noise_ratio)
            noise_config[col] = entry

        for col, cfg in noise_config.items():
            sigma = cfg["sigma"]
            column_std = cfg["column_std"]
            if sigma <= 0:
                warnings.append(
                    f"column {col!r} was configured for noise but sigma is 0, so its "
                    f"values would be transmitted unchanged"
                )
            elif column_std > 0 and sigma < NEGLIGIBLE_NOISE_RATIO * column_std:
                warnings.append(
                    f"noise on {col!r} is negligible relative to its spread "
                    f"(sigma={sigma:g}, column std={column_std:g})"
                )

        return transmitted, masked, excluded_final, mask_strategies, noise_config, warnings

    # ------------------------------------------------------------- transform

    def _transform(
        self,
        df: pd.DataFrame,
        transmitted: list[str],
        masked: list[str],
        mask_strategies: dict[str, str],
        noise_config: dict[str, dict],
        rng: np.random.Generator,
    ) -> pd.DataFrame:
        """Build the exact frame that would be transmitted.

        Single implementation shared by ``generate_preview`` and
        ``apply_masking``; a second copy is what let the audited hash drift
        away from the payload.
        """
        columns = list(transmitted) + list(masked)
        frame = pd.DataFrame({col: _column(df, col) for col in columns})

        for col in masked:
            strategy = mask_strategies.get(col)
            if strategy == "hash":
                frame[col] = _column(df, col).map(self._pseudonymiser.token).astype("object")
            elif strategy in ("masked", "replace"):
                frame[col] = "MASKED"
            # strategy "noise": value stays, noise is added below

        for col, cfg in noise_config.items():
            if col in frame.columns and cfg.get("method") == "gaussian":
                sigma = float(cfg.get("sigma", 0.0))
                if sigma <= 0:
                    continue
                noise = rng.normal(0.0, sigma, len(frame))
                frame[col] = frame[col].astype(float) + noise

        return frame

    # --------------------------------------------------------------- public

    def generate_preview(
        self,
        df: pd.DataFrame,
        dataset_id: str,
        sensitive_columns: list[str] | None = None,
        excluded_columns: list[str] | None = None,
        noise_std: float = 0.0,
        seed: int = 42,
        strategy_overrides: dict[str, str] | None = None,
        noise_ratio: float = 0.0,
    ) -> UploadPreview:
        """Generate a preview of what will be uploaded.

        Args:
            df: Full DataFrame.
            dataset_id: Dataset identifier.
            sensitive_columns: Columns to mask (by name).
            excluded_columns: Columns to exclude entirely.
            noise_std: Absolute Gaussian sigma added to numeric columns.
            seed: Random seed; the transmitted frame is reproduced from it.
            strategy_overrides: column -> "hash" | "masked" | "noise".
            noise_ratio: Gaussian sigma as a fraction of each column's std.
                Preferred over ``noise_std``: an absolute sigma is meaningless
                across columns with different units.

        Returns:
            UploadPreview whose ``upload_hash`` describes the exact frame
            ``apply_masking`` will produce.
        """
        transmitted, masked, excluded_final, mask_strategies, noise_config, warnings = self._plan(
            df,
            set(sensitive_columns or []),
            set(excluded_columns or []),
            float(noise_std),
            float(noise_ratio),
            dict(strategy_overrides or {}),
        )

        rng = np.random.default_rng(seed)
        frame = self._transform(df, transmitted, masked, mask_strategies, noise_config, rng)

        if not self._pseudonymiser.stable:
            warnings.append(
                "no pseudonym key is configured, so pseudonyms are random for this "
                "process and will not match a later upload"
            )

        return UploadPreview(
            dataset_id=dataset_id,
            row_count=len(df),
            total_columns=len(df.columns),
            transmitted_columns=transmitted,
            masked_columns=masked,
            excluded_columns=excluded_final,
            mask_strategies=mask_strategies,
            noise_config=noise_config,
            upload_hash=canonical_frame_hash(frame),
            timestamp=datetime.now(timezone.utc).isoformat(),
            seed=seed,
            pseudonym_key_id=self._pseudonymiser.key_id,
            pseudonyms_stable=self._pseudonymiser.stable,
            warnings=warnings,
        )

    def apply_masking(
        self,
        df: pd.DataFrame,
        preview: UploadPreview,
        seed: int | None = None,
    ) -> pd.DataFrame:
        """Apply masking to produce the actual uploaded DataFrame.

        ``seed`` defaults to the preview's seed so the result matches the
        hashed preview. Passing a different value silently changes the payload
        and is only useful for tests.
        """
        rng = np.random.default_rng(preview.seed if seed is None else seed)
        return self._transform(
            df,
            preview.transmitted_columns,
            preview.masked_columns,
            preview.mask_strategies,
            preview.noise_config,
            rng,
        )

    def record_upload(
        self,
        operator: str,
        provider: str,
        model_version: str,
        preview: UploadPreview,
        purpose: str = "",
    ) -> UploadRecord:
        """Record a confirmed upload."""
        import uuid

        record = UploadRecord(
            record_id=str(uuid.uuid4()),
            operator=operator,
            provider=provider,
            model_version=model_version,
            dataset_id=preview.dataset_id,
            row_count=preview.row_count,
            columns_uploaded=preview.transmitted_columns,
            mask_rules=preview.mask_strategies,
            noise_rules=preview.noise_config,
            upload_hash=preview.upload_hash,
            purpose=purpose,
            timestamp=datetime.now(timezone.utc).isoformat(),
            pseudonym_key_id=preview.pseudonym_key_id,
        )
        self._upload_history.append(record)
        return record

    def list_records(
        self,
        dataset_id: str | None = None,
        operator: str | None = None,
    ) -> list[dict]:
        """List upload records with optional filters."""
        result = []
        for rec in self._upload_history:
            if dataset_id and rec.dataset_id != dataset_id:
                continue
            if operator and rec.operator != operator:
                continue
            result.append(rec.to_dict())
        return result


# Module-level singleton
_DEID_ENGINE = DeidentificationEngine()


def generate_upload_preview(
    df: pd.DataFrame,
    dataset_id: str,
    sensitive_columns: list[str] | None = None,
    excluded_columns: list[str] | None = None,
    noise_std: float = 0.0,
    seed: int = 42,
    strategy_overrides: dict[str, str] | None = None,
    noise_ratio: float = 0.0,
) -> UploadPreview:
    """Convenience function for IPC handler."""
    return _DEID_ENGINE.generate_preview(
        df, dataset_id, sensitive_columns, excluded_columns, noise_std, seed,
        strategy_overrides, noise_ratio,
    )


def apply_deidentification(
    df: pd.DataFrame,
    preview: UploadPreview,
    seed: int | None = None,
) -> pd.DataFrame:
    """Apply de-identification to a DataFrame."""
    return _DEID_ENGINE.apply_masking(df, preview, seed)


def record_upload(
    operator: str,
    provider: str,
    model_version: str,
    preview: UploadPreview,
    purpose: str = "",
) -> UploadRecord:
    """Record a confirmed upload."""
    return _DEID_ENGINE.record_upload(operator, provider, model_version, preview, purpose)


def list_upload_records(
    dataset_id: str | None = None,
    operator: str | None = None,
) -> list[dict]:
    """List upload records."""
    return _DEID_ENGINE.list_records(dataset_id, operator)
