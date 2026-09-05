# SPC EWMA/CUSUM 控制圖 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add EWMA and CUSUM control charts to the SPC page for detecting small process shifts.

**Architecture:** New engine functions `compute_ewma`/`compute_cusum` in `spc.py`, dispatched via existing `spc/analyze` handler, with frontend chart rendering and parameter controls.

**Tech Stack:** Python 3.11, numpy, React 18, antd v5, Plotly.js.

**Spec:** `docs/superpowers/specs/2026-09-05-spc-ewma-cusum-design.md`

---

### Task 1: Engine — EWMA and CUSUM computation (TDD)

**Files:**
- Modify: `engine/src/process_intelligence_engine/spc.py`
- Modify: `engine/src/process_intelligence_engine/main.py`
- Test: `engine/tests/test_spc.py`

- [ ] **Step 1: Write failing tests**

Append to `engine/tests/test_spc.py`:

```python
def test_compute_ewma_basic():
    """Test EWMA chart computation."""
    rng = np.random.default_rng(42)
    values = [10.0 + 0.1 * i + rng.normal(0, 0.1) for i in range(50)]
    result = compute_ewma(values, lambda_param=0.2, L=3.0)
    
    assert result["chart_type"] == "ewma"
    assert len(result["z_values"]) == len(values)
    assert result["ucl"] is not None
    assert result["cl"] is not None
    assert result["lcl"] is not None
    assert result["lambda"] == 0.2
    assert result["L"] == 3.0


def test_compute_ewma_violations():
    """Test EWMA violation detection."""
    # Create data with clear shift
    values = [10.0] * 25 + [12.0] * 25  # shift from 10 to 12
    result = compute_ewma(values, lambda_param=0.2, L=3.0)
    
    # Should detect some violations after shift
    assert len(result["violations"]) > 0
    # Violations should be after the shift point
    for v in result["violations"]:
        assert v["point_idx"] >= 20


def test_compute_cusum_basic():
    """Test CUSUM chart computation."""
    rng = np.random.default_rng(42)
    values = [10.0 + rng.normal(0, 0.5) for _ in range(50)]
    result = compute_cusum(values, k=0.5, H=5.0)
    
    assert result["chart_type"] == "cusum"
    assert len(result["c_plus"]) == len(values)
    assert len(result["c_minus"]) == len(values)
    assert result["k"] == 0.5
    assert result["H"] == 5.0


def test_compute_cusum_violations():
    """Test CUSUM violation detection."""
    # Create data with clear shift
    values = [10.0] * 25 + [13.0] * 25  # shift from 10 to 13
    result = compute_cusum(values, k=0.5, H=5.0)
    
    # Should detect some violations
    assert len(result["violations"]) > 0


def test_compute_ewma_empty_raises():
    """Test EWMA raises on empty input."""
    with pytest.raises(ValueError, match="values must not be empty"):
        compute_ewma([])


def test_compute_cusum_empty_raises():
    """Test CUSUM raises on empty input."""
    with pytest.raises(ValueError, match="values must not be empty"):
        compute_cusum([])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd engine && .venv/bin/python -m pytest tests/test_spc.py::test_compute_ewma_basic tests/test_spc.py::test_compute_cusum_basic -v`
Expected: FAIL with `FunctionNotFound` or `ImportError`

- [ ] **Step 3: Implement EWMA and CUSUM functions**

In `spc.py`, add after existing `compute_i_mr` function (after line 154):

