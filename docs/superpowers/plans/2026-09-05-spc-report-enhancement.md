# SPC 報告匯出增強 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SPC control chart analysis results to the existing report generation system (HTML/PDF/Excel).

**Architecture:** Extend `ReportData` model with SPC results, add `control_chart_svg()` to charting.py, add `_render_spc()` to HTML report, auto-run I-MR analysis in `_handle_report_generate`.

**Tech Stack:** Python 3.11, SVG, React 18, TypeScript.

**Spec:** `docs/superpowers/specs/2026-09-05-spc-report-enhancement-design.md`

---

### Task 1: Engine — SPC report data model + SVG chart + HTML render

**Files:**
- Modify: `engine/src/process_intelligence_engine/reporting/models.py`
- Modify: `engine/src/process_intelligence_engine/reporting/charting.py`
- Modify: `engine/src/process_intelligence_engine/reporting/html.py`
- Test: `engine/tests/test_reporting.py`

- [ ] **Step 1: Extend ReportData model**

In `models.py`, add after existing fields (before `version`):
```python
    # SPC analysis
    spc_results: list[dict] = field(default_factory=list)
```

- [ ] **Step 2: Add control_chart_svg() to charting.py**

Append to `charting.py`:
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
    n = len(x_values)
    if n == 0:
        return ""
    
    # Compute y ranges
    all_y = [v for v in x_values if v is not None] + [x_ucl, x_lcl, x_cl, mr_ucl, mr_cl]
    y_min = min(all_y)
    y_max = max(all_y)
    y_pad = (y_max - y_min) * 0.1 or 1
    y_min -= y_pad
    y_max += y_pad
    
    def sx(i: float) -> float:
        return _PLOT_LEFT + (i / max(n - 1, 1)) * (_WIDTH - _PLOT_LEFT - _PLOT_RIGHT)
    
    def sy_top(y: float) -> float:
        return _PLOT_TOP + (1 - (y - y_min) / (y_max - y_min)) * 160
    
    def sy_bottom(y: float) -> float:
        return 220 + (1 - (y - y_min) / (y_max - y_min)) * 140
    
    elems: list[str] = []
    
    # Title
    elems.append(f'<text x="320" y="10" text-anchor="middle" font-size="12" font-weight="bold">{_e(title)}</text>')
    
    # Top chart: Individuals
    elems.append(f'<line x1="{_PLOT_LEFT}" y1="180" x2="{_WIDTH - _PLOT_RIGHT}" y2="180" stroke="#ccc" stroke-width="0.5"/>')
    elems.append(f'<line x1="{_PLOT_LEFT}" y1="20" x2="{_PLOT_LEFT}" y2="180" stroke="#ccc" stroke-width="0.5"/>')
    
    # CL, UCL, LCL lines
    elems.append(f'<line x1="{_PLOT_LEFT}" y1="{sy_top(x_cl):.1f}" x2="{_WIDTH - _PLOT_RIGHT}" y2="{sy_top(x_cl):.1f}" stroke="#52c41a" stroke-width="1" stroke-dasharray="4,2"/>')
    elems.append(f'<text x="{_WIDTH - _PLOT_RIGHT + 2}" y="{sy_top(x_cl):.1f}-3" font-size="8" fill="#52c41a">CL</text>')
    elems.append(f'<line x1="{_PLOT_LEFT}" y1="{sy_top(x_ucl):.1f}" x2="{_WIDTH - _PLOT_RIGHT}" y2="{sy_top(x_ucl):.1f}" stroke="#fa8c16" stroke-width="1" stroke-dasharray="4,2"/>')
    elems.append(f'<text x="{_WIDTH - _PLOT_RIGHT + 2}" y="{sy_top(x_ucl):.1f}-3" font-size="8" fill="#fa8c16">UCL</text>')
    elems.append(f'<line x1="{_PLOT_LEFT}" y1="{sy_top(x_lcl):.1f}" x2="{_WIDTH - _PLOT_RIGHT}" y2="{sy_top(x_lcl):.1f}" stroke="#fa8c16" stroke-width="1" stroke-dasharray="4,2"/>')
    elems.append(f'<text x="{_WIDTH - _PLOT_RIGHT + 2}" y="{sy_top(x_lcl):.1f}+8" font-size="8" fill="#fa8c16">LCL</text>')
    
    # Data line + markers
    points = []
    for i, v in enumerate(x_values):
        if v is None:
            continue
        x = sx(float(i))
        y = sy_top(v)
        points.append(f"{x:.1f},{y:.1f}")
    if len(points) > 1:
        elems.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="#1677ff" stroke-width="1.5"/>')
    for i, v in enumerate(x_values):
        if v is None:
            continue
        x = sx(float(i))
        y = sy_top(v)
        color = "#ff4d4f" if v > x_ucl or v < x_lcl else "#1677ff"
        elems.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2" fill="{color}"/>')
    
    # Bottom chart: MR
    elems.append(f'<line x1="{_PLOT_LEFT}" y1="360" x2="{_WIDTH - _PLOT_RIGHT}" y2="360" stroke="#ccc" stroke-width="0.5"/>')
    elems.append(f'<line x1="{_PLOT_LEFT}" y1="220" x2="{_PLOT_LEFT}" y2="360" stroke="#ccc" stroke-width="0.5"/>')
    elems.append(f'<line x1="{_PLOT_LEFT}" y1="{sy_bottom(mr_cl):.1f}" x2="{_WIDTH - _PLOT_RIGHT}" y2="{sy_bottom(mr_cl):.1f}" stroke="#52c41a" stroke-width="1" stroke-dasharray="4,2"/>')
    elems.append(f'<line x1="{_PLOT_LEFT}" y1="{sy_bottom(mr_ucl):.1f}" x2="{_WIDTH - _PLOT_RIGHT}" y2="{sy_bottom(mr_ucl):.1f}" stroke="#fa8c16" stroke-width="1" stroke-dasharray="4,2"/>')
    
    mr_points = []
    for i, v in enumerate(mr_values):
        if v is None:
            continue
        x = sx(float(i))
        y = sy_bottom(v)
        mr_points.append(f"{x:.1f},{y:.1f}")
    if len(mr_points) > 1:
        elems.append(f'<polyline points="{" ".join(mr_points)}" fill="none" stroke="#722ed1" stroke-width="1.5"/>')
    for i, v in enumerate(mr_values):
        if v is None:
            continue
        x = sx(float(i))
        y = sy_bottom(v)
        color = "#ff4d4f" if v > mr_ucl else "#722ed1"
        elems.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2" fill="{color}"/>')
    
    svg = f'<svg viewBox="0 0 {_WIDTH} 400" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:640px;">{"".join(elems)}</svg>'
    return svg
