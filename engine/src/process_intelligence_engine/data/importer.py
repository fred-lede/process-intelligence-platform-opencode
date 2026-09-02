"""Excel/CSV data import with encoding detection.

Phase 1 scope:
- Read a single-file Unit/product granularity dataset.
- Detect encoding for CSV, delimiter, and produce a raw preview
  plus lightweight per-column type stats.
- Never mutates the source file. All results are in-memory.
"""

from __future__ import annotations

import csv as _csv
from dataclasses import dataclass, field
from pathlib import Path

try:
    import pandas as pd  # type: ignore
except ImportError:  # pragma: no cover
    pd = None

SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv"}


@dataclass
class ColumnStats:
    """Lightweight per-column statistics used for field detection."""

    numeric: bool
    non_null_count: int
    unique_count: int

    def __getitem__(self, key: str):
        return getattr(self, key)


@dataclass
class ImportStats:
    """Aggregate import statistics."""

    row_count: int
    column_count: int
    column_stats: dict[str, ColumnStats] = field(default_factory=dict)


@dataclass
class ImportResult:
    """Result of an import operation."""

    file_path: str
    format: str
    encoding: str
    delimiter: str | None
    columns: list[str]
    raw_preview: list[list[str|None]]
    row_count: int
    column_count: int
    stats: ImportStats
    _data: list[list[str | None]] = field(default_factory=list, repr=False)

    def to_dataframe(self, values: list[list[str | None]] | None = None) -> "pd.DataFrame":
        """Rebuild a type-normalized dataframe from captured cell values.

        Empty strings become NaN and columns that are numeric in >= 90% of
        their populated cells are coerced to numeric, so downstream stages
        (quality, distribution, modeling) see analysis-ready types.
        """
        rows = self._data if self._data else (values or self.raw_preview[1:])
        data: dict[str, list] = {col: [] for col in self.columns}
        for row in rows:
            row = list(row) + [None] * (len(self.columns) - len(row))
            for col, value in zip(self.columns, row):
                if isinstance(value, str) and value.strip() == "":
                    value = None
                data[col].append(value)
        frame = pd.DataFrame(data)
        for col in frame.columns:
            coerced = pd.to_numeric(frame[col], errors="coerce")
            populated = frame[col].notna().sum()
            if populated > 0 and coerced.notna().sum() >= populated * 0.9:
                frame[col] = coerced
        return frame

    def to_dto(self) -> dict:
        """Serialize into a JSON-compatible dict."""
        column_stats = {
            name: {
                "numeric": cs.numeric,
                "non_null_count": cs.non_null_count,
                "unique_count": cs.unique_count,
            }
            for name, cs in self.stats.column_stats.items()
        }
        return {
            "file_path": self.file_path,
            "format": self.format,
            "encoding": self.encoding,
            "delimiter": self.delimiter,
            "columns": self.columns,
            "raw_preview": self.raw_preview,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "stats": {
                "row_count": self.stats.row_count,
                "column_count": self.stats.column_count,
                "column_stats": column_stats,
            },
        }


def _detect_encoding(path: Path, sample_size: int = 100_000) -> str:
    """Detect CSV encoding. Tries UTF-8, then common fallbacks."""
    raw = path.read_bytes()[:sample_size]
    for enc in ("utf-8", "big5", "cp950", "gb18030", "shift_jis", "latin-1"):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "utf-8"


def _detect_delimiter(path: Path) -> str:
    """Detect CSV delimiter from the first line."""
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
            first_line = fh.readline()
    except OSError:
        return ","
    if not first_line:
        return ","
    counts = {d: first_line.count(d) for d in (",", ";", "\t", "|")}
    if not any(counts.values()):
        return ","
    return max(counts, key=counts.get)


def _infer_numeric(values: list[str | None]) -> bool:
    """Heuristic numeric check over a column's raw string values."""
    non_null = [v for v in values if v is not None and str(v).strip() != ""]
    if not non_null:
        return False
    numeric_hits = 0
    for v in non_null[:200]:
        try:
            float(v)
            numeric_hits += 1
        except (TypeError, ValueError):
            continue
    return numeric_hits / len(non_null) >= 0.9


def _frame_to_rows(frame: pd.DataFrame) -> list[list[str | None]]:
    """Convert an entire frame to string|None cell lists (full data)."""
    return frame.apply(
        lambda row: [None if pd.isna(v) else str(v) for v in row],
        axis=1,
    ).tolist()


