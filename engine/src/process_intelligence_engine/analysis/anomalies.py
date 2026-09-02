"""Anomaly-scenario detection and the analysis data package (Phase 2).

Three anomaly families from the spec (section 11.2):

1. Spec anomalies      — value outside LSL/USL tolerance of the output.
2. Process control     — value beyond control limits (auto mean±3σ unless
                          overridden) or a sustained monotonic rise (runs rule).
3. Engineering         — user-defined deviation templates around a target.

Every scenario carries an occurrence probability estimated from the data,
a source tag, a confidence and a magnitude-distribution summary (used by
Monte Carlo in a later phase). All outputs are plain Python types so they
serialize cleanly to JSON.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import pandas as pd


class AnomalyType(Enum):
    SPEC = "spec"
    CONTROL = "control"
    ENGINEERING = "engineering"


class AnomalyDirection(Enum):
    ABOVE = "above"
    BELOW = "below"
    RUN = "run"
    DEVIATION = "deviation"


DEFAULT_RUNS_LENGTH = 5
CONTROL_SIGMA = 3.0
ENGINEERING_CONFIDENCE = 0.85


@dataclass
class AnomalyScenario:
    anomaly_id: str
    name: str
    anomaly_type: AnomalyType
    target_input: str
    direction: AnomalyDirection
    threshold: float | None = None
    target: float | None = None
    tolerance: float | None = None
    occurrence_probability: float = 0.0
    magnitude_distribution: dict | None = None
    duration_distribution: dict | None = None
    correlation_group: str | None = None
    source: str = "historical_observation"
    confidence: float = 0.0
    user_confirmed: bool = False
    detail: dict = field(default_factory=dict)

    def to_dto(self) -> dict:
        return {
            "anomaly_id": self.anomaly_id,
            "name": self.name,
            "type": self.anomaly_type.value,
            "target_input": self.target_input,
            "direction": self.direction.value,
            "threshold": self.threshold,
            "target": self.target,
            "tolerance": self.tolerance,
            "occurrence_probability": float(self.occurrence_probability),
            "magnitude_distribution": self.magnitude_distribution,
            "duration_distribution": self.duration_distribution,
            "correlation_group": self.correlation_group,
            "source": self.source,
            "confidence": float(self.confidence),
            "user_confirmed": self.user_confirmed,
            "detail": self.detail,
        }


def _clean(series: pd.Series) -> np.ndarray:
    return pd.to_numeric(series, errors="coerce").dropna().to_numpy(dtype=float)


def _confidence_from_events(n_events: int, n_total: int) -> float:
    """Heuristic confidence from evidence strength."""
    if n_events == 0:
        return 0.4
    if n_total == 0:
        return 0.4
    # More events => higher confidence, capped at 0.95.
    return min(0.95, 0.5 + 0.35 * np.sqrt(n_events / max(n_total, 1)) * 10)


def _magnitude(values: np.ndarray, threshold: float) -> dict:
    deviations = values - threshold
    return {
        "mean": float(deviations.mean()) if deviations.size else None,
        "std": float(deviations.std()) if deviations.size else None,
        "min": float(deviations.min()) if deviations.size else None,
        "max": float(deviations.max()) if deviations.size else None,
        "count": int(deviations.size),
    }


def _detect_threshold_anomaly(
    df: pd.DataFrame,
    column: str,
    threshold: float,
    direction: AnomalyDirection,
    name: str,
    anomaly_type: AnomalyType,
    source: str,
    base_confidence: float | None = None,
    counter: list[int] | None = None,
    emit_if_zero: bool = True,
) -> AnomalyScenario | None:
    series = _clean(df[column])
    if series.size == 0:
        return None
    if direction == AnomalyDirection.ABOVE:
        mask = series > threshold
    else:
        mask = series < threshold
    n_events = int(mask.sum())
    n_total = int(series.size)
    if n_events == 0 and not emit_if_zero:
        return None
    scenario = AnomalyScenario(
        anomaly_id=f"an-{counter[0]}" if counter else f"an-{id(df) % 100000}",
        name=name,
        anomaly_type=anomaly_type,
        target_input=column,
        direction=direction,
        threshold=threshold,
        occurrence_probability=n_events / n_total if n_total else 0.0,
        magnitude_distribution=_magnitude(series[mask], threshold),
        source=source,
        confidence=base_confidence if base_confidence is not None else _confidence_from_events(n_events, n_total),
        detail={"event_count": n_events, "total": n_total},
    )
    if counter:
        counter[0] += 1
    return scenario


def _detect_runs(df: pd.DataFrame, column: str, runs_length: int, counter: list[int]) -> AnomalyScenario | None:
    series = _clean(df[column])
    if series.size < runs_length:
        return None
    diffs = np.diff(series)
    rising = diffs > 0
    longest = 0
    current = 0
    run_start = 0
    best_start = 0
    for i, up in enumerate(rising):
        if up:
            if current == 0:
                run_start = i
            current += 1
            if current > longest:
                longest = current
                best_start = run_start
        else:
            current = 0
    run_steps = longest + 1
    if run_steps < runs_length:
        return None
    start_value = float(series[best_start])
    end_value = float(series[best_start + longest])
    total_rise = end_value - start_value
    scenario = AnomalyScenario(
        anomaly_id=f"an-{counter[0]}",
        name=f"{column} 連續上升",
        anomaly_type=AnomalyType.CONTROL,
        target_input=column,
        direction=AnomalyDirection.RUN,
        occurrence_probability=run_steps / max(series.size, 1),
        magnitude_distribution={
            "count": int(run_steps),
            "total_rise": float(total_rise),
            "mean_step": float(total_rise / run_steps),
            "start_value": start_value,
            "end_value": end_value,
        },
        source="historical_observation",
        confidence=_confidence_from_events(run_steps, series.size),
        detail={"run_length": int(run_steps), "start_index": int(best_start)},
    )
    counter[0] += 1
    return scenario


def detect_anomaly_scenarios(
    df: pd.DataFrame,
    spec: dict | None = None,
    control_limits: dict[str, dict] | None = None,
    engineering_scenarios: list[dict] | None = None,
    runs_length: int = DEFAULT_RUNS_LENGTH,
) -> list[AnomalyScenario]:
    """Detect all three anomaly families over the dataset.

    Args:
        df: The dataset frame.
        spec: The confirmed spec definition, e.g.
            {"output_field": "temperature", "lsl": 235.0, "usl": 255.0, "target": 245.0}.
        control_limits: Manual LCL/UCL per column, e.g.
            {"temperature": {"lcl": 232.0, "ucl": 258.0}}. Missing entries
            use the data's mean ± 3σ as control limits.
        engineering_scenarios: User-defined templates, each with
            {name, target_input, direction, target, tolerance}.
        runs_length: Minimum sustained rising run that flags a control anomaly.

    Returns:
        List of detected scenarios (spec-first, then control, then runs).
    """
    spec = spec or {}
    control_limits = control_limits or {}
    engineering_scenarios = engineering_scenarios or []
    scenarios: list[AnomalyScenario] = []
    counter = [1]

    # --- Spec anomalies on the output field -------------------------------
    output_field = spec.get("output_field")
    if output_field and output_field in df.columns:
        lsl = spec.get("lsl")
        usl = spec.get("usl")
        if usl is not None:
            scenario = _detect_threshold_anomaly(
                df, output_field, float(usl), AnomalyDirection.ABOVE,
                f"{output_field} 超出上限 (>{usl})", AnomalyType.SPEC, "historical_observation",
                counter=counter,
            )
            if scenario:
                scenarios.append(scenario)
        if lsl is not None:
            scenario = _detect_threshold_anomaly(
                df, output_field, float(lsl), AnomalyDirection.BELOW,
                f"{output_field} 低於下限 (<{lsl})", AnomalyType.SPEC, "historical_observation",
                counter=counter,
            )
            if scenario:
                scenarios.append(scenario)

    # --- Control-limit anomalies on numeric inputs ------------------------
    handled = set()
    for column, limits in (control_limits or {}).items():
        if column not in df.columns:
            continue
        handled.add(column)
        # If neither limit is set, skip automatic inference for that column.
        if limits.get("ucl") is None and limits.get("lcl") is None:
            continue
        series = _clean(df[column])
        if series.size == 0:
            continue
        ucl = limits.get("ucl")
        lcl = limits.get("lcl")
        if ucl is not None:
            scenario = _detect_threshold_anomaly(
                df, column, float(ucl), AnomalyDirection.ABOVE,
                f"{column} 高於管制線 (> {ucl})", AnomalyType.CONTROL, "historical_observation",
                counter=counter,
            )
            if scenario:
                scenarios.append(scenario)
        if lcl is not None:
            scenario = _detect_threshold_anomaly(
                df, column, float(lcl), AnomalyDirection.BELOW,
                f"{column} 低於管制線 (< {lcl})", AnomalyType.CONTROL, "historical_observation",
                counter=counter,
            )
            if scenario:
                scenarios.append(scenario)

    # Auto mean±3σ for numeric columns not covered by manual limits.
    for column in df.columns:
        if not pd.api.types.is_numeric_dtype(df[column]):
            continue
        if column in handled:
            continue
        series = _clean(df[column])
        if series.size < 10:
            continue
        mean = float(series.mean())
        std = float(series.std())
        if std == 0:
            continue
        ucl = mean + CONTROL_SIGMA * std
        lcl = mean - CONTROL_SIGMA * std
        scenario = _detect_threshold_anomaly(
            df, column, ucl, AnomalyDirection.ABOVE,
            f"{column} 高於管制線 (> {ucl:.2f})", AnomalyType.CONTROL, "historical_observation",
            counter=counter, emit_if_zero=False,
        )
        if scenario:
            scenarios.append(scenario)
        scenario = _detect_threshold_anomaly(
            df, column, lcl, AnomalyDirection.BELOW,
            f"{column} 低於管制線 (< {lcl:.2f})", AnomalyType.CONTROL, "historical_observation",
            counter=counter, emit_if_zero=False,
        )
        if scenario:
            scenarios.append(scenario)

    # --- Runs rule (continuous rise) --------------------------------------
    for column in df.columns:
        if not pd.api.types.is_numeric_dtype(df[column]):
            continue
        run_scenario = _detect_runs(df, column, runs_length, counter)
        if run_scenario:
            scenarios.append(run_scenario)

    # --- Engineering deviation templates ----------------------------------
    for template in engineering_scenarios:
        column = template.get("target_input")
        if not column or column not in df.columns:
            continue
        target = template.get("target")
        tolerance = template.get("tolerance", 0.0)
        if target is None or tolerance is None:
            continue
        series = _clean(df[column])
        if series.size == 0:
            continue
        mask = np.abs(series - float(target)) > float(tolerance)
        n_events = int(mask.sum())
        scenario = AnomalyScenario(
            anomaly_id=f"an-{counter[0]}",
            name=template.get("name") or f"{column} 偏離 {target} ± {tolerance}",
            anomaly_type=AnomalyType.ENGINEERING,
            target_input=column,
            direction=AnomalyDirection.DEVIATION,
            target=float(target),
            tolerance=float(tolerance),
            occurrence_probability=n_events / series.size if series.size else 0.0,
            magnitude_distribution=_magnitude(series[mask], float(target)),
            source="engineering_input",
            confidence=ENGINEERING_CONFIDENCE,
            detail={"event_count": n_events, "total": int(series.size)},
        )
        counter[0] += 1
        scenarios.append(scenario)

    return scenarios


def build_analysis_package(
    dataset_id: str,
    source_file: str,
    row_count: int,
    column_count: int,
    field_roles: dict[str, str],
    spec: dict,
    anomalies: list[dict],
    confirmed_roles: set[str] | list[str],
) -> dict:
    """Assemble the analysis data package fingerprint (schema section 11A).

    The package records which parts of the analysis are user-confirmed and
    whether the dataset is complete enough to move to modeling
    (requires at least one output and one input).
    """
    confirmed_roles = set(confirmed_roles)
    confirmed_field_count = len(confirmed_roles)
    missing_requirements: list[str] = []
    if "output" not in set(field_roles.values()):
        missing_requirements.append("output")
    if "input" not in set(field_roles.values()):
        missing_requirements.append("input")
    complete = not missing_requirements

    return {
        "version": 1,
        "dataset_id": dataset_id,
        "data": {
            "source_file": source_file,
            "row_count": int(row_count),
            "column_count": int(column_count),
            "field_roles": dict(field_roles),
            "confirmed_field_count": int(confirmed_field_count),
        },
        "spec": dict(spec or {}),
        "anomalies": list(anomalies or []),
        "complete": complete,
        "missing_requirements": missing_requirements,
    }


__all__ = [
    "AnomalyType",
    "AnomalyDirection",
    "AnomalyScenario",
    "detect_anomaly_scenarios",
    "build_analysis_package",
]