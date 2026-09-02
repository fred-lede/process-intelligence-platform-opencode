"""Tests for Phase 2 anomaly-scenario detection."""

import numpy as np
import pandas as pd
import pytest

from process_intelligence_engine.analysis.anomalies import (
    AnomalyDirection,
    AnomalyScenario,
    AnomalyType,
    build_analysis_package,
    detect_anomaly_scenarios,
)


def _sensor_df(n=200):
    rng = np.random.default_rng(11)
    temp = rng.normal(245.0, 1.0, n)
    pressure = rng.normal(0.45, 0.01, n)
    # Sparse extremes keep σ modest so extremes sit beyond ±3σ:
    temp[9] = 256.5
    temp[41] = 258.5
    temp[87] = 233.0
    temp[123] = 231.0
    pressure[5] = 0.58
    pressure[23] = 0.56
    pressure[57] = 0.32
    pressure[91] = 0.34
    # Clean 7-step rising run out of a trough starting at index 150.
    temp[144:151] = np.linspace(249.0, 243.0, 7)
    temp[150:157] = np.linspace(243.0, 258.0, 7)
    df = pd.DataFrame({"temperature": temp, "pressure": pressure})
    return df


def test_spec_anomalies_detected_with_probability():
    df = _sensor_df()
    scenarios = detect_anomaly_scenarios(
        df,
        spec={"output_field": "temperature", "lsl": 235.0, "usl": 255.0, "target": 245.0},
        control_limits={},
        engineering_scenarios=[],
    )
    spec_above = [s for s in scenarios if s.anomaly_type == AnomalyType.SPEC and s.direction == AnomalyDirection.ABOVE]
    spec_below = [s for s in scenarios if s.anomaly_type == AnomalyType.SPEC and s.direction == AnomalyDirection.BELOW]

    assert any(s.target_input == "temperature" for s in spec_above)
    assert 0.0 < spec_above[0].occurrence_probability <= 1.0
    assert spec_above[0].source == "historical_observation"
    assert spec_below
    assert spec_below[0].threshold == 235.0


def test_spec_anomaly_thresholds_from_limits():
    df = _sensor_df()
    scenarios = detect_anomaly_scenarios(
        df,
        spec={"output_field": "temperature", "lsl": None, "usl": 255.0, "target": None},
        control_limits={},
        engineering_scenarios=[],
    )
    above = [s for s in scenarios if s.anomaly_type == AnomalyType.SPEC and s.direction == AnomalyDirection.ABOVE]
    assert len(above) == 1
    assert above[0].threshold == 255.0
    # No BELOW *spec* scenario without an LSL.
    assert not any(s.anomaly_type == AnomalyType.SPEC and s.direction == AnomalyDirection.BELOW for s in scenarios)


def test_control_limits_auto_three_sigma():
    df = _sensor_df()
    scenarios = detect_anomaly_scenarios(
        df,
        spec={},
        control_limits={},  # not provided -> infer to mean ± 3 sigma
        runs_length=5,
        engineering_scenarios=[],
    )
    control = [s for s in scenarios if s.anomaly_type == AnomalyType.CONTROL]
    targets = {s.target_input for s in control}
    assert "temperature" in targets
    assert "pressure" in targets
    # The injected 256.5 values exceed mean+3σ; 233.0 below mean-3σ.
    kinds = {(s.target_input, s.direction.value) for s in control}
    assert ("temperature", "above") in kinds
    assert ("temperature", "below") in kinds


def test_control_limits_manual_override():
    df = _sensor_df()
    scenarios = detect_anomaly_scenarios(
        df,
        spec={},
        control_limits={"pressure": {"lcl": 0.30, "ucl": 0.60}},
        runs_length=5,
        engineering_scenarios=[],
    )
    pressure_controls = [
        s for s in scenarios
        if s.target_input == "pressure" and s.anomaly_type == AnomalyType.CONTROL
        and s.direction in (AnomalyDirection.ABOVE, AnomalyDirection.BELOW)
    ]
    # Manual limits contain all pressure data -> no anomaly events.
    assert all(s.occurrence_probability == 0.0 for s in pressure_controls)


def test_control_runs_rule_detects_continuous_rise():
    df = _sensor_df()
    scenarios = detect_anomaly_scenarios(
        df,
        spec={},
        control_limits={},
        runs_length=5,
        engineering_scenarios=[],
    )
    runs = [s for s in scenarios if s.direction == AnomalyDirection.RUN]
    assert runs
    run = runs[0]
    assert run.anomaly_type == AnomalyType.CONTROL
    assert run.name  # readable generated name
    assert run.magnitude_distribution["count"] > 0


def test_runs_not_flagged_without_enough_steps():
    df = _sensor_df()
    scenarios = detect_anomaly_scenarios(
        df,
        spec={},
        control_limits={},
        runs_length=8,  # injected run is only 7 steps
        engineering_scenarios=[],
    )
    runs = [s for s in scenarios if s.direction == AnomalyDirection.RUN]
    assert not runs


def test_engineering_deviations():
    df = _sensor_df()
    scenarios = detect_anomaly_scenarios(
        df,
        spec={},
        control_limits={},
        engineering_scenarios=[
            {
                "name": "溫度偏離",
                "target_input": "temperature",
                "direction": "deviation",
                "target": 245.0,
                "tolerance": 10.0,
            }
        ],
    )
    eng = [s for s in scenarios if s.anomaly_type == AnomalyType.ENGINEERING]
    assert eng
    assert eng[0].source == "engineering_input"
    assert eng[0].confidence >= 0.5
    assert eng[0].direction == AnomalyDirection.DEVIATION
    assert eng[0].target == 245.0
    assert eng[0].tolerance == 10.0
    assert eng[0].magnitude_distribution["count"] > 0


def test_scenario_serializable():
    df = _sensor_df()
    scenarios = detect_anomaly_scenarios(
        df,
        spec={"output_field": "temperature", "lsl": 235.0, "usl": 255.0, "target": 245.0},
        control_limits={},
        engineering_scenarios=[],
    )
    import json

    payload = json.dumps([s.to_dto() for s in scenarios])
    assert payload


def test_build_analysis_package_fingerprint():
    df = _sensor_df()
    scenarios = detect_anomaly_scenarios(
        df,
        spec={"output_field": "temperature", "lsl": 235.0, "usl": 255.0, "target": 245.0},
        control_limits={},
        engineering_scenarios=[],
    )
    pkg = build_analysis_package(
        dataset_id="ds-1",
        source_file="/tmp/sensor.csv",
        row_count=200,
        column_count=2,
        field_roles={"temperature": "output", "pressure": "input"},
        spec={"output_field": "temperature", "lsl": 235.0, "usl": 255.0, "target": 245.0},
        anomalies=[s.to_dto() for s in scenarios],
        confirmed_roles={"temperature", "pressure"},
    )
    assert pkg["data"]["row_count"] == 200
    assert pkg["data"]["column_count"] == 2
    assert pkg["data"]["source_file"] == "/tmp/sensor.csv"
    assert pkg["data"]["field_roles"]["temperature"] == "output"
    # completeness: output + inputs present.
    assert pkg["complete"] is True
    assert pkg["missing_requirements"] == []


def test_build_analysis_package_incomplete_without_output():
    pkg = build_analysis_package(
        dataset_id="ds-2",
        source_file="/tmp/x.csv",
        row_count=10,
        column_count=1,
        field_roles={"temperature": "input"},
        spec={},
        anomalies=[],
        confirmed_roles={"temperature"},
    )
    assert pkg["complete"] is False
    assert "output" in "".join(pkg["missing_requirements"])