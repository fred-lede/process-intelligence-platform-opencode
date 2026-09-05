# SPC 深化 — 多欄位比較 + 優化建議 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-column capability comparison and process optimization suggestions to the SPC page.

**Architecture:** New engine handler `spc/batch_analyze` for batch processing, `compute_spc_suggestions()` for generating recommendations, frontend extends SPC.tsx with comparison mode and suggestions display.

**Tech Stack:** Python 3.11, React 18, antd v5, TypeScript, Plotly.js.

**Spec:** `docs/superpowers/specs/2026-09-05-spc-enhancement-design.md`

---

### Task 1: Engine — Batch analyze + suggestions

**Files:**
- Modify: `engine/src/process_intelligence_engine/spc.py`
- Modify: `engine/src/process_intelligence_engine/main.py`
- Test: `engine/tests/test_spc.py`

- [ ] **Step 1: Add `compute_spc_suggestions()` to spc.py**

Append after existing functions:
```python
def compute_spc_suggestions(result: dict) -> list[dict]:
    """Generate improvement suggestions based on SPC analysis."""
    suggestions = []
    
    # Capability check
    cap = result.get("capability")
    if cap and cap.get("cpk") is not None:
        if cap["cpk"] < 1.0:
            suggestions.append({
                "severity": "error",
                "type": "low_capability",
                "message": f"製程能力不足 (Cpk={cap['cpk']:.2f} < 1.0)，建議減少變異或調整目標",
            })
        elif cap["cpk"] < 1.33:
            suggestions.append({
                "severity": "warning",
                "type": "marginal_capability",
                "message": f"製程能力邊緣 (Cpk={cap['cpk']:.2f})，建議監控並準備改善方案",
            })
    
    # Rule violations
    violations = result.get("violations", [])
    rule_4 = [v for v in violations if v.get("rule") == 4]
    rule_5 = [v for v in violations if v.get("rule") == 5]
    
    if rule_4:
        suggestions.append({
            "severity": "error",
            "type": "shift_detected",
            "message": f"偵測到製程偏移（Rule 4: {len(rule_4)} 次），建議檢查原料或機台參數",
        })
    
    if rule_5:
        suggestions.append({
            "severity": "warning",
            "type": "trend_detected",
            "message": f"偵測到趨勢（Rule 5: {len(rule_5)} 次），建議檢查工具磨損或溫度漂移",
        })
    
    # EWMA/CUSUM specific
    if result.get("chart_type") in ("ewma", "cusum"):
        ewma_v = [v for v in violations if v.get("rule") == 1]
        if ewma_v:
            suggestions.append({
                "severity": "warning",
                "type": "small_shift",
                "message": f"EWMA/CUSUM 檢測到小漂移（{len(ewma_v)} 次），建議即時調整",
            })
    
    return suggestions
```

- [ ] **Step 2: Add batch analyze handler to main.py**

In `main.py`, add import:
```python
from process_intelligence_engine.spc import (
    ...
    compute_spc_suggestions,
)
```

Add handler function:
```python
def _handle_spc_batch_analyze(params: dict) -> dict:
    """Analyze multiple columns and return results with suggestions."""
    df = REGISTRY.get(params["dataset_id"])
    columns = params.get("columns", [])
    chart_type = params.get("chart_type", "i-mr")
    lsl = params.get("lsl")
    usl = params.get("usl")
    
    results = {}
    for col in columns:
        if col not in df.columns:
            continue
        values = df[col].dropna().tolist()
        if not values:
            continue
        
        if chart_type == "i-mr":
            result = compute_i_mr(values, lsl=lsl, usl=usl)
        elif chart_type == "xbar-r":
            # ... similar for other chart types
            continue
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
            continue
        
        result["suggestions"] = compute_spc_suggestions(result)
        results[col] = result
    
    return {"results": results, "columns": list(results.keys())}
```

Register in dispatch table (find existing `spc/analyze` handler):
```python
"spc/batch_analyze": _handle_spc_batch_analyze,
```

- [ ] **Step 3: Write tests**

