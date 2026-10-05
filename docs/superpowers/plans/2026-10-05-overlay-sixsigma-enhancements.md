# Overlay 覆蓋圖 + Six Sigma 小補強 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 補齊 Crystal Ball 對照的缺口——Overlay 覆蓋圖（調參前後對比）+ DPMO/Z-score 顯示 + 極端百分位 P0.1/P99.9 + 敏感度龍捲風圖渲染。

**Architecture:** 引擎層新增 `monte_carlo/compare` handler（兩次蒙地卡羅結果對比：mean shift / std reduction / 兩份 histogram+CDF 疊加資料）；前端 MonteCarlo.tsx 加「儲存基準 → 疊加比較」流程與 Overlay Plot。小補強：percentiles 加 p0.1/p99.9、capability 卡補 DPMO（=ng_probability×1e6）與 Z-score、敏感度表格改為橫條圖（Plotly bar，已排序）。

**Tech Stack:** Python 3.14（engine）、numpy/scipy、TypeScript + React + Plotly（react-plotly.js，既有）、Ant Design、pytest / npx tsc

**Spec:** 使用者提供的 Crystal Ball 4 圖表 + 2 報告材料（Overlay Chart＝方案驗證；Forecast Report 極端百分位；龍捲風圖＝瓶頸診斷）。缺口盤點結論：Overlay 完全沒有、DPMO/Z 沒有、P0.1/P99.9 沒有、敏感度僅表格無圖。

## Global Constraints

- 引擎 IPC 協定為 stdin/stdout JSON；新 handler 走 `handle_request` 註冊模式（main.py L2280+）。
- 新 IPC method 必須加入 `auth/policy.py` 的對應角色清單（reader 可讀、operator 可寫——compare 屬讀類）。
- 前端新欄位一律加到 `src/lib/engine.ts` 型別定義；`npx tsc --noEmit` 必須 EXIT 0。
- i18n 三語（en/zh-TW/es-MX）鍵集必須同步。
- 引擎測試：`uv run --with pytest --with pytest-cov --with pytest-asyncio pytest`；已知 pre-existing 失敗 `test_v040_workflow.py::test_report_review_export_and_reopen_golden_case`（缺 Tesseract）不算回歸。
- 不改既有 `monte_carlo/run` 回傳結構（只加欄位，附加式）。

## Review Focus

- compare handler 對「兩次 result 的 n_simulations 不同」時的統計對比必須仍正確（mean/std 比較不依賴等量樣本）。
- spec 未定義基準儲存行為：合理人預期切換 model 或重新 import 後，舊基準不該被誤用——前端須在 model/dataset 變更時清除基準（對應既有 `handleModelChange` 模式）。
- P0.1/P99.9 在 n<1000 樣本下為外插估計——引擎照算（np.percentile 線性法），前端不封鎖，但 caption 註明樣本數。
- DPMO 只在 lsl/usl 存在時才有意義——無規格時 DPMO 卡不得顯示（對應現行 capability 卡條件式渲染）。
- 敏感度 items 可能為空（未計算前）——龍捲風圖不得在空資料下渲染。

---

### Task 1: 引擎 — percentiles 擴充 + DPMO/Z-score 欄位

**Files:**
- Modify: `engine/src/process_intelligence_engine/monte_carlo.py:477-481`（percentiles dict）、L555-570（return dict 加 dpmo/z_scores）
- Test: `engine/tests/test_monte_carlo.py`

**Interfaces:**
- Consumes: 既有 `run_monte_carlo` 回傳結構
- Produces: `percentiles` 新增 `p0_1`、`p99_9` 兩鍵；回傳 dict 新增 `dpmo: float|None`（ng_probability×1e6，無 lsl/usl 時 None）、`z_lsl`/`z_usl`/`z_min`（Z-scores，無對應規格界時為 None）。

- [ ] **Step 1: 寫失敗測試**（附加到 `engine/tests/test_monte_carlo.py`）