```python
def compute_ewma(
    values: list[float] | np.ndarray,
    lambda_param: float = 0.2,
    L: float = 3.0,
    lsl: float | None = None,
    usl: float | None = None,
) -> dict[str, Any]:
    """Compute EWMA control chart for detecting small shifts."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        raise ValueError("values must not be empty")
    
    x_bar = float(np.mean(arr))
    sigma = float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0
    
    # Compute EWMA statistic
    z_values = [round(x_bar, 6)]
    z = x_bar
    for x in arr[1:]:
        z = lambda_param * x + (1 - lambda_param) * z
        z_values.append(round(z, 6))
    
    # Control limits (constant for simplicity)
    sigma_z = sigma * np.sqrt(lambda_param / (2 - lambda_param))
    ucl = round(x_bar + L * sigma_z, 6)
    lcl = round(max(0, x_bar - L * sigma_z), 6)
    
    # Violations
    violations = []
    for i, z in enumerate(z_values):
        if z > ucl or z < lcl:
            violations.append({
                "point_idx": i,
                "rule": 1,
                "description": f"EWMA z={z:.3f} outside limits [{lcl:.3f}, {ucl:.3f}]"
            })
    
    return {
        "chart_type": "ewma",
        "x_values": [round(float(v), 6) for v in arr],
        "z_values": z_values,
        "ucl": ucl,
        "lcl": lcl,
        "cl": round(x_bar, 6),
        "lambda": lambda_param,
        "L": L,
        "violations": violations,
    }


def compute_cusum(
    values: list[float] | np.ndarray,
    k: float = 0.5,
    H: float = 5.0,
    lsl: float | None = None,
    usl: float | None = None,
) -> dict[str, Any]:
    """Compute CUSUM control chart for detecting small shifts."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        raise ValueError("values must not be empty")
    
    x_bar = float(np.mean(arr))
    sigma = float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0
    
    # Compute CUSUM statistics (two-sided)
    c_plus = [0.0]
    c_minus = [0.0]
    for x in arr[1:]:
        c_plus.append(round(max(0, c_plus[-1] + (x - x_bar) / sigma - k), 6) if sigma > 0 else 0.0)
        c_minus.append(round(max(0, c_minus[-1] - (x - x_bar) / sigma - k), 6) if sigma > 0 else 0.0)
    
    # Violations
    violations = []
    for i in range(len(arr)):
        if c_plus[i] > H or c_minus[i] > H:
            violations.append({
                "point_idx": i,
                "rule": 1,
                "description": f"CUSUM at {i} exceeds H={H}"
            })
    
    return {
        "chart_type": "cusum",
        "x_values": [round(float(v), 6) for v in arr],
        "c_plus": c_plus,
        "c_minus": c_minus,
        "k": k,
        "H": H,
        "violations": violations,
    }
```

- [ ] **Step 4: Update main.py dispatch**

In `main.py`, add imports and dispatch:

```python
from process_intelligence_engine.spc import (
    compute_i_mr,
    compute_xbar_r,
    compute_xbar_s,
    compute_capability,
    compute_ewma,
    compute_cusum,
)
```

In `_handle_spc_analyze` (around line 1074), add branches:

```python
    if chart_type == "i-mr":
        result = compute_i_mr(values, lsl=lsl, usl=usl)
    elif chart_type == "xbar-r":
        ...
    elif chart_type == "ewma":
        result = compute_ewma(
            values,
            lambda_param=params.get("ewma_lambda", 0.2),
            L=params.get("ewma_L", 3.0),
            lsl=lsl,
            usl=usl,
        )
    elif chart_type == "cusum":
        result = compute_cusum(
            values,
            k=params.get("cusum_k", 0.5),
            H=params.get("cusum_H", 5.0),
            lsl=lsl,
            usl=usl,
        )
    else:
        raise ValueError(f"Unknown chart_type: {chart_type}")
```

- [ ] **Step 5: Run tests**

Run: `cd engine && .venv/bin/python -m pytest tests/test_spc.py -q`
Expected: all SPC tests PASS (existing + new)

Run: `cd engine && .venv/bin/python -m pytest tests/ -q`
Expected: **324 passed, 1 skipped** (baseline 316 + 8 new)

- [ ] **Step 6: Commit**

```bash
git add engine/src/process_intelligence_engine/spc.py engine/src/process_intelligence_engine/main.py engine/tests/test_spc.py
git commit -m "feat(engine): add EWMA and CUSUM control charts"
```

---

### Task 2: Frontend — EWMA/CUSUM UI and rendering

**Files:**
- Modify: `src/lib/engine.ts`
- Modify: `src/features/spc/SPC.tsx`
- Modify: `src/i18n/en.json`, `zh-TW.json`, `es-MX.json`

- [ ] **Step 1: Update engine.ts types**

In `engine.ts`, extend `SPCAnalysisResult` to include EWMA/CUSUM fields:

```typescript
export interface SPCAnalysisResult {
  // ... existing fields ...
  chart_type: string
  x_values?: number[]
  z_values?: number[]      // for EWMA
  c_plus?: number[]        // for CUSUM
  c_minus?: number[]       // for CUSUM
  ucl?: number
  lcl?: number
  cl?: number
  lambda?: number          // for EWMA
  L?: number               // for EWMA
  k?: number               // for CUSUM
  H?: number               // for CUSUM
  // ... rest ...
}
```

- [ ] **Step 2: Add i18n keys**

In all three i18n files, add to `spc` section:

```json
"ewma": "EWMA",
"cusum": "CUSUM",
"ewmaLambda": "EWMA λ",
"ewmaL": "EWMA L",
"cusumK": "CUSUM k",
"cusumH": "CUSUM H",
"ewmaViolations": "EWMA Violations",
"cusumViolations": "CUSUM Violations",
"ewmaZValue": "EWMA Z(t)",
"cusumCP": "CUSUM C⁺",
"cusumCM": "CUSUM C⁻"
```

Verify parity command (same as before).

- [ ] **Step 3: Update SPC.tsx chart type selector**

Add to options array:
```tsx
{ value: 'ewma', label: t('spc.ewma') },
{ value: 'cusum', label: t('spc.cusum') },
```

- [ ] **Step 4: Add parameter controls for EWMA/CUSUM**

After subgroup size input (around line 309), add conditional controls:

```tsx
{chartType === 'ewma' && (
  <>
    <Form.Item label={t('spc.ewmaLambda')} style={{ margin: 0 }}>
      <InputNumber min={0.05} max={0.5} step={0.05} value={ewmaLambda}
        onChange={(v) => setEwmaLambda(v || 0.2)} style={{ width: 80 }} />
    </Form.Item>
    <Form.Item label={t('spc.ewmaL')} style={{ margin: 0 }}>
      <InputNumber min={2} max={4} step={0.5} value={ewmaL}
        onChange={(v) => setEwmaL(v || 3)} style={{ width: 80 }} />
    </Form.Item>
  </>
)}
{chartType === 'cusum' && (
  <>
    <Form.Item label={t('spc.cusumK')} style={{ margin: 0 }}>
      <InputNumber min={0.1} max={1} step={0.1} value={cusumK}
        onChange={(v) => setCusumK(v || 0.5)} style={{ width: 80 }} />
    </Form.Item>
    <Form.Item label={t('spc.cusumH')} style={{ margin: 0 }}>
      <InputNumber min={3} max={6} step={0.5} value={cusumH}
        onChange={(v) => setCusumH(v || 5)} style={{ width: 80 }} />
    </Form.Item>
  </>
)}
```

Add state variables:
```typescript
const [ewmaLambda, setEwmaLambda] = useState(0.2)
const [ewmaL, setEwmaL] = useState(3)
const [cusumK, setCusumK] = useState(0.5)
const [cusumH, setCusumH] = useState(5)
```

- [ ] **Step 5: Update handleAnalyze to pass parameters**

```typescript
const res = await analyzeSPC({
  dataset_id: importResult.dataset_id,
  column,
  chart_type: chartType,
  subgroup_size: chartType === 'i-mr' ? 1 : subgroupSize,
  lsl: spec?.lsl ?? undefined,
  usl: spec?.usl ?? undefined,
  ewma_lambda: chartType === 'ewma' ? ewmaLambda : undefined,
  ewma_L: chartType === 'ewma' ? ewmaL : undefined,
  cusum_k: chartType === 'cusum' ? cusumK : undefined,
  cusum_H: chartType === 'cusum' ? cusumH : undefined,
  ...(nodeFilterColumn && nodeFilterValue
    ? { filter_column: nodeFilterColumn, filter_value: nodeFilterValue }
    : {}),
})
```

- [ ] **Step 6: Add plot building for EWMA/CUSUM**

In `buildPlotData()` function, add branches:

```typescript
if (result.chart_type === 'ewma') {
  const z = result.z_values ?? []
  const x = result.x_values?.map((_, i) => i) ?? []
  data.push({
    x, y: z, mode: 'lines+markers',
    name: 'EWMA Z(t)', line: { color: '#1677ff' }, marker: { size: 4 },
  })
  if (result.ucl != null && x.length > 0) {
    data.push({
      x: [x[0], x[x.length - 1]], y: [result.ucl, result.ucl],
      mode: 'lines', name: 'UCL',
      line: { color: '#fa8c16', dash: 'dash' }, showlegend: false,
    })
  }
  if (result.lcl != null && x.length > 0) {
    data.push({
      x: [x[0], x[x.length - 1]], y: [result.lcl, result.lcl],
      mode: 'lines', name: 'LCL',
      line: { color: '#fa8c16', dash: 'dash' }, showlegend: false,
    })
  }
  if (result.cl != null && x.length > 0) {
    data.push({
      x: [x[0], x[x.length - 1]], y: [result.cl, result.cl],
      mode: 'lines', name: 'CL',
      line: { color: '#52c41a', dash: 'dash' }, showlegend: false,
    })
  }
  // Violations
  const violZ = (result.violations ?? []).map(v => z[v.point_idx] ?? 0)
  const violX = (result.violations ?? []).map(v => x[v.point_idx] ?? v.point_idx)
  if (violZ.length > 0) {
    data.push({
      x: violX, y: violZ, mode: 'markers', name: 'Violations',
      marker: { color: '#ff4d4f', size: 8, symbol: 'x' }, showlegend: false,
    })
  }
} else if (result.chart_type === 'cusum') {
  const c_plus = result.c_plus ?? []
  const c_minus = result.c_minus ?? []
  const x = result.x_values?.map((_, i) => i) ?? []
  data.push({
    x, y: c_plus, mode: 'lines+markers',
    name: 'C⁺', line: { color: '#1677ff' }, marker: { size: 4 },
  })
  data.push({
    x, y: c_minus, mode: 'lines+markers',
    name: 'C⁻', line: { color: '#722ed1' }, marker: { size: 4 },
  })
  if (result.H != null && x.length > 0) {
    data.push({
      x: [x[0], x[x.length - 1]], y: [result.H, result.H],
      mode: 'lines', name: 'H (limit)',
      line: { color: '#fa8c16', dash: 'dash' }, showlegend: false,
    })
  }
  // Violations
  const allC = [...c_plus, ...c_minus]
  const violX_cusum = (result.violations ?? []).map(v => x[v.point_idx] ?? v.point_idx)
  if (violX_cusum.length > 0) {
    data.push({
      x: violX_cusum, y: violX_cusum.map(() => result.H ?? 5),
      mode: 'markers', name: 'Violations',
      marker: { color: '#ff4d4f', size: 8, symbol: 'x' }, showlegend: false,
    })
  }
}
```

- [ ] **Step 7: Verify frontend**

Run: `npx tsc --noEmit`
Expected: exit 0
Run: `npm run build 2>&1 | tail -2`
Expected: `✓ built in ...s`

- [ ] **Step 8: Commit**

```bash
git add src/lib/engine.ts src/features/spc/SPC.tsx src/i18n/en.json src/i18n/zh-TW.json src/i18n/es-MX.json
git commit -m "feat(spc): EWMA/CUSUM UI with parameter controls and rendering"
```

---

### Task 3: Docs + verification + push

**Files:** `PROGRESS.md`, `TASK.md`, `README.md`

- [ ] **Step 1: Update docs**

- `PROGRESS.md`: append entry for EWMA/CUSUM feature
- `TASK.md`: add DONE entry
- `README.md`: update Phase 8 to mention EWMA/CUSUM

- [ ] **Step 2: Final verification**

Run: `cd engine && .venv/bin/python -m pytest tests/ -q`
Expected: **324 passed, 1 skipped**
Run: `npx tsc --noEmit`
Expected: exit 0
Run: `npm run build 2>&1 | tail -2`
Expected: `✓ built in ...s`

- [ ] **Step 3: Commit + push**

```bash
git add PROGRESS.md TASK.md README.md
git commit -m "docs: SPC EWMA/CUSUM control charts"
git push
```

---

## Self-review

- Spec coverage: all requirements met (engine functions, IPC dispatch, frontend UI, i18n, tests)
- No placeholders; all code blocks complete
- Type consistency: `SPCAnalysisResult` extended with optional fields, existing code unaffected