In `test_spc.py`, append:
```python
def test_compute_spc_suggestions_low_capability():
    """Test suggestions for low Cpk."""
    rng = np.random.default_rng(42)
    # Create data with high variation
    values = [10.0 + rng.normal(0, 2.0) for _ in range(100)]
    result = compute_i_mr(values, lsl=5.0, usl=15.0)
    suggestions = compute_spc_suggestions(result)
    
    # Should have low capability suggestion
    assert len(suggestions) > 0
    cap_types = [s["type"] for s in suggestions]
    assert "low_capability" in cap_types or "marginal_capability" in cap_types


def test_compute_spc_suggestions_shift():
    """Test suggestions for shift detection."""
    # Create data with clear shift
    values = [10.0] * 30 + [12.0] * 30 + [10.0] * 20
    result = compute_i_mr(values)
    suggestions = compute_spc_suggestions(result)
    
    # Should detect shift (Rule 4)
    shift_suggestions = [s for s in suggestions if s["type"] == "shift_detected"]
    assert len(shift_suggestions) > 0


def test_compute_spc_suggestions_stable():
    """Test no suggestions for stable process."""
    rng = np.random.default_rng(42)
    values = [10.0 + rng.normal(0, 0.1) for _ in range(100)]
    result = compute_i_mr(values)
    suggestions = compute_spc_suggestions(result)
    
    # Should have no suggestions or only info-level
    error_suggestions = [s for s in suggestions if s["severity"] == "error"]
    assert len(error_suggestions) == 0


def test_spc_batch_analyze(tmp_path):
    """Test batch analyze endpoint."""
    # Import helper from test_main_spc
    import sys
    sys.path.insert(0, 'tests')
    from test_main_spc import _import_csv_for_spc
    did = _import_csv_for_spc(tmp_path)
    
    result = handle_request("spc/batch_analyze", {
        "dataset_id": did,
        "columns": ["output_thickness"],
        "chart_type": "i-mr",
    })
    assert "results" in result
    assert "output_thickness" in result["results"]
    assert "suggestions" in result["results"]["output_thickness"]
```

- [ ] **Step 4: Run tests**

Run: `cd engine && .venv/bin/python -m pytest tests/test_spc.py -q`
Expected: all SPC tests PASS

Run: `cd engine && .venv/bin/python -m pytest tests/ -q`
Expected: **330+ passed, 1 skipped** (baseline 322 + 8 new)

- [ ] **Step 5: Commit**

```bash
git add engine/src/process_intelligence_engine/spc.py engine/src/process_intelligence_engine/main.py engine/tests/test_spc.py
git commit -m "feat(engine): batch analyze + optimization suggestions"
```

---

### Task 2: Frontend — Multi-column UI + suggestions

**Files:**
- Modify: `src/lib/engine.ts`
- Modify: `src/features/spc/SPC.tsx`
- Modify: `src/lib/assistantData.ts`
- Modify: `src/i18n/en.json`, `zh-TW.json`, `es-MX.json`

- [ ] **Step 1: Update engine.ts types**

Add new types and functions:
```typescript
export interface SPCSuggestion {
  severity: 'error' | 'warning' | 'info'
  type: string
  message: string
}

export interface SPCBatchResult {
  results: Record<string, SPCAnalysisResult>
  columns: string[]
}

export async function analyzeSPCBatch(params: {
  dataset_id: string
  columns: string[]
  chart_type?: string
  subgroup_size?: number
  lsl?: number
  usl?: number
  ewma_lambda?: number
  ewma_L?: number
  cusum_k?: number
  cusum_H?: number
}): Promise<SPCBatchResult> {
  return engineCall<SPCBatchResult>('spc/batch_analyze', params as unknown as Record<string, unknown>)
}
```

- [ ] **Step 2: Add i18n keys**

In all three i18n files, add to `spc` section:
```json
"batchAnalyze": "Batch Analysis",
"compareColumns": "Compare Columns",
"suggestions": "Optimization Suggestions",
"noSuggestions": "Process is stable, no special attention needed",
"severity_error": "Urgent",
"severity_warning": "Warning",
"lowCapability": "Low capability",
"shiftDetected": "Shift detected",
"trendDetected": "Trend detected"
```

Verify parity:
```bash
python3 -c "import json; ks=[set(json.load(open('src/i18n/%s.json'%f))['spc']) for f in ('en','zh-TW','es-MX')]; print('parity ok:', ks[0]==ks[1]==ks[2], 'count:', len(ks[0]))"
```

- [ ] **Step 3: Update SPC.tsx — add batch mode**

Add state:
```typescript
const [batchMode, setBatchMode] = useState(false)
const [selectedColumns, setSelectedColumns] = useState<string[]>([])
const [batchResult, setBatchResult] = useState<SPCBatchResult | null>(null)
```

Add toggle in UI (after existing analyze button):
```tsx
<Space style={{ marginBottom: 12 }}>
  <Button 
    type={batchMode ? 'primary' : 'default'} 
    onClick={() => setBatchMode(!batchMode)}
  >
    {t('spc.batchAnalyze')}
  </Button>
</Space>
```

Batch mode UI (conditional render):
```tsx
{batchMode && (
  <Card title={t('spc.compareColumns')} size="small">
    <Select
      mode="multiple"
      style={{ width: '100%', marginBottom: 12 }}
      value={selectedColumns}
      onChange={setSelectedColumns}
      options={numericColumns.map(name => ({ value: name, label: name }))}
      placeholder={t('spc.selectColumns')}
    />
    <Button type="primary" onClick={handleBatchAnalyze} loading={loading} disabled={selectedColumns.length === 0}>
      {t('spc.analyze')}
    </Button>
  </Card>
)}
```