```python
def test_monte_carlo_extreme_percentiles_and_dpmo():
    rng = np.random.default_rng(3)
    df = _make_simple_dataset(rng)
    result = run_monte_carlo(
        df=df, model_type="doe_linear",
        coefficients={"_intercept": 10.0, "x1": 2.0, "x2": -1.5},
        input_columns=["x1", "x2"], output_column="y",
        n_simulations=3000, seed=42,
        lsl=60.0, usl=90.0,
    )
    p = result["percentiles"]
    assert "p0_1" in p and "p99_9" in p
    assert p["p0_1"] < p["p1"] < p["p99"] < p["p99_9"]
    assert result["dpmo"] == pytest.approx(result["ng_probability"] * 1e6)
    # Z-scores: (usl - mean)/std 與 (mean - lsl)/std 至少一個存在
    assert result["z_usl"] == pytest.approx((result["output_mean"] - 90.0) / result["output_std"], abs=1e-6) or result["z_lsl"] == pytest.approx((60.0 - result["output_mean"]) / result["output_std"], abs=1e-6)


def test_monte_carlo_dpmo_none_without_spec():
    rng = np.random.default_rng(3)
    df = _make_simple_dataset(rng)
    result = run_monte_carlo(
        df=df, model_type="doe_linear",
        coefficients={"_intercept": 10.0, "x1": 2.0, "x2": -1.5},
        input_columns=["x1", "x2"], output_column="y",
        n_simulations=500, seed=42,
    )
    assert result["dpmo"] is None
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd engine && uv run --with pytest --with pytest-cov --with pytest-asyncio pytest tests/test_monte_carlo.py::test_monte_carlo_extreme_percentiles_and_dpmo tests/test_monte_carlo.py::test_monte_carlo_dpmo_none_without_spec -q --no-cov`
Expected: FAIL（KeyError: 'p0_1' / 'dpmo'）

- [ ] **Step 3: 實作**（monte_carlo.py）

percentiles dict 加兩鍵：
```python
    percentiles = {
        "p0_1": float(np.percentile(output_values, 0.1)),
        "p1": float(np.percentile(output_values, 1)),
        "p5": float(np.percentile(output_values, 5)),
        "p50": float(np.percentile(output_values, 50)),
        "p95": float(np.percentile(output_values, 95)),
        "p99": float(np.percentile(output_values, 99)),
        "p99_9": float(np.percentile(output_values, 99.9)),
    }
```
return dict 前計算：
```python
    dpmo: float | None = None
    z_lsl = z_usl = None
    if lsl is not None or usl is not None:
        dpmo = float(ng_probability) * 1e6
        if output_std > 0:
            if lsl is not None:
                z_lsl = (output_mean - lsl) / output_std
            if usl is not None:
                z_usl = (usl - output_mean) / output_std
```
return 加 `"dpmo": dpmo, "z_lsl": z_lsl, "z_usl": z_usl,`

- [ ] **Step 4: 跑測試確認通過**

Run: `cd engine && uv run --with pytest --with pytest-cov --with pytest-asyncio pytest tests/test_monte_carlo.py -q --no-cov`
Expected: PASS（24/24）

- [ ] **Step 5: Commit**

```bash
git add engine/src/process_intelligence_engine/monte_carlo.py engine/tests/test_monte_carlo.py
git commit -m "feat(monte-carlo): 極端百分位 P0.1/P99.9 + DPMO/Z-score 欄位"
```

### Task 2: 引擎 — `monte_carlo/compare` handler（Overlay 資料）

**Files:**
- Modify: `engine/src/process_intelligence_engine/main.py`（新 `_handle_monte_carlo_compare` + 註冊 + dispatch）、`engine/src/process_intelligence_engine/auth/policy.py`（reader 清單加 `monte_carlo/compare`）
- Test: `engine/tests/test_main_monte_carlo.py`

