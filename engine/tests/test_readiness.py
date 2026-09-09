import pandas as pd

from process_intelligence_engine.data.readiness import analyze_readiness


def test_readiness_reports_distribution_and_summary_for_input_output_fixture():
    df = pd.DataFrame({"input_load": [1.0, 1.2, 1.1, 1.3], "output": [10.0, 10.2, 9.9, 10.1]})
    result = analyze_readiness(df, [{"name": "input_load", "role": "input"}, {"name": "output", "role": "output"}])
    assert result["status"] == "info"
    assert {item["column"] for item in result["columns"]} == {"input_load", "output"}
    assert result["columns"][0]["best_distribution"] == "empirical"
    assert result["columns"][0]["summary"]["min"] == 1.0


def test_readiness_flags_missing_and_constant_columns():
    df = pd.DataFrame({"input": [1.0, None, 1.0], "output": [2.0, 2.0, 2.0]})
    result = analyze_readiness(df, [{"name": "input", "role": "input"}, {"name": "output", "role": "output"}])
    by_name = {item["column"]: item for item in result["columns"]}
    assert result["status"] == "warning"
    assert by_name["input"]["status"] == "warning"
    assert by_name["output"]["status"] == "warning"
    assert {"missing_values", "constant_column"}.issubset({issue["code"] for issue in by_name["input"]["issues"]})
    assert {issue["code"] for issue in by_name["output"]["issues"]} == {"constant_column"}


def test_readiness_blocks_column_without_numeric_values():
    df = pd.DataFrame({"input": ["bad", "data"], "output": [1.0, 2.0]})
    result = analyze_readiness(df, [{"name": "input", "role": "input"}, {"name": "output", "role": "output"}])
    item = next(item for item in result["columns"] if item["column"] == "input")
    assert result["status"] == "critical"
    assert item["status"] == "critical"
    assert item["issues"][0]["code"] == "no_numeric_values"
