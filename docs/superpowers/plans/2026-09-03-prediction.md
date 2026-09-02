# Phase 10 — 互動預測 (What-if) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add interactive What-if prediction tool — select a trained DOE model, adjust input sliders, see predicted output and NG status in real-time.

**Architecture:** Backend reuses `predict_output()` from `monte_carlo.py`. Frontend renders sliders with live prediction updates using Plotly for a simple gauge chart.

**Tech Stack:** Python 3.11 + NumPy, Tauri IPC, React 18 + Ant Design 5, TypeScript, pytest.

---

## Task 1: 後端預測引擎

**Files:**
- Create: `engine/src/process_intelligence_engine/prediction.py`
- Test: `engine/tests/test_prediction.py`

- [ ] **Step 1: Write the failing test**

Create `engine/tests/test_prediction.py`:

```python
"""Tests for prediction engine."""
import pytest
from process_intelligence_engine.prediction import predict_single, get_input_ranges


def test_predict_single_linear():
    coeffs = {"_intercept": 10.0, "x1": 2.0, "x2": -1.5}
    inputs = {"x1": 100.0, "x2": 50.0}
    result = predict_single("doe_linear", coeffs, inputs)
    expected = 10.0 + 2.0 * 100.0 - 1.5 * 50.0
    assert abs(result - expected) < 0.001


def test_predict_single_quadratic():
    coeffs = {
        "_intercept": 10.0,
        "x1": 2.0,
        "x2": -1.5,
        "x1_x_x1": 0.01,
        "x1_x_x2": 0.02,
    }
    inputs = {"x1": 100.0, "x2": 50.0}
    result = predict_single("doe_quadratic", coeffs, inputs)
    expected = 10.0 + 2.0 * 100.0 - 1.5 * 50.0 + 0.01 * 100.0**2 + 0.02 * 100.0 * 50.0
    assert abs(result - expected) < 0.001


def test_predict_single_missing_coefficient():
    coeffs = {"_intercept": 10.0}
    inputs = {"x1": 5.0}
    result = predict_single("doe_linear", coeffs, inputs)
    assert result == 10.0


def test_get_input_ranges():
    """Test input range calculation from data."""
    import pandas as pd
    import numpy as np
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "x1": rng.normal(100, 5, 100),
        "x2": rng.normal(50, 3, 100),
    })
    ranges = get_input_ranges(df, ["x1", "x2"])
    assert "x1" in ranges
    assert "x2" in ranges
    assert ranges["x1"]["min"] < ranges["x1"]["max"]
    assert ranges["x2"]["min"] < ranges["x2"]["max"]
    assert ranges["x1"]["mean"] == pytest.approx(100.0, abs=5)
    assert ranges["x2"]["mean"] == pytest.approx(50.0, abs=3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && .venv/bin/pytest tests/test_prediction.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

Create `engine/src/process_intelligence_engine/prediction.py`:

```python
"""Interactive prediction engine for What-if analysis."""
from __future__ import annotations

import numpy as np
import pandas as pd


def predict_single(
    model_type: str,
    coefficients: dict[str, float],
    inputs: dict[str, float],
) -> float:
    """Predict a single output value using DOE model coefficients."""
    intercept = coefficients.get("_intercept", 0.0)
    result = intercept

    # Main effects
    for key, val in inputs.items():
        coef = coefficients.get(key, 0.0)
        result += coef * val

    # Interaction effects
    input_keys = list(inputs.keys())
    for i in range(len(input_keys)):
        for j in range(i + 1, len(input_keys)):
            pair_key = f"{input_keys[i]}_x_{input_keys[j]}"
            coef = coefficients.get(pair_key, 0.0)
            result += coef * inputs[input_keys[i]] * inputs[input_keys[j]]
            # Also try compact format
            pair_key2 = f"{input_keys[i]}x{input_keys[j]}"
            coef2 = coefficients.get(pair_key2, 0.0)
            result += coef2 * inputs[input_keys[i]] * inputs[input_keys[j]]

    # Quadratic effects
    for key in input_keys:
        sq_key = f"{key}_x_{key}"
        coef = coefficients.get(sq_key, 0.0)
        result += coef * inputs[key] ** 2
        # Also try compact format
        sq_key2 = f"{key}{key}"
        coef2 = coefficients.get(sq_key2, 0.0)
        result += coef2 * inputs[key] ** 2

    return float(result)