**Interfaces:**
- Consumes: Task 1 的 percentiles/dpmo；既有 `run_monte_carlo`、`MODEL_REGISTRY`
- Produces: IPC `monte_carlo/compare`，params `{baseline: {…monte_carlo/run params…}, candidate: {…}}`（兩份完整模擬參數）；回傳 `{success, comparison: {mean_shift, mean_shift_pct, std_reduction_pct, baseline: {mean, std, histogram, cdf_data}, candidate: {mean, std, histogram, cdf_data}, dpmo_baseline, dpmo_candidate}}`。前端只需此結構渲染 Overlay。

- [ ] **Step 1: 寫失敗測試**（附加到 `engine/tests/test_main_monte_carlo.py`）

```python
def test_monte_carlo_compare_overlay(tmp_path):
    import pandas as pd
    from process_intelligence_engine.main import handle_request
    rng = np.random.default_rng(9)
    n = 200
    x1 = rng.normal(100, 5, n)
    x2 = rng.normal(50, 3, n)
    y = 10 + 2 * x1 - 1.5 * x2 + rng.normal(0, 1, n)
    df = pd.DataFrame({"x1": x1, "x2": x2, "y": y})
    did = handle_request("data/import", {"data": df.to_dict(orient="list")})["dataset_id"]
    fit = handle_request("modeling/fit", {
        "dataset_id": did, "model_type": "doe_linear",
        "target": "y", "inputs": ["x1", "x2"],
    })
    model_id = fit["model_id"]
    base = {"dataset_id": did, "model_id": model_id, "n_simulations": 2000, "seed": 42,
            "lsl": 150.0, "usl": 400.0,
            "input_distributions": {"x1": {"name": "normal"}, "x2": {"name": "normal"}}}
    cand = dict(base, input_distributions={"x1": {"name": "normal"}, "x2": {"name": "uniform"}})
    result = handle_request("monte_carlo/compare", {"baseline": base, "candidate": cand})
    assert result["success"] is True
    c = result["comparison"]
    assert set(c["baseline"]["histogram"]["counts"]) is not None
    assert c["baseline"]["cdf_data"]["x"] and c["candidate"]["cdf_data"]["x"]
    assert isinstance(c["mean_shift"], float)
    assert isinstance(c["std_reduction_pct"], float)
    assert c["dpmo_baseline"] is not None and c["dpmo_candidate"] is not None
```

（若 `data/import`/`modeling/fit` 的確切 params 與此不同，以 `test_main_monte_carlo.py` 既有測試的 setup 寫法為準——先讀該檔再寫。）

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd engine && uv run --with pytest --with pytest-cov --with pytest-asyncio pytest tests/test_main_monte_carlo.py::test_monte_carlo_compare_overlay -q --no-cov`
Expected: FAIL（unknown method monte_carlo/compare）

- [ ] **Step 3: 實作 `_handle_monte_carlo_compare`**

```python
def _handle_monte_carlo_compare(params: dict) -> dict:
    """Run two Monte Carlo simulations and return overlay comparison stats."""
    baseline = _handle_monte_carlo_run(params.get("baseline", {}))
    candidate = _handle_monte_carlo_run(params.get("candidate", {}))
    if not baseline.get("success") or not candidate.get("success"):
        return {"success": False,
                "error": {"code": "MONTE_CARLO_COMPARE_FAILED",
                          "baseline_error": baseline.get("error"),
                          "candidate_error": candidate.get("error")}}
    b = baseline["result"]; c = candidate["result"]
    mean_shift = c["output_mean"] - b["output_mean"]
    mean_shift_pct = mean_shift / b["output_mean"] if b["output_mean"] else 0.0
    std_reduction_pct = (1.0 - c["output_std"] / b["output_std"]) if b["output_std"] else 0.0
    return {"success": True, "comparison": {
        "mean_shift": mean_shift,
        "mean_shift_pct": mean_shift_pct,
        "std_reduction_pct": std_reduction_pct,
        "baseline": {"mean": b["output_mean"], "std": b["output_std"],
                     "histogram": b["histogram"], "cdf_data": b["cdf_data"]},
        "candidate": {"mean": c["output_mean"], "std": c["output_std"],
                      "histogram": c["histogram"], "cdf_data": c["cdf_data"]},
        "dpmo_baseline": b.get("dpmo"),
        "dpmo_candidate": c.get("dpmo"),
    }}