```

- [ ] **Step 3: Add _render_spc() to html.py**

In `html.py`, add import:
```python
from .charting import histogram_svg, heatmap_svg, control_chart_svg
```

Add method after `_render_monte_carlo()`:
```python
def _render_spc(self) -> str:
    spc_results = self.data.spc_results or []
    if not spc_results:
        return ""
    
    parts = []
    for r in spc_results:
        body = f"<h3>{self._e(r.get('column', 'Unknown'))}</h3>"
        
        # Control chart SVG
        if r.get('x_values') and r.get('mr_values'):
            svg = control_chart_svg(
                x_values=r['x_values'],
                mr_values=r['mr_values'],
                x_ucl=r.get('x_ucl', 0),
                x_lcl=r.get('x_lcl', 0),
                x_cl=r.get('x_mean', 0),
                mr_ucl=r.get('mr_ucl', 0),
                mr_cl=r.get('mr_mean', 0),
                title=f"{r.get('column', 'Column')} I-MR Chart",
            )
            body += f"<div style='margin:10px 0;'>{svg}</div>"
        
        # Capability table
        cap = r.get('capability') or {}
        if cap:
            body += "<table border='1' cellpadding='5' style='border-collapse:collapse;margin:10px 0;'>"
            body += "<tr><th>Cp</th><th>Cpk</th><th>Pp</th><th>Ppk</th></tr>"
            body += f"<tr><td>{self._fmt(cap.get('cp'))}</td><td>{self._fmt(cap.get('cpk'))}</td>"
            body += f"<td>{self._fmt(cap.get('pp'))}</td><td>{self._fmt(cap.get('ppk'))}</td></tr>"
            body += "</table>"
        
        # Violations
        violations = r.get('violations', 0)
        body += f"<p><strong>Violations:</strong> {violations}</p>"
        
        # Suggestions
        suggestions = r.get('suggestions') or []
        if suggestions:
            body += "<h4>Optimization Suggestions</h4><ul>"
            for s in suggestions:
                color = 'red' if s.get('severity') == 'error' else 'orange'
                body += f"<li style='color:{color}'>{self._e(s.get('message', ''))}</li>"
            body += "</ul>"
        
        parts.append(self._section(f"SPC: {r.get('column', 'Unknown')}", body))
    
    return "\n".join(parts)
