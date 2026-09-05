# v0.3.0 統計異常偵測 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add IQR/Z-score outlier detection and CUSUM change point detection to the SPC module.

**Architecture:** New functions `detect_outliers()` and `detect_change_points()` in `spc.py`, integrated into `spc/analyze` handler, rendered in SPC.tsx chart traces.

**Tech Stack:** Python 3.11, numpy, React 18, Plotly.js.

**Spec:** `docs/superpowers/specs/2026-09-05-v030-statistical-outlier-detection-design.md`

---

### Task 1: Engine — Outlier and Change Point Detection (TDD)

**Files:**
- Modify: `engine/src/process_intelligence_engine/spc.py`
- Modify: `engine/src/process_intelligence_engine/main.py`
- Test: `engine/tests/test_spc.py`

- [ ] **Step 1: Write failing tests**

Append to `engine/tests/test_spc.py`:

```python
def test_detect_outliers_iqr():
    """Test IQR outlier detection."""
    from process_intelligence_engine.spc import detect_outliers
    values = [10.0] * 50 + [25.0, 26.0, 27.0]  # 3 outliers
    result = detect_outliers(values, method="iqr")
    assert result["method"] == "iqr"
    assert result["n_outliers"] == 3
    assert all(i >= 50 for i in result["outlier_indices"])
    assert "stats" in result
    assert result["stats"]["q1"] is not None


def test_detect_outliers_zscore():
    """Test Z-score outlier detection."""
    from process_intelligence_engine.spc import detect_outliers
    values = [0.0] * 100 + [10.0]  # 1 outlier (z ≈ 10)
    result = detect_outliers(values, method="zscore", zscore_threshold=3.0)
    assert result["method"] == "zscore"
    assert result["n_outliers"] >= 1
    assert len(result["outlier_indices"]) > 0


def test_detect_outliers_empty_raises():
    """Test empty input raises ValueError."""
    from process_intelligence_engine.spc import detect_outliers
    with pytest.raises(ValueError, match="values must not be empty"):
        detect_outliers([])


def test_detect_outliers_constant():
    """Test constant values returns no outliers."""
    from process_intelligence_engine.spc import detect_outliers
    result = detect_outliers([5.0] * 10, method="iqr")
    assert result["n_outliers"] == 0
    assert result["outlier_indices"] == []


def test_detect_change_points_basic():
    """Test CUSUM change point detection."""
    from process_intelligence_engine.spc import detect_change_points
    values = [0.0] * 50 + [5.0] * 50  # shift at index 50
    result = detect_change_points(values, method="cusum", k=0.5, H=5.0)
    assert result["method"] == "cusum"
    assert result["n_change_points"] > 0
    # Change point should be near the shift
    assert any(abs(cp - 50) < 10 for cp in result["change_points"])


def test_detect_change_points_no_shift():
    """Test no change points for constant data."""
    from process_intelligence_engine.spc import detect_change_points
    result = detect_change_points([10.0] * 100, method="cusum")
    assert result["n_change_points"] == 0
    assert result["change_points"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd engine && .venv/bin/python -m pytest tests/test_spc.py::test_detect_outliers_iqr tests/test_spc.py::test_detect_change_points_basic -v`
Expected: FAIL with `ImportError: cannot import name 'detect_outliers'`

- [ ] **Step 3: Implement detect_outliers()**

In `spc.py`, append after existing functions:

```python
def detect_outliers(
    values: list[float] | np.ndarray,
    method: str = "iqr",
    iqr_factor: float = 1.5,
    zscore_threshold: float = 3.0,
) -> dict[str, Any]:
    """Detect statistical outliers using IQR or Z-score method."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        raise ValueError("values must not be empty")
    
    if method == "iqr":
        q1 = float(np.percentile(arr, 25))
        q3 = float(np.percentile(arr, 75))
        iqr = q3 - q1
        lower = q1 - iqr_factor * iqr
        upper = q3 + iqr_factor * iqr
        outlier_mask = (arr < lower) | (arr > upper)
    elif method == "zscore":
        mean = float(np.mean(arr))
        std = float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0
        if std == 0:
            return {"outlier_indices": [], "n_outliers": 0, "method": method, "stats": {}}
        zscores = np.abs((arr - mean) / std)
        outlier_mask = zscores > zscore_threshold
    else:
        raise ValueError(f"Unknown method: {method}")
    
    outlier_indices = np.where(outlier_mask)[0].tolist()
    stats: dict[str, Any] = {
        "mean": round(float(np.mean(arr)), 6),
        "std": round(float(np.std(arr, ddof=1)), 6) if arr.size > 1 else 0.0,
    }
    if method == "iqr":
        stats.update({
            "q1": round(q1, 6),
            "q3": round(q3, 6),
            "iqr": round(iqr, 6),
            "lower_fence": round(lower, 6),
            "upper_fence": round(upper, 6),
        })
    
    return {
        "outlier_indices": outlier_indices,
        "n_outliers": len(outlier_indices),
        "method": method,
        "stats": stats,
    }
```

- [ ] **Step 4: Implement detect_change_points()**

Append to `spc.py`:

```python
def detect_change_points(
    values: list[float] | np.ndarray,
    method: str = "cusum",
    k: float = 0.5,
    H: float = 5.0,
) -> dict[str, Any]:
    """Detect change points using CUSUM statistic."""
    arr = np.asarray(values, dtype=float)
    if arr.size < 10:
        return {"change_points": [], "n_change_points": 0, "method": method}
    
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0
    if std == 0:
        return {"change_points": [], "n_change_points": 0, "method": method}
    
    c_plus = [0.0]
    c_minus = [0.0]
    change_points = []
    
    for i, x in enumerate(arr[1:], start=1):
        c_plus.append(round(max(0, c_plus[-1] + (x - mean) / std - k), 6))
        c_minus.append(round(max(0, c_minus[-1] - (x - mean) / std - k), 6))
        if c_plus[-1] > H or c_minus[-1] > H:
            change_points.append(i)
    
    return {
        "change_points": change_points,
        "n_change_points": len(change_points),
        "method": method,
        "cusum_max_plus": round(c_plus[-1], 6),
        "cusum_max_minus": round(c_minus[-1], 6),
    }
```

- [ ] **Step 5: Integrate into spc/analyze handler**

In `main.py`, find `_handle_spc_analyze` (around line 1089) and add after computing result:

```python
    # Detect outliers and change points
    from process_intelligence_engine.spc import detect_outliers, detect_change_points
    outlier_result = detect_outliers(values)
    change_point_result = detect_change_points(values)
    result["outlier_indices"] = outlier_result["outlier_indices"]
    result["change_points"] = change_point_result["change_points"]
    result["outlier_stats"] = outlier_result["stats"]
```

- [ ] **Step 6: Run tests and commit**

Run: `cd engine && .venv/bin/python -m pytest tests/test_spc.py -q`
Expected: all SPC tests PASS (existing + 6 new)

Run: `cd engine && .venv/bin/python -m pytest tests/ -q`
Expected: **345+ passed, 1 skipped**

```bash
git add engine/src/process_intelligence_engine/spc.py engine/src/process_intelligence_engine/main.py engine/tests/test_spc.py
git commit -m "feat(engine): statistical outlier and change point detection"
```

---

### Task 2: Frontend — Render outliers and change points

**Files:**
- Modify: `src/lib/engine.ts`
- Modify: `src/features/spc/SPC.tsx`
- Modify: `src/i18n/en.json`, `zh-TW.json`, `es-MX.json`

- [ ] **Step 1: Update SPCAnalysisResult type**

In `engine.ts`, add to `SPCAnalysisResult` interface (after existing fields):

```typescript
  outlier_indices?: number[]
  change_points?: number[]
  outlier_stats?: Record<string, number>
```

- [ ] **Step 2: Add i18n keys**

In all three i18n files, add to `spc` section:

```json
"outliers": "Outliers",
"changePoints": "Change Points",
"outlierIQR": "IQR Outliers",
"outlierZscore": "Z-score Outliers",
"detectOutliers": "Detect Outliers",
"detectChangePoints": "Detect Change Points"
```

Verify parity:
```bash
python3 -c "import json; ks=[set(json.load(open('src/i18n/%s.json'%f))['spc']) for f in ('en','zh-TW','es-MX')]; print('parity ok:', ks[0]==ks[1]==ks[2], 'count:', len(ks[0]))"
```
Expected: `parity ok: True count: 62`

- [ ] **Step 3: Add trace rendering in SPC.tsx**

In `buildPlotData()`, after the violations trace block, add:

```typescript
// Outlier markers (blue circles)
if (result.outlier_indices && result.outlier_indices.length > 0) {
  const ox = result.outlier_indices
  const oy = result.chart_type === 'i-mr'
    ? result.x_values?.filter((_, i) => ox.includes(i)) ?? []
    : result.xbar_values?.filter((_, i) => ox.includes(i)) ?? []
  data.push({
    x: ox, y: oy, mode: 'markers',
    name: t('spc.outliers'),
    marker: { color: '#1677ff', size: 10, symbol: 'circle' },
    showlegend: true,
  })
}

// Change point markers (green triangles)
if (result.change_points && result.change_points.length > 0) {
  const cx = result.change_points
  const cy = result.chart_type === 'i-mr'
    ? result.x_values?.filter((_, i) => cx.includes(i)) ?? []
    : result.xbar_values?.filter((_, i) => cx.includes(i)) ?? []
  data.push({
    x: cx, y: cy, mode: 'markers',
    name: t('spc.changePoints'),
    marker: { color: '#52c41a', size: 12, symbol: 'triangle-up' },
    showlegend: true,
  })
}
```

- [ ] **Step 4: Verify frontend**

Run: `npx tsc --noEmit`
Expected: exit 0
Run: `npm run build 2>&1 | tail -2`
Expected: `✓ built in ...s`

- [ ] **Step 5: Commit**

```bash
git add src/lib/engine.ts src/features/spc/SPC.tsx src/i18n/en.json src/i18n/zh-TW.json src/i18n/es-MX.json
git commit -m "feat(spc): render outliers and change points in charts"
```

---

### Task 3: Docs + verification + push

**Files:** `PROGRESS.md`, `TASK.md`, `README.md`

- [ ] **Step 1: Update docs**
  - `PROGRESS.md`: append v0.3.0 outlier detection section
  - `TASK.md`: add DONE entry
  - `README.md`: update SPC section to mention outlier detection

- [ ] **Step 2: Final verification**
  ```bash
  cd engine && .venv/bin/python -m pytest tests/ -q
  npx tsc --noEmit
  npm run build 2>&1 | tail -2
  ```

- [ ] **Step 3: Commit + push**
  ```bash
  git add PROGRESS.md TASK.md README.md
  git commit -m "docs: v0.3.0 statistical outlier detection"
  git push
  ```

---

## Self-review

- Spec coverage: outlier detection ✅, change point detection ✅, frontend rendering ✅, i18n ✅
- No placeholders; all code blocks complete
- Type consistency: `SPCAnalysisResult` extended with optional fields matching engine return shape