def get_input_ranges(df: pd.DataFrame, input_columns: list[str]) -> dict:
    """Calculate input ranges (min, max, mean, std) from DataFrame."""
    ranges = {}
    for col in input_columns:
        if col not in df.columns:
            continue
        series = df[col].dropna().astype(float)
        if len(series) == 0:
            continue
        ranges[col] = {
            "min": float(series.min()),
            "max": float(series.max()),
            "mean": float(series.mean()),
            "std": float(series.std(ddof=1)) if len(series) > 1 else 0.0,
        }
    return ranges
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd engine && .venv/bin/pytest tests/test_prediction.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run full test suite**

Run: `cd engine && .venv/bin/pytest -q`
Expected: No regressions

- [ ] **Step 6: Commit**

```bash
git add engine/src/process_intelligence_engine/prediction.py engine/tests/test_prediction.py
git commit -m "feat(prediction): add prediction engine with predict_single and get_input_ranges"
```

---

## Task 2: IPC handlers

**Files:**
- Modify: `engine/src/process_intelligence_engine/main.py`
- Test: `engine/tests/test_main_prediction.py`

- [ ] **Step 1: Write the failing test**

Create `engine/tests/test_main_prediction.py`:

```python
"""Tests for prediction IPC handlers."""
import pytest
from process_intelligence_engine.main import handle_request


def _import_csv_for_pred(tmp_path):
    import numpy as np
    rng = np.random.default_rng(42)
    rows = ["x1,x2,y"]
    for _ in range(100):
        x1 = rng.normal(100, 5)
        x2 = rng.normal(50, 3)
        y = 10 + 2 * x1 - 1.5 * x2 + rng.normal(0, 1)
        rows.append(f"{x1:.4f},{x2:.4f},{y:.4f}")
    path = tmp_path / "pred.csv"
    path.write_text("\n".join(rows), encoding="utf-8")
    return handle_request("data/import", {"file_path": str(path)})["dataset_id"]


def _fit_model(tmp_path, did):
    return handle_request("modeling/fit", {
        "dataset_id": did,
        "model_type": "doe_linear",
        "target": "y",
        "inputs": ["x1", "x2"],
    })


def test_prediction_predict_basic(tmp_path):
    did = _import_csv_for_pred(tmp_path)
    fit = _fit_model(tmp_path, did)
    model_id = fit["model_id"]

    result = handle_request("prediction/predict", {
        "model_id": model_id,
        "input_values": {"x1": 100.0, "x2": 50.0},
    })
    assert result["success"]
    assert result["predicted"] is not None
    assert isinstance(result["predicted"], float)
    assert result["equation"] is not None
    assert result["inputs"] == ["x1", "x2"]
    import json
    json.dumps(result)


def test_prediction_predict_unknown_model_raises(tmp_path):
    did = _import_csv_for_pred(tmp_path)
    with pytest.raises(KeyError):
        handle_request("prediction/predict", {
            "model_id": "nonexistent",
            "input_values": {"x1": 100.0},
        })


def test_prediction_model_info(tmp_path):
    did = _import_csv_for_pred(tmp_path)
    fit = _fit_model(tmp_path, did)
    model_id = fit["model_id"]

    result = handle_request("prediction/model_info", {
        "model_id": model_id,
    })
    assert result["success"]
    assert result["model_type"] == "doe_linear"
    assert result["inputs"] == ["x1", "x2"]
    assert result["equation"] is not None
    assert result["n_train"] > 0
    import json
    json.dumps(result)


def test_prediction_model_info_unknown_model_raises():
    with pytest.raises(KeyError):
        handle_request("prediction/model_info", {
            "model_id": "nonexistent",
        })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && .venv/bin/pytest tests/test_main_prediction.py -v`
Expected: FAIL — `ValueError: Unknown method: prediction/predict`

- [ ] **Step 3: Add IPC handlers to main.py**

In `engine/src/process_intelligence_engine/main.py`, add import:

```python
from process_intelligence_engine.prediction import predict_single, get_input_ranges
```

Add handlers before `handle_request`:

