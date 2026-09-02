import os
import tempfile

import pandas as pd
import pytest

from process_intelligence_engine.data.importer import (
    ImportResult,
    ImportStats,
    import_file,
)


@pytest.fixture
def csv_simple(tmp_path):
    """A simple, well-formed CSV with mixed column types."""
    path = tmp_path / "simple.csv"
    path.write_text(
        "barcode,temperature,pressure,ok_flag,defect\naaa001,238.5,0.42,1,A\naaa002,241.2,0.45,1,\naaa003,255.1,0.51,0,B\n",
        encoding="utf-8",
    )
    return str(path)


@pytest.fixture
def xlsx_simple(tmp_path):
    """A simple Excel workbook."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "data"
    ws.append(["part_id", "x", "y", "ok"])
    ws.append(["P001", 1.5, 2.5, "OK"])
    ws.append(["P002", 1.8, 2.9, "OK"])
    ws.append(["P003", 2.1, 3.4, "NG"])
    path = tmp_path / "simple.xlsx"
    wb.save(path)
    return str(path)


def test_import_csv_detects_columns_and_rows(csv_simple):
    result = import_file(csv_simple)

    assert isinstance(result, ImportResult)
    assert result.row_count == 3
    assert result.column_count == 5
    assert result.columns == ["barcode", "temperature", "pressure", "ok_flag", "defect"]


def test_import_csv_preserves_raw_preview(csv_simple):
    result = import_file(csv_simple)

    assert len(result.raw_preview) == 4  # header + 3 rows
    assert result.raw_preview[0] == ["barcode", "temperature", "pressure", "ok_flag", "defect"]
    assert result.raw_preview[1][0] == "aaa001"


def test_import_xlsx_uses_first_sheet(xlsx_simple):
    result = import_file(xlsx_simple)

    assert result.row_count == 3
    assert result.column_count == 4
    assert result.columns == ["part_id", "x", "y", "ok"]


def test_import_reports_stats(csv_simple):
    result = import_file(csv_simple)

    stats = result.stats
    assert isinstance(stats, ImportStats)
    assert stats.row_count == 3
    assert stats.column_count == 5
    assert "temperature" in stats.column_stats
    assert stats.column_stats["temperature"]["numeric"] is True
    assert stats.column_stats["barcode"]["numeric"] is False


def test_import_csv_with_encoding_detection(tmp_path):
    """CSV encoded in a non-UTF8 encoding should still import with correct preview."""
    path = tmp_path / "big5.csv"
    # Big5-encoded Chinese labels
    path.write_bytes("溫度,壓力\n100,1.2\n200,2.4\n".encode("big5"))

    result = import_file(str(path))

    assert result.row_count == 2
    assert result.columns == ["溫度", "壓力"]
    assert result.encoding in {"big5", "cp950"}


def test_import_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        import_file("/nonexistent/path/file.csv")


def test_import_unsupported_extension(tmp_path):
    path = tmp_path / "data.txt"
    path.write_text("a,b\n1,2\n")

    with pytest.raises(ValueError) as excinfo:
        import_file(str(path))
    assert "supported" in str(excinfo.value).lower()


def test_import_empty_csv(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")

    result = import_file(str(path))
    assert result.row_count == 0
    assert result.column_count == 0


def test_to_dataframe_normalizes_types(tmp_path):
    """Full-data dataframe must coerce numeric columns and blank cells to NaN."""
    path = tmp_path / "normalize.csv"
    path.write_text(
        "temp,ok\n1.0,OK\n2.0,OK\n,NG\n4.0,OK\n",
        encoding="utf-8",
    )

    result = import_file(str(path))
    df = result.to_dataframe()

    assert pd.api.types.is_numeric_dtype(df["temp"])
    assert not pd.api.types.is_numeric_dtype(df["ok"])
    assert int(df["temp"].isna().sum()) == 1
    assert int(df["ok"].nunique()) == 2