```

Add to `_generate_html()` sections list (after `_render_monte_carlo()`):
```python
self._render_spc(),
```

- [ ] **Step 4: Write tests**

In `test_reporting.py` (or new test file), add:
```python
def test_control_chart_svg():
    from process_intelligence_engine.reporting.charting import control_chart_svg
    svg = control_chart_svg(
        x_values=[10.0, 11.0, 9.0, 10.5, 11.2],
        mr_values=[None, 1.0, 2.0, 1.5, 0.7],
        x_ucl=12.0, x_lcl=8.0, x_cl=10.0,
        mr_ucl=3.0, mr_cl=1.2,
    )
    assert "<svg" in svg
    assert "I-MR" in svg
    assert "UCL" in svg
    assert "LCL" in svg


def test_render_spc_section():
    from process_intelligence_engine.reporting.html import HTMLReportGenerator
    from process_intelligence_engine.reporting.models import ReportData
    from datetime import datetime
    
    data = ReportData(
        project_name="Test",
        operator="Test",
        created_at=datetime.now(),
        row_count=100,
        column_count=3,
        spc_results=[{
            "column": "thickness",
            "x_values": [10.0, 11.0, 9.0, 10.5],
            "mr_values": [None, 1.0, 2.0, 1.5],
            "x_ucl": 12.0, "x_lcl": 8.0, "x_mean": 10.0,
            "mr_ucl": 3.0, "mr_mean": 1.2,
            "violations": 0,
            "capability": {"cp": 1.5, "cpk": 1.2, "pp": 1.4, "ppk": 1.1},
            "suggestions": [{"severity": "warning", "type": "marginal", "message": "Test suggestion"}],
        }],
    )
    gen = HTMLReportGenerator(data)
    html = gen.generate()
    assert "SPC: thickness" in html
    assert "<svg" in html
    assert "1.5" in html  # Cp value
```

- [ ] **Step 5: Run tests**

Run: `cd engine && .venv/bin/python -m pytest tests/test_reporting.py -q`
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add engine/src/process_intelligence_engine/reporting/models.py engine/src/process_intelligence_engine/reporting/charting.py engine/src/process_intelligence_engine/reporting/html.py engine/tests/test_reporting.py
git commit -m "feat(engine): add SPC control chart to report generation"
```

---

### Task 2: Engine — Auto SPC analysis in report handler

**Files:**
- Modify: `engine/src/process_intelligence_engine/main.py`
- Test: `engine/tests/test_main_report.py`

- [ ] **Step 1: Add SPC analysis to _handle_report_generate**

In `main.py`, after existing section assembly (around line 794), add:

```python
spc_results = []
try:
    from process_intelligence_engine.spc import compute_i_mr, compute_spc_suggestions
    output_cols = [f['name'] for f in fields_list if f.get('role') == 'output']
    if not output_cols:
        output_cols = num_cols[:1]
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
            "x_values": r["x_values"],
            "mr_values": r["mr_values"],
        })
except Exception:
    pass
```