```python
def _handle_prediction_predict(params: dict) -> dict:
    """Predict output for given input values."""
    model_id = params["model_id"]
    fit = MODEL_REGISTRY.get(model_id)

    input_values = params.get("input_values", {})
    predicted = predict_single(fit.model_type, fit.coefficients or {}, input_values)

    return {
        "success": True,
        "predicted": float(predicted),
        "equation": fit.equation,
        "inputs": list(fit.inputs),
        "model_type": fit.model_type,
    }


def _handle_prediction_model_info(params: dict) -> dict:
    """Get model info for prediction UI."""
    model_id = params["model_id"]
    fit = MODEL_REGISTRY.get(model_id)

    return {
        "success": True,
        "model_type": fit.model_type,
        "inputs": list(fit.inputs),
        "coefficients": fit.coefficients or {},
        "equation": fit.equation,
        "n_train": fit.n_train,
        "target": fit.target,
    }
```

Add dispatch in `handle_request`:

```python
    if method == "prediction/predict":
        return _handle_prediction_predict(params)
    if method == "prediction/model_info":
        return _handle_prediction_model_info(params)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd engine && .venv/bin/pytest tests/test_main_prediction.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run full test suite**

Run: `cd engine && .venv/bin/pytest -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add engine/src/process_intelligence_engine/main.py engine/tests/test_main_prediction.py
git commit -m "feat(prediction): add prediction/predict and prediction/model_info IPC handlers"
```

---

## Task 3: Frontend API

**Files:**
- Modify: `src/lib/engine.ts`

- [ ] **Step 1: Add Prediction types and functions**

Append to `src/lib/engine.ts`:

```typescript
// --- Phase 10: Interactive Prediction (What-if) --------------------------------

export interface PredictionResult {
  success: boolean
  predicted: number
  equation: string
  inputs: string[]
  model_type: string
}

export interface ModelInfo {
  success: boolean
  model_type: string
  inputs: string[]
  coefficients: Record<string, number>
  equation: string
  n_train: number
  target: string
}

export interface InputRange {
  min: number
  max: number
  mean: number
  std: number
}

export async function predictOutput(params: {
  model_id: string
  input_values: Record<string, number>
}): Promise<PredictionResult> {
  return engineCall<PredictionResult>('prediction/predict', params)
}

export async function getModelInfo(params: {
  model_id: string
}): Promise<ModelInfo> {
  return engineCall<ModelInfo>('prediction/model_info', params)
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add src/lib/engine.ts
git commit -m "feat(prediction): add prediction frontend API types and functions"
```

---

## Task 4: 前端頁面

**Files:**
- Create: `src/features/prediction/Prediction.tsx`
- Modify: `src/App.tsx`
- Modify: `src/components/layout/Sidebar.tsx`
- Modify: `src/i18n/en.json`
- Modify: `src/i18n/zh-TW.json`

- [ ] **Step 1: Add i18n strings**

In `src/i18n/en.json`, add to `nav`:
```json
"prediction": "Interactive Prediction",
```

Add new section:
```json
"prediction": {
  "title": "Interactive Prediction (What-if)",
  "selectModel": "Select Model",
  "noModels": "No trained models yet. Go to Model Center to train one first.",
  "equation": "Equation",
  "inputValue": "Input Value",
  "predictedOutput": "Predicted Output",
  "ngStatus": "NG Status",
  "inSpec": "In Spec",
  "belowLSL": "Below LSL",
  "aboveUSL": "Above USL",
  "distanceToLimit": "Distance to Limit",
  "restoreDefaults": "Restore Defaults",
  "noData": "Please import data first.",
  "selectModelFirst": "Please select a model."
}
```

Same for `src/i18n/zh-TW.json`:
```json
"prediction": {
  "title": "互動預測 (What-if)",
  "selectModel": "選擇模型",
  "noModels": "尚未訓練模型。請先到模型中心訓練。",
  "equation": "方程式",
  "inputValue": "輸入值",
  "predictedOutput": "預測輸出",
  "ngStatus": "規格判定",
  "inSpec": "在規格內",
  "belowLSL": "低於 LSL",
  "aboveUSL": "高於 USL",
  "distanceToLimit": "距離邊界",
  "restoreDefaults": "還原預設值",
  "noData": "請先匯入資料。",
  "selectModelFirst": "請選擇模型。"
}
```

- [ ] **Step 2: Create Prediction.tsx**

Create `src/features/prediction/Prediction.tsx`:

```typescript
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, Select, Space, Button, Alert, Typography, Tag, Slider, InputNumber, Row, Col, Statistic } from 'antd'
import { useDataPipelineStore } from '../../stores/dataPipelineStore'
import { predictOutput, getModelInfo, listModels, type ModelInfo } from '../../lib/engine'