```
dispatch 加 `if method == "monte_carlo/compare": return _handle_monte_carlo_compare(params)`；policy.py reader 清單加 `"monte_carlo/compare"`。

- [ ] **Step 4: 跑測試確認通過**

Run: `cd engine && uv run --with pytest --with pytest-cov --with pytest-asyncio pytest tests/test_main_monte_carlo.py -q --no-cov`
Expected: PASS（全部）

- [ ] **Step 5: Commit**

```bash
git add engine/src/process_intelligence_engine/main.py engine/src/process_intelligence_engine/auth/policy.py engine/tests/test_main_monte_carlo.py
git commit -m "feat(monte-carlo): monte_carlo/compare overlay handler"
```

### Task 3: 前端 — Overlay 圖 + DPMO/Z + P0.1/P99.9 + 龍捲風圖

**Files:**
- Modify: `src/lib/engine.ts`（MonteCarloPercentiles 加 p0_1/p99_9；MonteCarloResult 加 dpmo/z_lsl/z_usl；新 MonteCarloComparison 型別 + `compareMonteCarlo()`）
- Modify: `src/features/monte-carlo/MonteCarlo.tsx`（Overlay 卡 + DPMO/Z 顯示 + 百分位列 + 龍捲風圖）
- Modify: `src/i18n/en.json`、`src/i18n/zh-TW.json`、`src/i18n/es-MX.json`（三語鍵同步）
- Test: `npx tsc --noEmit` + `npm run build`

**Interfaces:**
- Consumes: Task 1 的 dpmo/z_lsl/z_usl/p0_1/p99_9、Task 2 的 `monte_carlo/compare`
- Produces: UI — Overlay 卡（儲存基準按鈕 + 疊加 Plot + mean shift/std reduction 標註）、DPMO/Z 卡、P0.1/P99.9 卡、敏感度橫條圖

- [ ] **Step 1: engine.ts 型別**

```typescript
export interface MonteCarloPercentiles {
  p0_1: number
  p1: number
  p5: number
  p50: number
  p95: number
  p99: number
  p99_9: number
}
// MonteCarloResult 加：
//   dpmo?: number | null
//   z_lsl?: number | null
//   z_usl?: number | null
export interface MonteCarloComparison {
  mean_shift: number
  mean_shift_pct: number
  std_reduction_pct: number
  baseline: { mean: number; std: number; histogram: MonteCarloHistogram; cdf_data: MonteCarloCDFData }
  candidate: { mean: number; std: number; histogram: MonteCarloHistogram; cdf_data: MonteCarloCDFData }
  dpmo_baseline: number | null
  dpmo_candidate: number | null
}
export async function compareMonteCarlo(params: { baseline: MonteCarloParams; candidate: MonteCarloParams }): Promise<{ success: boolean; comparison?: MonteCarloComparison; error?: { code: string; message: string } }> {
  return engineCall('monte_carlo/compare', params as unknown as Record<string, unknown>)
}
```

- [ ] **Step 2: MonteCarlo.tsx**

- state：`baselineSnapshot: MonteCarloResult | null`；`compareLoading`
- 「設為基準」按鈕（result 存在時 enabled）→ `setBaselineSnapshot(result)`；「清除基準」
- `handleModelChange`/dataset 變更時 `setBaselineSnapshot(null)`（Review Focus 第 2 條）
- Overlay 卡（baselineSnapshot && result 時）：Plot 疊兩份 histogram bar（baseline `#1677ff` opacity 0.6、candidate `#52c41a` opacity 0.6，`histfunc: 'sum'`, `nbinsx: 30`）+ 兩份 CDF lines；下方標註 mean_shift（含方向色：向目標靠攏綠）、std_reduction_pct（>0 綠 =更穩健）、兩者 DPMO 對比
- DPMO 卡：`result.dpmo != null` 時顯示（放 capability 卡內，col span 調整）；Z_lsl/Z_usl 同列
- 百分位陣列頭尾加 `{ label: t('monteCarlo.p0_1'), value: result.percentiles.p0_1 }` 與 p99_9（span 4→3 或改兩列）
- 敏感度龍捲風圖（ModelCenter.tsx）：`sensitivity.items` 存在時，在表格上方加 Plotly 橫條圖（`type:'bar', orientation:'h', y: items.map(i=>i.input).reverse(), x: items.map(i=>i.sensitivity*100).reverse()`，已排序故 reverse 讓最大在上）；空資料不渲染

