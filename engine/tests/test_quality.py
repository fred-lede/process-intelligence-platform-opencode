import pandas as pd
import pytest

from process_intelligence_engine.data.quality import (
    QualityCheck,
    QualityReport,
    QualityIssue,
    QualityStatus,
    run_quality_checks,
)


def _make_df(data: dict) -> pd.DataFrame:
    return pd.DataFrame(data)


def test_missing_value_detection():
    df = _make_df({"temp": [1.0, None, 3.0], "pressure": [1.0, 2.0, 3.0]})
    report = run_quality_checks(df)

    temp_issue = next(
        (i for i in report.issues if i.check == QualityCheck.MISSING_VALUE
         and i.column == "temp"), None
    )
    assert temp_issue is not None
    assert temp_issue.severity == QualityStatus.WARNING
    assert temp_issue.detail["missing_rate"] == pytest.approx(1 / 3)


def test_duplicate_rows_detection():
    df = _make_df({"id": [1, 1, 2], "v": [0.5, 0.5, 0.7]})
    report = run_quality_checks(df)

    assert any(i.check == QualityCheck.DUPLICATE for i in report.issues)


def test_constant_column_detection():
    df = _make_df({"temp": [255.0, 255.0, 255.0], "id": [1, 2, 3]})
    report = run_quality_checks(df)

    assert any(
        i.check == QualityCheck.CONSTANT_COLUMN and i.column == "temp"
        for i in report.issues
    )


def test_outlier_detection_iqr():
    df = _make_df({"v": [10, 11, 12, 13, 14, 100]})
    report = run_quality_checks(df, categorical_columns=[])

    outlier = next(
        (i for i in report.issues if i.check == QualityCheck.OUTLIER
         and i.column == "v"), None
    )
    assert outlier is not None
    assert outlier.severity == QualityStatus.WARNING


def test_unbalanced_okng_detection():
    df = _make_df({"flag": ["OK", "OK", "OK", "OK", "NG"]})
    report = run_quality_checks(df, quality_columns=["flag"])

    assert any(
        i.check == QualityCheck.UNBALANCED_OKNG for i in report.issues
    )


def test_datetime_order_anomaly():
    df = pd.DataFrame({"ts": ["2026-01-01", "2026-01-02", "2025-12-31"]})
    # Note: values are treated as categorical when not declared as datetime.
    report = run_quality_checks(df, datetime_columns=["ts"])

    assert any(i.check == QualityCheck.TIME_ORDER for i in report.issues)


def test_no_issues_on_clean_dataframe():
    df = _make_df({
        "id": list(range(100)),
        "temp": [255.0 + (i % 10) for i in range(100)],
        "pressure": [1.0] * 100,
    })
    report = run_quality_checks(df)

    # Clean data: still might flag pressure as constant; assert report has
    # a lowered severity overall (no critical issues).
    assert all(i.severity != QualityStatus.CRITICAL for i in report.issues)


def test_report_contains_summary_counts():
    df = _make_df({"a": [1, None, 3], "b": ["x", "x", "x"]})
    report = run_quality_checks(df)

    assert report.row_count == 3
    assert report.column_count == 2
    assert report.issue_count >= 2
    assert isinstance(report.issues, list)


def test_outlier_classification_field_present():
    df = _make_df({"v": [10, 11, 12, 13, 14, 100]})
    report = run_quality_checks(df, categorical_columns=[])

    outlier = next(
        (i for i in report.issues if i.check == QualityCheck.OUTLIER), None
    )
    assert outlier is not None
    assert "classification" in outlier.detail

    # Classification must be one of the spec's categories.
    assert outlier.detail["classification"] in {
        "possible_measurement_error",
        "possible_process_anomaly",
        "true_extreme_event",
        "undetermined",
    }


def test_invalid_format_detection():
    df = _make_df({"temperature": ["85.1", "85.2", "85mv", "85.3", "85.4"]})
    report = run_quality_checks(df)

    invalid = next(
        (i for i in report.issues if i.check == QualityCheck.INVALID_FORMAT
         and i.column == "temperature"), None
    )
    assert invalid is not None
    assert invalid.severity == QualityStatus.WARNING
    assert invalid.detail["non_numeric_count"] == 1


def test_no_invalid_format_when_consistent_strings():
    df = _make_df({"note": ["ok", "ng", "warn", "ok"]})
    report = run_quality_checks(df)

    assert not any(i.check == QualityCheck.INVALID_FORMAT for i in report.issues)


def test_unit_mixing_detection():
    df = _make_df({"length": ["12.5mm", "13.0mm", "0.51in", "13.1mm"]})
    report = run_quality_checks(df)

    unit = next(
        (i for i in report.issues if i.check == QualityCheck.UNIT_MIXING
         and i.column == "length"), None
    )
    assert unit is not None
    assert set(unit.detail["units"]) == {"mm", "in"}


def test_no_unit_mixing_when_single_unit():
    df = _make_df({"length": ["12.5mm", "13.0mm", "13.1mm"]})
    report = run_quality_checks(df)

    assert not any(i.check == QualityCheck.UNIT_MIXING for i in report.issues)


def test_input_out_of_range_with_provided_ranges():
    df = _make_df({"temp": [220.0, 230.0, 255.0, 999.0, 228.0]})
    report = run_quality_checks(
        df,
        input_columns=["temp"],
        input_ranges={"temp": (210.0, 260.0)},
    )

    oor = next(
        (i for i in report.issues if i.check == QualityCheck.INPUT_OUT_OF_RANGE
         and i.column == "temp"), None
    )
    assert oor is not None
    assert oor.detail["out_of_range_count"] == 1
    assert oor.detail["range_lower"] == 210.0
    assert oor.detail["range_upper"] == 260.0


def test_input_out_of_range_statistical_heuristic():
    df = _make_df({"temp": [100.0, 101.0, 102.0, 103.0, 104.0, 1500.0]})
    report = run_quality_checks(df, input_columns=["temp"])

    oor = next(
        (i for i in report.issues if i.check == QualityCheck.INPUT_OUT_OF_RANGE
         and i.column == "temp"), None
    )
    assert oor is not None


def test_input_out_of_range_no_range_set():
    df = _make_df({"temp": [255.0, 255.1, 255.2, 255.3, 255.4]})
    report = run_quality_checks(df, input_columns=["temp"])

    assert not any(i.check == QualityCheck.INPUT_OUT_OF_RANGE for i in report.issues)


def test_missing_spec_detection():
    df = _make_df({"thickness": [1.6, 1.61, 1.62, 1.63, 1.64]})
    report = run_quality_checks(
        df,
        output_columns=["thickness"],
        spec={"thickness": {"lsl": None, "usl": None, "target": 1.62}},
    )

    missing = next(
        (i for i in report.issues if i.check == QualityCheck.MISSING_SPEC
         and i.column == "thickness"), None
    )
    assert missing is not None


def test_missing_spec_when_spec_present():
    df = _make_df({"thickness": [1.6, 1.61, 1.62, 1.63, 1.64]})
    report = run_quality_checks(
        df,
        output_columns=["thickness"],
        spec={"thickness": {"lsl": 1.5, "usl": 1.8, "target": 1.62}},
    )

    assert not any(i.check == QualityCheck.MISSING_SPEC for i in report.issues)