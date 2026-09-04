"""Cloud upload de-identification (spec 11A, 24).

Before sending data to a cloud AI provider, the system must:
1. Show the user which columns will be transmitted and which are masked.
2. Require explicit confirmation before uploading.
3. Record the upload in the audit log with provider, model, columns, mask rules.

Masking strategies:
- Sensitive columns (identified by role or name) are hashed or replaced.
- Numerical columns can have Gaussian noise added.
- Categorical columns can be replaced with anonymous tokens.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
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
    noise_config: dict[str, dict]  # column -> {"std": float, "method": str}
    upload_hash: str  # SHA-256 of the uploaded data (for audit)
    timestamp: str

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
        }


class DeidentificationEngine:
    """Engine for de-identifying data before cloud upload."""

    def __init__(self) -> None:
        self._upload_history: list[UploadRecord] = []

    def generate_preview(
        self,
        df: pd.DataFrame,
        dataset_id: str,
        sensitive_columns: list[str] | None = None,
        excluded_columns: list[str] | None = None,
        noise_std: float = 0.0,
        seed: int = 42,
        strategy_overrides: dict[str, str] | None = None,
    ) -> UploadPreview:
        """Generate a preview of what will be uploaded.

        Args:
            df: Full DataFrame.
            dataset_id: Dataset identifier.
            sensitive_columns: Columns to mask (by name).
            excluded_columns: Columns to exclude entirely.
            noise_std: Std dev of Gaussian noise to add to numeric columns.
            seed: Random seed for reproducibility.

        Returns:
            UploadPreview with mask details and upload hash.
        """
        cols = list(df.columns)
        sensitive = set(sensitive_columns or [])
        excluded = set(excluded_columns or [])

        # Auto-detect sensitive columns by name patterns
        auto_sensitive: set[str] = set()
        for col in cols:
            col_lower = col.lower()
            for pattern in SENSITIVE_PATTERNS:
                if pattern in col_lower:
                    auto_sensitive.add(col)
                    break

        all_sensitive = sensitive | auto_sensitive

        transmitted = [c for c in cols if c not in all_sensitive and c not in excluded]
        masked = [c for c in cols if c in all_sensitive and c not in excluded]
        excluded_final = list(excluded)

        overrides = strategy_overrides or {}

        # Build mask strategies
        mask_strategies: dict[str, str] = {}
        for col in masked:
            if overrides.get(col) == "hash":
                mask_strategies[col] = "hash"
            elif overrides.get(col) == "masked":
                mask_strategies[col] = "masked"
            elif overrides.get(col) == "noise" and pd.api.types.is_numeric_dtype(df[col]):
                mask_strategies[col] = "noise"
            elif df[col].dtype in ("object", "string", "category"):
                mask_strategies[col] = "hash"
            else:
                mask_strategies[col] = "replace"

        # Build noise config
        noise_config: dict[str, dict] = {}
        rng = np.random.default_rng(seed)
        for col in transmitted:
            if overrides.get(col) == "noise" and pd.api.types.is_numeric_dtype(df[col]):
                noise_config[col] = {"std": noise_std, "method": "gaussian"}
            elif pd.api.types.is_numeric_dtype(df[col]) and noise_std > 0:
                noise_config[col] = {"std": noise_std, "method": "gaussian"}
        for col in masked:
            if overrides.get(col) == "noise" and pd.api.types.is_numeric_dtype(df[col]):
                noise_config[col] = {"std": noise_std, "method": "gaussian"}

        # Compute upload hash (SHA-256 of transmitted data summary)
        upload_data = df[transmitted].copy()
        for col in masked:
            if mask_strategies.get(col) == "hash" and df[col].dtype in ("object", "string"):
                upload_data[col] = df[col].apply(
                    lambda x: sha256(str(x).encode()).hexdigest()[:8] if pd.notna(x) else "NULL"
                )
            else:
                upload_data[col] = "MASKED"
        for col in excluded_final:
            upload_data[col] = "EXCLUDED"

        # Add noise to numeric columns
        if noise_std > 0:
            for col in transmitted:
                if col in noise_config and pd.api.types.is_numeric_dtype(df[col]):
                    noise = rng.normal(0, noise_std, len(upload_data))
                    upload_data[col] = upload_data[col].astype(float) + noise

        data_bytes = str(upload_data.to_dict()).encode()
        upload_hash = sha256(data_bytes).hexdigest()

        return UploadPreview(
            dataset_id=dataset_id,
            row_count=len(df),
            total_columns=len(cols),
            transmitted_columns=transmitted,
            masked_columns=masked,
            excluded_columns=excluded_final,
            mask_strategies=mask_strategies,
            noise_config=noise_config,
            upload_hash=upload_hash,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def apply_masking(
        self,
        df: pd.DataFrame,
        preview: UploadPreview,
        seed: int = 42,
    ) -> pd.DataFrame:
        """Apply masking to produce the actual uploaded DataFrame."""
        rng = np.random.default_rng(seed)
        df_out = df[preview.transmitted_columns + list(preview.masked_columns)].copy()

        # Hash / mask sensitive columns
        for col in preview.masked_columns:
            strategy = preview.mask_strategies.get(col)
            if strategy == "hash":
                df_out[col] = df_out[col].apply(
                    lambda x: sha256(str(x).encode()).hexdigest()[:8] if pd.notna(x) else "NULL"
                )
            elif strategy in ("masked", "replace"):
                df_out[col] = "MASKED"
            # strategy "noise": leave values warm; noise applied below

        # Add noise to numeric columns (transmitted or noise-masked)
        for col, cfg in preview.noise_config.items():
            if col in df_out.columns and cfg["method"] == "gaussian":
                noise = rng.normal(0, cfg["std"], len(df_out))
                df_out[col] = df_out[col].astype(float) + noise

        return df_out

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
) -> UploadPreview:
    """Convenience function for IPC handler."""
    return _DEID_ENGINE.generate_preview(
        df, dataset_id, sensitive_columns, excluded_columns, noise_std, seed,
        strategy_overrides,
    )


def apply_deidentification(
    df: pd.DataFrame,
    preview: UploadPreview,
    seed: int = 42,
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