Then pass `spc_results` to `ReportData`:
```python
report_data = ReportData(
    ...
    spc_results=spc_results,
)
```

- [ ] **Step 2: Add test**

In `test_main_report.py`, append:
```python
def test_report_generate_with_spc(tmp_path):
    """Test that report includes SPC analysis."""
    import numpy as np
    rng = np.random.default_rng(42)
    n = 100
    x1 = rng.uniform(0, 1, n)
    y = 2.0 + 3.0 * x1 + rng.normal(0, 0.1, n)
    rows = ["x1,y"]
    for i in range(n):
        rows.append(f"{x1[i]:.5f},{y[i]:.5f}")
    path = tmp_path / "spc_report.csv"
    path.write_text("\n".join(rows), encoding="utf-8")
    did = handle_request("data/import", {"file_path": str(path)})["dataset_id"]
    
    result = handle_request("report/generate", {
        "dataset_id": did,
        "format": "html",
        "spec": {"outputField": "y", "lsl": 0.0, "usl": 10.0},
    })
    assert result["success"]
    assert "SPC:" in result["content"]
    assert "<svg" in result["content"]
```

- [ ] **Step 3: Run tests and commit**

Run: `cd engine && .venv/bin/python -m pytest tests/test_main_report.py -q`
Expected: all tests PASS

Run: `cd engine && .venv/bin/python -m pytest tests/ -q`
Expected: full suite PASS (327+ passed)

```bash
git add engine/src/process_intelligence_engine/main.py engine/tests/test_main_report.py
git commit -m "feat(engine): auto SPC analysis in report generation"
```

---

### Task 3: Frontend + i18n + docs

**Files:**
- Modify: `src/lib/engine.ts`
- Modify: `src/i18n/en.json`, `zh-TW.json`, `es-MX.json`
- Modify: `PROGRESS.md`, `TASK.md`

- [ ] **Step 1: Update engine.ts**

Add optional param to `ReportParams`:
```typescript
export interface ReportParams {
  // ... existing fields
  spc_columns?: string[]
}
```

- [ ] **Step 2: Add i18n keys**

In all three i18n files, add to `report` section:
```json
"spcSection": "Statistical Process Control",
"spcViolations": "Violations",
"spcCapability": "Capability",
"spcSuggestions": "Suggestions"
```

Verify parity:
```bash
python3 -c "import json; ks=[set(json.load(open('src/i18n/%s.json'%f))['report']) for f in ('en','zh-TW','es-MX')]; print('parity ok:', ks[0]==ks[1]==ks[2])"
```

- [ ] **Step 3: Verify frontend**

Run: `npx tsc --noEmit`
Expected: exit 0

- [ ] **Step 4: Commit**

```bash
git add src/lib/engine.ts src/i18n/en.json src/i18n/zh-TW.json src/i18n/es-MX.json
git commit -m "feat(report): add SPC report params and i18n"
```

---

### Task 4: Docs + verification + push

- [ ] **Step 1: Update docs**
  - `PROGRESS.md`: append entry for SPC report enhancement
  - `TASK.md`: add DONE entry
  - `README.md`: update reporting section to mention SPC charts

- [ ] **Step 2: Final verification**
  ```bash
  cd engine && .venv/bin/python -m pytest tests/ -q
  npx tsc --noEmit
  npm run build 2>&1 | tail -2
  ```

- [ ] **Step 3: Commit + push**
  ```bash
  git add PROGRESS.md TASK.md README.md
  git commit -m "docs: SPC report enhancement"
  git push
  ```

---

## Self-review

- Spec coverage: ReportData model ✅, SVG chart ✅, HTML render ✅, auto analysis ✅, tests ✅
- No placeholders; all code blocks complete
- Type consistency: `spc_results: list[dict]` matches engine return shape
