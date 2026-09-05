# SPC 深化 — EWMA / CUSUM 控制圖 — 設計規格 v1.0

日期：2026-09-05
狀態：設計討論中

## 目標

在既有 I-MR / X-bar+R / X-bar+S 控制圖之上，新增 EWMA 與 CUSUM 兩種控制圖類型，
用於檢測製程均值的小幅度漂移（shift detection），與西電規則（WE rules）配合使用。

## 動機

- I-MR / X-bar 對大漂移敏感（3σ 界限），但對小漂移（<1.5σ）反應較慢
- EWMA 用加權移動平均平滑資料，對持續性小漂移更敏感
- CUSUM 累積偏差，對小幅持續偏移最敏感
- 兩者為品質工程標準工具（Montgomery, Introduction to Statistical Quality Control）

## 範圍

### Included

1. **引擎**：新增 `compute_ewma` / `compute_cusum` 函式（spc.py）
2. **IPC**：`spc/analyze` handler 支援新 chart_type
3. **前端**：SPC.tsx 加選單選項 + 繪圖 + 控制參數 UI
4. **TDD**：新增 ~8 支測試
5. **i18n**：spc section 新增 ~10 keys × 3 語系

### Excluded

- EWMA/CUSUM 的能力指數（Cp/Cpk）— 不適用，因兩者非為量測製程變異設計
- EWMA/CUSUM 的自動參數調整（λ, k, H 固定預設，UI 可微調）
- 與 I-MR / X-bar 的整合圖（獨立圖表）

## 設計

### 引擎 — EWMA

```python
def compute_ewma(
    values: list[float] | np.ndarray,
    lambda_param: float = 0.2,
    L: float = 3.0,
    lsl: float | None = None,
    usl: float | None = None,
) -> dict[str, Any]:
    """Compute EWMA control chart."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        raise ValueError("values must not be empty")
    
    x_bar = float(np.mean(arr))
    sigma = float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0
    
    # Compute EWMA statistic
    z_values = [x_bar]
    z = x_bar
    for x in arr[1:]:
        z = lambda_param * x + (1 - lambda_param) * z
        z_values.append(round(z, 6))
    
    # Control limits (time-varying)
    sigma_z = sigma * np.sqrt(lambda_param / (2 - lambda_param))
    ucl = [x_bar + L * sigma_z * np.sqrt(2 * lambda_param / (1 - lambda_param**i) / lambda_param) 
           for i in range(len(z_values))]
    lcl = [max(0, x_bar - L * sigma_z * ...) for ...]  # simplified to constant for now
    # Simpler: constant limits for EWMA
    ucl_const = x_bar + L * sigma_z
    lcl_const = max(0, x_bar - L * sigma_z)
    
    # Violations (points outside limits)
    violations = []
    for i, z in enumerate(z_values):
        if z > ucl_const or z < lcl_const:
            violations.append({"point_idx": i, "rule": 1, "description": f"EWMA {z:.3f} outside limits"})
    
    return {
        "chart_type": "ewma",
        "x_values": [round(float(v), 6) for v in arr],
        "z_values": z_values,
        "ucl": round(ucl_const, 6),
        "lcl": round(lcl_const, 6),
        "cl": round(x_bar, 6),
        "lambda": lambda_param,
        "L": L,
        "violations": violations,
    }
```

### 引擎 — CUSUM

```python
def compute_cusum(
    values: list[float] | np.ndarray,
    k: float = 0.5,
    H: float = 5.0,
    lsl: float | None = None,
    usl: float | None = None,
) -> dict[str, Any]:
    """Compute CUSUM control chart."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        raise ValueError("values must not be empty")
    
    x_bar = float(np.mean(arr))
    sigma = float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0
    
    # Compute CUSUM statistics (two-sided)
    c_plus = [0.0]
    c_minus = [0.0]
    for x in arr[1:]:
        c_plus.append(max(0, c_plus[-1] + (x - x_bar) / sigma - k))
        c_minus.append(max(0, c_minus[-1] - (x - x_bar) / sigma - k))
    
    # Violations
    violations = []
    for i in range(len(arr)):
        if c_plus[i] > H or c_minus[i] > H:
            violations.append({"point_idx": i, "rule": 1, "description": f"CUSUM at {i} exceeds H={H}"})
    
    return {
        "chart_type": "cusum",
        "x_values": [round(float(v), 6) for v in arr],
        "c_plus": [round(v, 6) for v in c_plus],
        "c_minus": [round(v, 6) for v in c_minus],
        "k": k,
        "H": H,
        "violations": violations,
    }
```

### 前端 — SPCCard

在 `SPC.tsx` 的 chart type 選單新增：

```tsx
options={[
  { value: 'i-mr', label: t('spc.iMr') },
  { value: 'xbar-r', label: t('spc.xbarR') },
  { value: 'xbar-s', label: t('spc.xbarS') },
  { value: 'ewma', label: t('spc.ewma') },
  { value: 'cusum', label: t('spc.cusum') },
]}
```

EWMA/CUSUM 時顯示進階參數區：
- EWMA: λ (0.05~0.5, default 0.2), L (2~4, default 3)
- CUSUM: k (0.1~1.0, default 0.5), H (3~6, default 5)

繪圖：
- EWMA: Z_t 線 + 中心線 (μ) + UCL/LCL (橘虛)
- CUSUM: C⁺ 線 + C⁻ 線 + H 界限 (橘虛)

### i18n 新增 keys

| key | en | zh-TW |
|---|---|---|
| `ewma` | EWMA | EWMA |
| `cusum` | CUSUM | CUSUM |
| `ewmaLambda` | EWMA λ | EWMA λ |
| `ewmaL` | EWMA L | EWMA L |
| `cusumK` | CUSUM k | CUSUM k |
| `cusumH` | CUSUM H | CUSUM H |
| `ewmaZValue` | EWMA Z(t) | EWMA Z(t) |
| `cusumCP` | CUSUM C⁺ | CUSUM C⁺ |
| `cusumCM` | CUSUM C⁻ | CUSUM C⁻ |
| `ewmaViolations` | EWMA violations | EWMA 違規 |
| `cusumViolations` | CUSUM violations | CUSUM 違規 |

## 驗證

- 引擎 full suite：新增 ~8 測試 → 316 + 8 = 324 passed
- `npx tsc --noEmit` clean
- `npm run build` 成功
- 三語 `spc` key-set parity ok

## Commit 預期

預計 2-3 commits：
1. `feat(engine): add ewma and cusum control charts`
2. `feat(spc): EWMA/CUSUM UI + i18n`
3. `docs` + push

## Files changed（預期）

- `engine/src/process_intelligence_engine/spc.py`（+compute_ewma, +compute_cusum）
- `engine/src/process_intelligence_engine/main.py`（+dispatch）
- `engine/tests/test_spc.py`（+8 測試）
- `src/features/spc/SPC.tsx`（+選單選項 + 繪圖 + 參數 UI）
- `src/lib/engine.ts`（+SPCAnalysisResult 欄位）
- `src/i18n/en.json`, `zh-TW.json`, `es-MX.json`（+11 keys ×3）
