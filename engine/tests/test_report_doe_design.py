"""The report's designed-DOE content: design basis, ANOVA df, and model-type names.

Written because a designed-DOE report used to carry none of this: the design context was
computed for validation/analyze and never reached ReportData, and the renderers printed the
raw model id, so an exported report showed "doe_categorical_factorial" where the application
shows a model name.
"""
from io import BytesIO
from typing import Any

from openpyxl import load_workbook

from process_intelligence_engine.reporting.models import ReportData, model_type_label
from process_intelligence_engine.reporting.html import HTMLReportGenerator
from process_intelligence_engine.reporting.excel import ExcelReportGenerator


DESIGN_CONTEXT = {
    "kind": "categorical_factorial_doe",
    "validation_mode": "design_based",
    "n_obs": 27,
    "n_cells": 9,
    "observed_cells": 9,
    "replicate_min": 1,
    "replicate_max": 1,
    "model_df": 8,
    "residual_df": 18,
    "has_replicates": False,
    "warning": "Small designed DOE: use ANOVA, residual diagnostics, and confirmation "
               "experiments as primary evidence; ordinary random-fold CV is supplementary.",
}


def _data(**kwargs: Any) -> ReportData:
    base: dict[str, Any] = {
        "project_name": "DOE Report",
        "operator": "Tester",
        "dataset_id": "ds_doe",
        "best_model": {"model_id": "m1", "model_type": "doe_categorical_factorial"},
    }
    base.update(kwargs)
    return ReportData(**base)


def _html(**kwargs: Any) -> str:
    return HTMLReportGenerator(_data(**kwargs)).generate()


def test_model_type_label_maps_known_types_and_keeps_unknown_ids():
    assert model_type_label("doe_categorical_factorial") == "DOE 三水準類別因子"
    assert model_type_label("xgboost") == "XGBoost"
    # An unrecognised type must stay visible rather than become blank or a guess.
    assert model_type_label("some_future_type") == "some_future_type"
    assert model_type_label(None) == ""


def test_report_shows_the_model_name_not_the_raw_id():
    html = _html()
    assert "DOE 三水準類別因子" in html
    assert "doe_categorical_factorial" not in html


def test_design_section_absent_without_a_design_context():
    assert "設計基礎與 ANOVA 自由度" not in _html()


def test_design_section_reports_cells_and_degrees_of_freedom():
    html = _html(design_context=DESIGN_CONTEXT, confirmation_evidence={})
    assert "設計基礎與 ANOVA 自由度" in html
    assert "實際觀測格數" in html
    assert "殘差自由度" in html
    # No replicates means pure error and lack-of-fit cannot be estimated; the report has to
    # say so rather than let the reader assume replication was tested.
    assert "沒有重複觀測" in html


def test_design_section_states_when_replicates_allow_lack_of_fit():
    ctx = dict(DESIGN_CONTEXT, has_replicates=True, replicate_max=2)
    html = _html(design_context=ctx)
    assert "有重複觀測" in html
    assert "缺適性" in html


def test_design_section_flags_unobserved_cells_as_a_gap():
    ctx = dict(DESIGN_CONTEXT, n_cells=27, observed_cells=9)
    assert "設計缺口" in _html(design_context=ctx)


def test_design_section_reports_confirmation_evidence_when_present():
    evidence = {"count": 3, "pass_count": 2, "pass_rate": 2 / 3,
                "mean_abs_prediction_error": 0.125}
    html = _html(design_context=DESIGN_CONTEXT, confirmation_evidence=evidence)
    assert "確認實驗" in html
    assert "67%" in html


def test_design_section_says_evidence_is_missing_when_no_confirmation_exists():
    html = _html(design_context=DESIGN_CONTEXT,
                 confirmation_evidence={"count": 0, "pass_count": 0, "pass_rate": None,
                                        "mean_abs_prediction_error": None})
    assert "尚無確認實驗記錄" in html


def test_categorical_note_does_not_claim_contour_or_surface_charts():
    # Categorical factors are discrete levels; claiming Contour/3D Surface would describe
    # charts this report does not contain.
    assert "不含 Contour 與 3D Surface" in _html(design_context=DESIGN_CONTEXT)


def test_continuous_doe_keeps_the_contour_note():
    html = _html(best_model={"model_id": "m2", "model_type": "doe_quadratic"})
    assert "Contour／Surface 為其他輸入固定下的切片" in html
    assert "設計基礎與 ANOVA 自由度" not in html  # no design context passed


def test_excel_carries_the_design_sheet_and_the_model_name():
    wb = load_workbook(BytesIO(ExcelReportGenerator(
        _data(design_context=DESIGN_CONTEXT, confirmation_evidence={})
    ).generate()))
    assert "設計基礎" in wb.sheetnames
    sheet = wb["設計基礎"]
    cells = [c.value for row in sheet.iter_rows() for c in row]
    assert "殘差自由度" in cells
    assert "實際觀測格數" in cells


def test_excel_comparison_sheet_has_no_raw_model_ids():
    data = _data(model_comparison=[
        {"model_id": "m1", "model_type": "doe_categorical_factorial", "metrics": {},
         "status": "validated"},
    ])
    wb = load_workbook(BytesIO(ExcelReportGenerator(data).generate()))
    values = [c.value for row in wb["模型比較"].iter_rows() for c in row]
    assert "DOE 三水準類別因子" in values
    assert "doe_categorical_factorial" not in values