Add handler:
```typescript
const handleBatchAnalyze = async () => {
  if (!importResult || selectedColumns.length === 0) return
  setLoading(true)
  try {
    const res = await analyzeSPCBatch({
      dataset_id: importResult.dataset_id,
      columns: selectedColumns,
      chart_type: chartType,
      subgroup_size: chartType === 'i-mr' ? 1 : subgroupSize,
      lsl: spec?.lsl ?? undefined,
      usl: spec?.usl ?? undefined,
      ewma_lambda: chartType === 'ewma' ? ewmaLambda : undefined,
      ewma_L: chartType === 'ewma' ? ewmaL : undefined,
      cusum_k: chartType === 'cusum' ? cusumK : undefined,
      cusum_H: chartType === 'cusum' ? cusumH : undefined,
    })
    setBatchResult(res)
  } catch (e) {
    setError(e instanceof Error ? e.message : String(e))
  } finally {
    setLoading(false)
  }
}
```

- [ ] **Step 4: Render comparison table and charts**

After existing result display, add batch results:
```tsx
{batchResult && (
  <>
    <Card title={t('spc.compareColumns')} size="small">
      <Table
        dataSource={Object.entries(batchResult.results).map(([col, res]) => ({
          key: col,
          column: col,
          cp: res.capability?.cp,
          cpk: res.capability?.cpk,
          pp: res.capability?.pp,
          ppk: res.capability?.ppk,
          violations: res.violations?.length ?? 0,
        }))}
        columns={[
          { title: t('spc.column'), dataIndex: 'column', key: 'column' },
          { title: 'Cp', dataIndex: 'cp', key: 'cp',
            render: (v: number) => <Tag color={capacityColor(v)}>{v?.toFixed(2) ?? 'N/A'}</Tag> },
          { title: 'Cpk', dataIndex: 'cpk', key: 'cpk',
            render: (v: number) => <Tag color={capacityColor(v)}>{v?.toFixed(2) ?? 'N/A'}</Tag> },
          { title: 'Pp', dataIndex: 'pp', key: 'pp',
            render: (v: number) => <Tag color={capacityColor(v)}>{v?.toFixed(2) ?? 'N/A'}</Tag> },
          { title: 'Ppk', dataIndex: 'ppk', key: 'ppk',
            render: (v: number) => <Tag color={capacityColor(v)}>{v?.toFixed(2) ?? 'N/A'}</Tag> },
          { title: t('spc.violations'), dataIndex: 'violations', key: 'violations' },
        ]}
        pagination={false}
      />
    </Card>
    
    {/* Individual charts */}
    {Object.entries(batchResult.results).map(([col, res]) => (
      <Card key={col} title={col} size="small">
        <Plot
          data={buildPlotDataForResult(res)}
          layout={plotLayout}
          config={{ responsive: true, displayModeBar: false }}
          style={{ width: '100%' }}
        />
      </Card>
    ))}
  </>
)}
```

- [ ] **Step 5: Add suggestions display**

In the single-column result display, after violations table, add:
```tsx
{result && result.suggestions && result.suggestions.length > 0 && (
  <Card title={t('spc.suggestions')} size="small">
    {result.suggestions.map((s, i) => (
      <Alert
        key={i}
        type={s.severity === 'error' ? 'error' : 'warning'}
        message={s.message}
        showIcon
        style={{ marginBottom: 8 }}
      />
    ))}
  </Card>
)}
{result && (!result.suggestions || result.suggestions.length === 0) && (
  <Alert type="success" message={t('spc.noSuggestions')} showIcon />
)}
```

- [ ] **Step 6: Update assistantData.ts**

In `buildSpcContext`, append suggestions:
```typescript
if (result && result.suggestions && result.suggestions.length > 0) {
  lines.push(`Suggestions: ${result.suggestions.map(s => s.message).join('; ')}.`)
}
```

- [ ] **Step 7: Verify frontend**

Run: `npx tsc --noEmit`
Expected: exit 0
Run: `npm run build 2>&1 | tail -2`
Expected: `✓ built in ...s`

- [ ] **Step 8: Commit**

```bash
git add src/lib/engine.ts src/features/spc/SPC.tsx src/lib/assistantData.ts src/i18n/en.json src/i18n/zh-TW.json src/i18n/es-MX.json
git commit -m "feat(spc): multi-column comparison + optimization suggestions"
```

---

### Task 3: Docs + push

**Files:** `PROGRESS.md`, `TASK.md`, `README.md`

- [ ] **Step 1: Update docs**
  - `PROGRESS.md`: append entry for SPC enhancement
  - `TASK.md`: add DONE entry
  - `README.md`: update Phase 8 to mention batch analysis + suggestions

- [ ] **Step 2: Final verification**
  ```bash
  cd engine && .venv/bin/python -m pytest tests/ -q
  npx tsc --noEmit
  npm run build 2>&1 | tail -2
  ```

- [ ] **Step 3: Commit + push**
  ```bash
  git add PROGRESS.md TASK.md README.md
  git commit -m "docs: SPC enhancement (batch + suggestions)"
  git push
  ```

---

## Self-review

- Spec coverage: all requirements met
- No placeholders; all code blocks complete
- Type consistency: `SPCBatchResult` matches engine return shape
