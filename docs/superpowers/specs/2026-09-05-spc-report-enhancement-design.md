# SPC 報告匯出增強 — 設計規格 v1.0

日期：2026-09-05
狀態：設計討論中

## 目標

在既有報告系統中新增 SPC 控制圖分析結果，讓匯出的 HTML/PDF/Excel 報告包含：
1. 控制圖（I-MR SVG）
2. 能力指數（Cp/Cpk/Pp/Ppk）
3. Western Electric 違規統計
4. 優化建議

## 範圍

### Included

1. **引擎 ReportData model**：新增 `spc_results: list[dict]` 欄位
2. **引擎 charting.py**：新增 `control_chart_svg()` 函式，繪製 I-MR 控制圖 SVG
3. **引擎 html.py**：新增 `_render_spc()` 方法，渲染 SPC 章節
4. **引擎 main.py**：`_handle_report_generate` 自動對 numeric output columns 跑 I-MR 分析
5. **前端 engine.ts**：ReportParams 加 `spc_columns?: string[]` 可選參數
6. **測試**：新增 SPC 報告生成測試

### Excluded

- EWMA/CUSUM 控制圖 SVG（後續版本）
- 多欄位並排比較圖（後續版本）
- 前端 Report 頁面 UI 變更（報告產生邏輯不變，只擴展數據）
- SPC 專用獨立報告（本次只擴展既有專案報告）

## 設計

### 1. ReportData model 擴展

`engine/src/process_intelligence_engine/reporting/models.py`：

```python
# 在已有欄位後新增：
spc_results: list[dict] = field(default_factory=list)
# 每個 dict 結構：
{
    "column": str,           # 欄位名稱
    "chart_type": str,       # "i-mr"
    "n_points": int,         # 資料點數
    "x_mean": float,         # 平均值
    "x_ucl": float,          # UCL
    "x_lcl": float,          # LCL
    "mr_ucl": float,         # MR UCL
    "violations": int,        # 違規數
    "capability": dict,       # {cp, cpk, pp, ppk}
    "suggestions": list[dict], # [{severity, type, message}]
}
```

### 2. charting.py 新增 control_chart_svg()

`engine/src/process_intelligence_engine/reporting/charting.py`：

```python
def control_chart_svg(
    x_values: Sequence[float],
    mr_values: Sequence[float | None],
    x_ucl: float,
    x_lcl: float,
    x_cl: float,
    mr_ucl: float,
    mr_cl: float,
    title: str = "I-MR Control Chart",
) -> str:
    """Render I-MR control chart as inline SVG."""
    # 繪製兩個子圖：上圖 Individuals，下圖 MR
    # 共用 x 軸，各自 y 軸
    # 返回 SVG markup string
```

設計要點：
- 固定 viewBox="0 0 640 400"
- 上圖 (y: 0-180)：Individuals 數據線 + UCL/LCL/CL 參考線
- 下圖 (y: 220-380)：MR 數據線 + MR UCL/CL 參考線
- 違規點以紅色標記
- 使用既有 `_nice_ticks()` 和 `_e()` helper

### 3. html.py 新增 _render_spc()

`engine/src/process_intelligence_engine/reporting/html.py`：

