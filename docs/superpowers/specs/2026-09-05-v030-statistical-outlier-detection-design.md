# v0.3.0 統計異常偵測增強 — 設計規格 v1.0

日期：2026-09-05
狀態：設計討論中

## 目標

在既有 SPC 控制圖之上，新增統計異常偵測功能：
1. **IQR/Z-score 離群值檢測**：自動標記統計異常點
2. **CUSUM 改變點偵測**：基於 CUSUM 統計量檢測製程偏移點

## 範圍

### Included
1. 引擎：`spc.py` 新增 `detect_outliers()` 和 `detect_change_points()` 函式
2. 引擎：`spc/analyze` handler 回傳 `outlier_indices` 和 `change_points`
3. 前端：SPC 圖表顯示離群值標記（藍色圓點）和改變點標記（綠色三角）
4. 前端：新增「統計異常」圖例說明
5. i18n：~6 keys × 3 語系
6. TDD：~6 支測試

### Excluded
- Isolation Forest（需要額外訓練，暫不納入）
- 多變數聯合異常偵測（後續版本）
- 自動通知/告警系統（後續版本）

## 設計

### 1. 引擎 — 離群值檢測

`spc.py` 新增：
```python
def detect_outliers(
    values: list[float] | np.ndarray,
    method: str = "iqr",  # "iqr" or "zscore"
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
            return {"outlier_indices": [], "stats": {}}
        zscores = np.abs((arr - mean) / std)
        outlier_mask = zscores > zscore_threshold
    else:
        raise ValueError(f"Unknown method: {method}")
    
    outlier_indices = np.where(outlier_mask)[0].tolist()
    return {
        "outlier_indices": outlier_indices,
        "n_outliers": len(outlier_indices),
        "method": method,
        "stats": {
            "mean": round(float(np.mean(arr)), 6),
            "std": round(float(np.std(arr, ddof=1)), 6) if arr.size > 1 else 0.0,
            "q1": round(q1, 6) if method == "iqr" else None,
            "q3": round(q3, 6) if method == "iqr" else None,
            "iqr": round(iqr, 6) if method == "iqr" else None,
            "lower_fence": round(lower, 6) if method == "iqr" else None,
            "upper_fence": round(upper, 6) if method == "iqr" else None,
        },
    }
```

### 2. 引擎 — 改變點偵測

`spc.py` 新增：
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
        return {"change_points": [], "n_change_points": 0}
    
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof(1))) if arr.size > 1 else 0.0
    if std == 0:
        return {"change_points": [], "n_change_points": 0}
    
    # Compute CUSUM
    c_plus = [0.0]
    c_minus = [0.0]
    change_points = []
    
    for i, x in enumerate(arr[1:], start=1):
        c_plus.append(max(0, c_plus[-1] + (x - mean) / std - k))
        c_minus.append(max(0, c_minus[-1] - (x - mean) / std - k))
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

### 3. 引擎 — 整合到 spc/analyze

在 `_handle_spc_analyze` 中，計算完結果後新增：
```python
# Detect outliers and change points
outlier_result = detect_outliers(values, method="iqr")
change_point_result = detect_change_points(values, method="cusum")

result["outlier_indices"] = outlier_result["outlier_indices"]
result["change_points"] = change_point_result["change_points"]
result["outlier_stats"] = outlier_result["stats"]
```

### 4. 前端 — SPC 圖表渲染

在 `buildPlotData()` 中，新增離群值和改變點 trace：

```typescript
// Outlier markers (blue circles)
if (result.outlier_indices && result.outlier_indices.length > 0) {
  const outlierX = result.outlier_indices
  const outlierY = (result.chart_type === 'i-mr' 
    ? result.x_values 
    : result.xbar_values)?.map((_, i) => result.z_values?.[i] ?? result.xbar_values?.[i]) ?? []
  data.push({
    x: outlierX, y: outlierY, mode: 'markers',
    name: 'Outliers',
    marker: { color: '#1677ff', size: 10, symbol: 'circle' },
    showlegend: true,
  })
}

// Change point markers (green triangles)
if (result.change_points && result.change_points.length > 0) {
  const cpX = result.change_points
  const cpY = (result.chart_type === 'i-mr' ? result.x_values : result.xbar_values)
    ?.map((v, i) => cpX.includes(i) ? v : undefined)
    .filter(v => v !== undefined)
  data.push({
    x: cpX, y: cpY, mode: 'markers',
    name: 'Change Points',
    marker: { color: '#52c41a', size: 12, symbol: 'triangle-up' },
    showlegend: true,
  })
}
```

### 5. i18n 新增 keys

| key | en | zh-TW |
|---|---|---|
| `outliers` | Outliers | 離群值 |
| `changePoints` | Change Points | 改變點 |
| `outlierIQR` | IQR Outliers | IQR 離群值 |
| `outlierZscore` | Z-score Outliers | Z-score 離群值 |
| `detectOutliers` | Detect Outliers | 偵測離群值 |
| `detectChangePoints` | Detect Change Points | 偵測改變點 |

## 驗證

- 引擎 full suite：新增 ~6 測試 → 345+ passed
- `npx tsc --noEmit` clean
- `npm run build` 成功
- 三語 `spc` key-set parity ok

## Commit 預期

預計 2-3 commits：
1. `feat(engine): statistical outlier and change point detection`
2. `feat(spc): render outliers and change points in charts`
3. `docs` + push

## Files changed（預期）

- `engine/src/process_intelligence_engine/spc.py`（+detect_outliers, +detect_change_points）
- `engine/src/process_intelligence_engine/main.py`（+整合到 spc/analyze）
- `engine/tests/test_spc.py`（+6 測試）
- `src/features/spc/SPC.tsx`（+離群值/改變點 trace）
- `src/i18n/en.json`, `zh-TW.json`, `es-MX.json`（+6 keys ×3）
