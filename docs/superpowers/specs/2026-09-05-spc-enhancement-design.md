# SPC 深化 — 多欄位比較 + 優化建議 — 設計規格 v1.0

日期：2026-09-05
狀態：設計討論中

## 目標

在既有 SPC 功能之上，新增：
1. **多欄位能力比較**：一次分析多個 output 欄位，並排顯示能力指數與控制圖
2. **製程優化建議**：基於 SPC 結果自動產生改善建議

## 範圍

### Feature A: 多欄位能力比較

**Included:**
- 引擎：`spc/batch_analyze` handler，接受 `columns: string[]`，回傳每個欄位的 `SPCAnalysisResult`
- 前端：SPC 頁新增「多欄位分析」模式（toggle 或獨立區段）
- 並排顯示：能力卡片表格 + 各欄位控制圖（可捲動）
- i18n: ~8 keys

**Excluded:**
- 跨欄位統計比較（如 ANOVA）
- 匯出比較報告

### Feature B: 製程優化建議

**Included:**
- 引擎：`compute_spc_suggestions(result)` 函式，分析 violated rules / capability / trend
- 建議規則：
  - Cpk < 1.0 → "製程能力不足，建議減少變異或調整目標"
  - Rule 4 violation (8 points one side) → "偵測到製程偏移，建議檢查原料或機台參數"
  - Rule 5 violation (6 points trending) → "偵測到趨勢，建議檢查工具磨損或溫度漂移"
  - EWMA/CUSUM 違規 → "檢測到小漂移，建議即時調整"
- 前端：顯示建議卡片（紅色= urgent，橘色= warning，綠色= info）
- AI context: 包含建議摘要

**Excluded:**
- 自動調整機台參數
- 預測性維護

## 設計

### 引擎 — 多欄位批次分析

`main.py` 新增 handler：
```python
def _handle_spc_batch_analyze(params: dict) -> dict:
    df = REGISTRY.get(params["dataset_id"])
    columns = params.get("columns", [])
    chart_type = params.get("chart_type", "i-mr")
    results = {}
    for col in columns:
        values = df[col].dropna().tolist()
        if chart_type == "i-mr":
            results[col] = compute_i_mr(values, lsl=params.get("lsl"), usl=params.get("usl"))
        elif chart_type == "ewma":
            results[col] = compute_ewma(values, lambda_param=params.get("ewma_lambda", 0.2),
                                        L=params.get("ewma_L", 3.0), lsl=params.get("lsl"), usl=params.get("usl"))
        # ... similar for other chart types
    return {"results": results}
```

### 引擎 — 優化建議

`spc.py` 新增：
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
    rule_4_violations = [v for v in violations if v.get("rule") == 4]
    rule_5_violations = [v for v in violations if v.get("rule") == 5]
    
    if rule_4_violations:
        suggestions.append({
            "severity": "error",
            "type": "shift_detected",
            "message": f"偵測到製程偏移（Rule 4: {len(rule_4_violations)} 次），建議檢查原料或機台參數",
        })
    
    if rule_5_violations:
        suggestions.append({
            "severity": "warning",
            "type": "trend_detected",
            "message": f"偵測到趨勢（Rule 5: {len(rule_5_violations)} 次），建議檢查工具磨損或溫度漂移",
        })
    
    # EWMA/CUSUM specific
    if result.get("chart_type") in ("ewma", "cusum"):
        ewma_violations = [v for v in violations if v.get("rule") == 1]
        if ewma_violations:
            suggestions.append({
                "severity": "warning",
                "type": "small_shift",
                "message": f"EWMA/CUSUM 檢測到小漂移（{len(ewma_violations)} 次），建議即時調整",
            })
    
    return suggestions
```

### 前端 — 多欄位模式

`SPC.tsx` 新增：
- Toggle: 「單一欄位」/「多欄位比較」模式
- 多欄位模式：Select mode="multiple" 選 output columns
- 顯示：能力比較表格（每列一個 column，欄位：Cp/Cpk/Pp/Ppk + 顏色標籤）
- 控制圖：各欄位獨立 Plotly chart，垂直排列

### 前端 — 優化建議

- 在控制圖下方新增「優化建議」Card
- 每個 suggestion 顯示 severity icon + message
- 無建議時顯示 "製程穩定，無需特別注意"

### i18n 新增 keys

| key | en | zh-TW |
|---|---|---|
| `batchAnalyze` | Batch Analysis | 多欄位分析 |
| `compareColumns` | Compare Columns | 比較欄位 |
| `suggestions` | Optimization Suggestions | 優化建議 |
| `noSuggestions` | Process is stable | 製程穩定 |
| `severity_error` | Urgent | 緊急 |
| `severity_warning` | Warning | 警告 |
| `lowCapability` | Low capability | 能力不足 |
| `shiftDetected` | Shift detected | 偵測到偏移 |
| `trendDetected` | Trend detected | 偵測到趨勢 |

## 驗證

- 引擎 full suite: +8 測試 → 330+ passed
- `npx tsc --noEmit` clean
- `npm run build` 成功
- 三語 parity ok

## Commit 預期

預計 2-3 commits:
1. `feat(engine): batch analyze + optimization suggestions`
2. `feat(spc): multi-column UI + suggestions display`
3. `docs` + push

## Files changed（預期）

- `engine/src/process_intelligence_engine/spc.py`（+compute_spc_suggestions）
- `engine/src/process_intelligence_engine/main.py`（+batch handler）
- `engine/tests/test_spc.py`（+8 測試）
- `src/features/spc/SPC.tsx`（+多欄位模式 + 建議卡片）
- `src/lib/engine.ts`（+BatchAnalyzeResult type）
- `src/lib/assistantData.ts`（+建議 context）
- `src/i18n/*.json`（+9 keys ×3）