- [ ] **Step 3: i18n 三語**

新增鍵（en 為準，zh-TW/es-MX 同步翻譯）：`monteCarlo.p0_1`（P0.1）、`monteCarlo.p99_9`（P99.9）、`monteCarlo.dpmo`（DPMO）、`monteCarlo.zLsl`（Z (LSL)）、`monteCarlo.zUsl`（Z (USL)）、`monteCarlo.setBaseline`（Set as baseline）、`monteCarlo.clearBaseline`（Clear baseline）、`monteCarlo.baselineSet`（Baseline set）、`monteCarlo.overlayTitle`（Overlay: Baseline vs Candidate）、`monteCarlo.meanShift`（Mean shift）、`monteCarlo.stdReduction`（Std reduction）、`monteCarlo.overlayHint`（方案驗證說明：分佈向目標靠攏、變異縮小＝穩健性提高）。
檢查 es-MX 既有 `sourceFromNode` 是否為 `{{name}}`（TASK.md 遺留 follow-up），錯則一併修。

- [ ] **Step 4: 驗證**

Run: `npx tsc --noEmit` → EXIT 0
Run: `npm run build` → ✓ built

- [ ] **Step 5: Commit**

```bash
git add src/lib/engine.ts src/features/monte-carlo/MonteCarlo.tsx src/features/model-center/ModelCenter.tsx src/i18n/*.json
git commit -m "feat(monte-carlo): overlay 覆蓋圖 + DPMO/Z + 極端百分位 + 龍捲風圖"
```

### Task 4: 全量回歸 + 收尾

**Files:**
- Modify: `TASK.md`（記錄本批）、`PROGRESS.md`
- Test: 全量

- [ ] **Step 1: 引擎全量**

Run: `cd engine && uv run --with pytest --with pytest-cov --with pytest-asyncio pytest -q --no-cov`
Expected: 全綠（僅既有 test_v040_workflow golden case 失敗可接受）

- [ ] **Step 2: 前端建置**

Run: `npx tsc --noEmit && npm run build`
Expected: EXIT 0 / ✓ built

- [ ] **Step 3: 更新 TASK.md + PROGRESS.md，commit + push**

```bash
git add TASK.md PROGRESS.md
git commit -m "docs: overlay 覆蓋圖 + six sigma 補強完成記錄"
git push
```

---

## Self-Review 結論

- Spec 覆蓋：Task 1=極端百分位+DPMO/Z（Forecast Report）、Task 2=Overlay 引擎、Task 3=Overlay 前端+龍捲風圖（Sensitivity Chart）——材料缺口 1+3 全覆蓋；缺口 2（OptQuest）另開 spec，不在本計畫。✓
- 步驟單一動作、Expected 明確。✓
- 型別一致：p0_1/p99_9（下劃線，JSON 安全）、dpmo/z_lsl/z_usl 與前端同名。✓
- Review Focus 5 條對應：n_simulations 不等（Task 2 實作僅比統計量）、基準清除（Task 3 Step 2）、外插 caption（Task 3 i18n overlayHint）、DPMO 條件渲染（Task 1 測試 + Task 3）、空敏感度（Task 3 Step 2）。✓