export default function Prediction() {
  const { t } = useTranslation()
  const { importResult, spec } = useDataPipelineStore()

  const [models, setModels] = useState<Array<{ model_id: string; model_type: string; equation: string }>>([])
  const [selectedModel, setSelectedModel] = useState<string | undefined>()
  const [modelInfo, setModelInfo] = useState<ModelInfo | null>(null)
  const [inputValues, setInputValues] = useState<Record<string, number>>({})
  const [predicted, setPredicted] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listModels().then(r => {
      if (r.models) {
        setModels(r.models.map(m => ({ model_id: m.model_id, model_type: m.model_type, equation: m.equation })))
      }
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!selectedModel) {
      setModelInfo(null)
      setInputValues({})
      setPredicted(null)
      return
    }
    getModelInfo({ model_id: selectedModel }).then(r => {
      setModelInfo(r)
      const defaults: Record<string, number> = {}
      if (importResult) {
        const stats = importResult.stats.column_stats
        for (const inp of r.inputs) {
          const s = stats[inp]
          defaults[inp] = s ? (s.mean ?? 0) : 0
        }
      }
      setInputValues(defaults)
    }).catch(() => {})
  }, [selectedModel, importResult])

  useEffect(() => {
    if (!modelInfo || Object.keys(inputValues).length === 0) return
    setLoading(true)
    predictOutput({ model_id: selectedModel!, input_values: inputValues })
      .then(r => setPredicted(r.predicted))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [inputValues, modelInfo, selectedModel])

  const handleInputChange = (key: string, value: number | null) => {
    if (value === null) return
    setInputValues(prev => ({ ...prev, [key]: value }))
  }

  const handleRestore = () => {
    if (!modelInfo || !importResult) return
    const defaults: Record<string, number> = {}
    for (const inp of modelInfo.inputs) {
      const stats = importResult.stats.column_stats[inp]
      defaults[inp] = stats?.mean ?? 0
    }
    setInputValues(defaults)
  }

  const getNgStatus = () => {
    if (predicted === null) return null
    const { lsl, usl } = spec ?? {}
    if (lsl !== null && lsl !== undefined && predicted < lsl) return { text: t('prediction.belowLSL'), color: 'error' as const }
    if (usl !== null && usl !== undefined && predicted > usl) return { text: t('prediction.aboveUSL'), color: 'error' as const }
    return { text: t('prediction.inSpec'), color: 'success' as const }
  }

  const getDistanceToLimit = () => {
    if (predicted === null) return null
    const { lsl, usl } = spec ?? {}
    const dists: string[] = []
    if (lsl !== null && lsl !== undefined) dists.push(`LSL: ${(predicted - lsl).toFixed(2)}`)
    if (usl !== null && usl !== undefined) dists.push(`USL: ${(usl - predicted).toFixed(2)}`)
    return dists.join(' / ')
  }

  const ngStatus = getNgStatus()
  const hasData = !!importResult

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card title={t('prediction.title')}>
        <Space wrap style={{ marginBottom: 12 }}>
          <Select
            value={selectedModel}
            onChange={setSelectedModel}
            options={models.map(m => ({
              value: m.model_id,
              label: `${m.model_type} — ${m.equation.slice(0, 40)}...`,
            }))}
            disabled={models.length === 0}
            style={{ width: 400 }}
            placeholder={t('prediction.noModels')}
          />
          <Button onClick={handleRestore} disabled={!hasData || !modelInfo}>
            {t('prediction.restoreDefaults')}
          </Button>
        </Space>
        {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 12 }} />}
      </Card>

      {modelInfo && (
        <Row gutter={16}>
          <Col span={16}>
            <Card title={t('prediction.equation')} size="small">
              <Typography.Text code style={{ fontSize: 14 }}>{modelInfo.equation}</Typography.Text>
              <div style={{ marginTop: 12 }}>
                {modelInfo.inputs.map(inp => {
                  const stats = importResult?.stats.column_stats[inp]
                  const min = stats?.min ?? (inputValues[inp] ?? 0) - 3 * (stats?.std ?? 5)
                  const max = stats?.max ?? (inputValues[inp] ?? 0) + 3 * (stats?.std ?? 5)
                  const val = inputValues[inp] ?? 0
                  return (
                    <div key={inp} style={{ marginBottom: 12 }}>
                      <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                        <Typography.Text strong>{inp}</Typography.Text>
                        <InputNumber
                          value={val}
                          onChange={v => handleInputChange(inp, v)}
                          precision={2}
                          style={{ width: 100 }}
                          min={min}
                          max={max}
                        />
                      </Space>
                      <Slider
                        min={min}
                        max={max}
                        value={val}
                        onChange={v => handleInputChange(inp, v)}
                        step={(max - min) / 100}
                      />
                      <Space>
                        <Typography.Text type="secondary" style={{ fontSize: 11 }}>Min: {min.toFixed(2)}</Typography.Text>
                        <Typography.Text type="secondary" style={{ fontSize: 11 }}>Mean: {stats?.mean?.toFixed(2) ?? 'N/A'}</Typography.Text>
                        <Typography.Text type="secondary" style={{ fontSize: 11 }}>Max: {max.toFixed(2)}</Typography.Text>
                      </Space>
                    </div>
                  )
                })}
              </div>
            </Card>
          </Col>
          <Col span={8}>
            <Card title={t('prediction.predictedOutput')} size="small" style={{ height: '100%' }}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Statistic
                  title="Predicted Value"
                  value={predicted ?? 0}
                  precision={2}
                  loading={loading}
                />
                {ngStatus && (
                  <Tag color={ngStatus.color} style={{ fontSize: 14, padding: '4px 12px' }}>
                    {ngStatus.text}
                  </Tag>
                )}
                {spec?.lsl !== null && spec?.lsl !== undefined && (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    LSL: {spec.lsl.toFixed(2)}
                  </Typography.Text>
                )}
                {spec?.usl !== null && spec?.usl !== undefined && (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    USL: {spec.usl.toFixed(2)}
                  </Typography.Text>
                )}
                {getDistanceToLimit() && (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {t('prediction.distanceToLimit')}: {getDistanceToLimit()}
                  </Typography.Text>
                )}
              </Space>
            </Card>
          </Col>
        </Row>
      )}

      {!modelInfo && importResult && (
        <Alert type="info" message={t('prediction.selectModelFirst')} showIcon />
      )}
      {!importResult && (
        <Alert type="warning" message={t('prediction.noData')} showIcon />
      )}
    </div>
  )
}
```

- [ ] **Step 3: Wire up in App.tsx**

In `src/App.tsx`, add import and route:
```typescript
import Prediction from './features/prediction/Prediction'
// ...
if (activeTab === 'prediction') return <Prediction />
```

- [ ] **Step 4: Add Prediction tab to Sidebar**

In `src/components/layout/Sidebar.tsx`, add to `tabItems`:
```typescript
{ key: 'prediction', icon: <SlidersOutlined /> },
```
(`SlidersOutlined` is already imported)

- [ ] **Step 5: Verify TypeScript compiles**

Run: `npx tsc --noEmit`
Expected: No errors

- [ ] **Step 6: Build**

Run: `npm run build`
Expected: Build success

- [ ] **Step 7: Run tests**

Run: `cd engine && .venv/bin/pytest -q`
Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
git add engine/src/process_intelligence_engine/prediction.py engine/tests/test_prediction.py engine/src/process_intelligence_engine/main.py engine/tests/test_main_prediction.py src/lib/engine.ts src/features/prediction/Prediction.tsx src/App.tsx src/components/layout/Sidebar.tsx src/i18n/en.json src/i18n/zh-TW.json
git commit -m "feat(prediction): add interactive What-if prediction tool with live sliders"
```

---

## Self-Review

**Spec coverage:**
- [x] Select model from Model Registry
- [x] Sliders + number inputs for each input
- [x] Real-time prediction update
- [x] NG status with LSL/USL comparison
- [x] Model equation display
- [x] Restore defaults button
- [x] IPC handlers (`prediction/predict`, `prediction/model_info`)
- [x] Frontend API (`predictOutput`, `getModelInfo`)
- [x] i18n en/zh-TW
- [x] Tests for engine and IPC

**Scope check:**
- Random Forest / Hybrid NOT included (as specified)
- No prediction intervals (as specified)
- No scenario persistence (as specified)

---

## Verification Commands

```bash
# Backend tests
cd engine && .venv/bin/pytest tests/test_prediction.py tests/test_main_prediction.py -v

# Full test suite
cd engine && .venv/bin/pytest -q

# TypeScript check
npx tsc --noEmit

# Build
npm run build

# Run app
npm run tauri dev
```