def _import_csv(path: Path, preview_rows: int = 50) -> ImportResult:
    encoding = _detect_encoding(path)
    delimiter = _detect_delimiter(path)

    try:
        frame = pd.read_csv(path, encoding=encoding, sep=delimiter, dtype=str, keep_default_na=False)
    except pd.errors.EmptyDataError:
        return ImportResult(
            file_path=str(path),
            format="csv",
            encoding=encoding,
            delimiter=delimiter,
            columns=[],
            raw_preview=[],
            row_count=0,
            column_count=0,
            stats=ImportStats(row_count=0, column_count=0, column_stats={}),
            _data=[],
        )
    except UnicodeDecodeError:
        # Fall back to replacing decode to guarantee a readable preview.
        frame = pd.read_csv(path, encoding="utf-8", errors="replace", sep=delimiter, dtype=str, keep_default_na=False)

    if frame.empty or frame.columns.tolist() == [""] or all(c == "" for c in frame.columns):
        columns: list[str] = []
        raw_preview: list[list[str | None]] = []
        row_count = 0
        column_count = 0
        stats = ImportStats(row_count=0, column_count=0, column_stats={})
        data: list[list[str | None]] = []
    else:
        columns = [str(c) for c in frame.columns]
        row_count = int(frame.shape[0])
        column_count = int(frame.shape[1])
        rows = frame.head(preview_rows).astype(object).apply(lambda row: [None if str(v) == "" else str(v) for v in row], axis=1).tolist()
        raw_preview = [columns] + rows
        data = _frame_to_rows(frame.astype(object))

        column_stats: dict[str, ColumnStats] = {}
        for col in columns:
            values = frame[col].tolist()
            non_null = [v for v in values if v is not None and str(v).strip() != ""]
            column_stats[col] = ColumnStats(
                numeric=_infer_numeric(values),
                non_null_count=len(non_null),
                unique_count=len(set(non_null)),
            )
        stats = ImportStats(row_count=row_count, column_count=column_count, column_stats=column_stats)

    return ImportResult(
        file_path=str(path),
        format="csv",
        encoding=encoding,
        delimiter=delimiter,
        columns=columns,
        raw_preview=raw_preview,
        row_count=row_count,
        column_count=column_count,
        stats=stats,
        _data=data,
    )


def _import_excel(path: Path, preview_rows: int = 50) -> ImportResult:
    frame = pd.read_excel(path, sheet_name=0, dtype=object)
    if frame.empty:
        return ImportResult(
            file_path=str(path),
            format="xlsx",
            encoding="binary",
            delimiter=None,
            columns=[],
            raw_preview=[],
            row_count=0,
            column_count=0,
            stats=ImportStats(row_count=0, column_count=0, column_stats={}),
            _data=[],
        )

    columns = [str(c) for c in frame.columns]
    row_count = int(frame.shape[0])
    column_count = int(frame.shape[1])
    rows = frame.head(preview_rows).apply(lambda row: [None if pd.isna(v) else str(v) for v in row], axis=1).tolist()
    raw_preview = [columns] + rows
    data = _frame_to_rows(frame)

    column_stats: dict[str, ColumnStats] = {}
    for col in columns:
        values = frame[col].tolist()
        non_null = [v for v in values if v is not None and not (isinstance(v, float) and pd.isna(v)) and str(v).strip() != ""]
        column_stats[col] = ColumnStats(
            numeric=_infer_numeric([str(v) if v is not None else None for v in values]),
            non_null_count=len(non_null),
            unique_count=len(set(non_null)),
        )
    stats = ImportStats(row_count=row_count, column_count=column_count, column_stats=column_stats)

    return ImportResult(
        file_path=str(path),
        format=path.suffix.lstrip("."),
        encoding="binary",
        delimiter=None,
        columns=columns,
        raw_preview=raw_preview,
        row_count=row_count,
        column_count=column_count,
        stats=stats,
        _data=data,
    )


def import_file(file_path: str, preview_rows: int = 50) -> ImportResult:
    """Import a single Excel or CSV file.

    Args:
        file_path: Path to the file to import.
        preview_rows: Maximum number of rows to include in the preview.

    Returns:
        An ImportResult with columns, preview and stats.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file extension is not supported.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file extension '{ext}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    result = _import_csv(path, preview_rows) if ext == ".csv" else _import_excel(path, preview_rows)
    return result


__all__ = ["ImportResult", "ImportStats", "ColumnStats", "import_file"]