```python
def _render_spc(self) -> str:
    spc_results = self.data.spc_results or []
    if not spc_results:
        return ""
    
    parts = []
    for r in spc_results:
        body = f"<h3>{self._e(r['column'])}</h3>"
        
        # 控制圖 SVG
        if r.get('x_values') and r.get('mr_values'):
            body += control_chart_svg(
                x_values=r['x_values'],
                mr_values=r['mr_values'],
                x_ucl=r['x_ucl'],
                x_lcl=r['x_lcl'],
                x_cl=r['x_mean'],
                mr_ucl=r['mr_ucl'],
                mr_cl=r.get('mr_mean', 0),
                title=f"{r['column']} I-MR Chart",
            )
        
        # 能力指數表格
        cap = r.get('capability') or {}
        if cap:
            body += "<table><tr><th>Cp</th><th>Cpk</th><th>Pp</th><th>Ppk</th></tr>"
            body += f"<tr><td>{self._fmt(cap.get('cp'))}</td><td>{self._fmt(cap.get('cpk'))}</td>"
            body += f"<td>{self._fmt(cap.get('pp'))}</td><td>{self._fmt(cap.get('ppk'))}</td></tr></table>"
        
        # 違規統計
        violations = r.get('violations', 0)
        body += f"<p>Violations: <strong>{violations}</strong></p>"
        
        # 優化建議
        suggestions = r.get('suggestions') or []
        if suggestions:
            body += "<h4>Optimization Suggestions</h4><ul>"
            for s in suggestions:
                color = 'red' if s.get('severity') == 'error' else 'orange'
                body += f"<li style='color:{color}'>{self._e(s.get('message'))}</li>"
            body += "</ul>"
        
        parts.append(self._section(f"SPC: {r['column']}", body))
    
    return "\n".join(parts)
```

在 `_generate_html()` 的 sections 列表中，在 `_render_monte_carlo()` 之後加入 `_render_spc()`。

### 4. main.py 擴展 _handle_report_generate

在既有 section assembly 之後，新增 SPC 分析：

```python
spc_results = []
try:
    output_cols = [f['name'] for f in fields_list if f.get('role') == 'output']
    if not output_cols:
        output_cols = num_cols[:1]  # fallback: first numeric col
    for col in output_cols:
        values = df[col].dropna().tolist()
        if len(values) < 5:
            continue
        r = compute_i_mr(values, lsl=lsl, usl=usl)
        suggestions = compute_spc_suggestions(r)
        spc_results.append({
            "column": col,
            "chart_type": r["chart_type"],
            "n_points": len(values),
            "x_mean": r["control_limits"]["x"]["cl"],
            "x_ucl": r["control_limits"]["x"]["ucl"],
            "x_lcl": r["control_limits"]["x"]["lcl"],
            "mr_ucl": r["control_limits"]["mr"]["ucl"],
            "mr_mean": r["control_limits"]["mr"]["cl"],
            "violations": len(r["violations"]),
            "capability": r.get("capability"),
            "suggestions": suggestions,
            # 傳 SVG 需要的原始數據
            "x_values": r["x_values"],
            "mr_values": r["mr_values"],
        })
except Exception:
    pass
```

然後把 `spc_results` 傳入 `ReportData`。

### 5. 前端 engine.ts

`src/lib/engine.ts`：
```typescript
export interface ReportParams {
  // ... 既有欄位
  spc_columns?: string[]  // 可選：指定要分析的 SPC 欄位
}
```

### 6. i18n

在 `report` section 新增：
```json
"spcSection": "Statistical Process Control (SPC)",
"spcViolations": "Violations",
"spcCapability": "Capability Indices",
"spcSuggestions": "Optimization Suggestions"
```

## 驗證

- 引擎 full suite：新增 ~5 測試 → 332+ passed
- `npx tsc --noEmit` clean
- `npm run build` 成功
- 手動測試：產生報告 → 確認 SPC 章節包含控制圖 SVG + 能力指數 + 建議

## Commit 預期

預計 2 commits：
1. `feat(engine): add SPC section to report generation`
2. `feat(report): SPC report UI + i18n`

## Files changed（預期）

- `engine/src/process_intelligence_engine/reporting/models.py`
- `engine/src/process_intelligence_engine/reporting/charting.py`
- `engine/src/process_intelligence_engine/reporting/html.py`
- `engine/src/process_intelligence_engine/main.py`
- `engine/tests/test_main_report.py`（或新 test 檔）
- `src/lib/engine.ts`
- `src/i18n/en.json`, `zh-TW.json`, `es-MX.json`
