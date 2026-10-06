# OptQuest 式參數尋優 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在已訓練模型上以 LHS + 輕量蒙地卡羅評估搜尋滿足品質約束的最佳參數組合（三 objective 可選），回傳 best point + 收斂軌跡，前端 Prediction 頁新增 OptQuest 卡。

**Architecture:** 新引擎模組 `optimization.py`（LHS 採樣 + 逐點評估 + best-to-date 軌跡，演算法介面預留未來擴充）；IPC `optimization/optquest/run`；前端 Prediction 頁 OptQuest 卡（控制項 + best 表 + 軌跡圖 + 套用到輸入）。

**Tech Stack:** Python 3.14、numpy（無新依賴）、pytest、TypeScript + React + Plotly + AntD

**Spec:** `docs/superpowers/specs/2026-10-05-optquest-optimization-design.md`（ce41f88）

## Global Constraints

- 純 numpy，無新 Python 依賴；演算法介面預留未來擴充（search(fit, bounds, objective, constraints, rng)）。
- IPC stdin/stdout JSON，回傳 plain Python types；新 method 加入 policy 對應清單。
- 不改既有 monte_carlo/run、prediction/* 行為。
- 搜尋結果 UI 必須標註「模型內插預測，套用前須實驗驗證」。
- i18n 三語（en/zh-TW/es-MX）鍵集同步；tsc --noEmit EXIT 0。
- 引擎測試：`cd engine && uv run --with pytest --with pytest-cov --with pytest-asyncio pytest`（--no-cov）；pre-existing 失敗 test_v040_workflow golden case 不算回歸。

## Review Focus

- 單一輸入變數（n=1）：LHS 一維照常運作，不得崩潰（Task 1 測試）。
- bounds 顛倒（min>max）：validator 回 ValueError 結構化訊息；常數欄（min==max）：該維固定（Task 1 測試）。
- 無 LSL/USL 且 objective 為 maximize_yield/minimize_dpmo：回結構化錯誤（需規格界），不得靜默跑（Task 2 測試）。
- target 無法達成（範圍外）：hit_target 回 feasible=false 與最接近點，不虛報成功（Task 2 測試）。
- tree model batch predict 特徵順序：用 fit.selected_inputs or fit.inputs 的 fitted 順序（Task 1 實作沿用 predict_output 慣例）。

---

### Task 1: 引擎 — optimization.py（LHS + 評估 + 軌跡）

**Files:**
- Create: `engine/src/process_intelligence_engine/optimization.py`
- Test: `engine/tests/test_optimization.py`

**Interfaces:**
- Consumes: `prediction.get_input_ranges(df, cols)`、`prediction.predict_output(model_type, coefficients, inputs, model, feature_names)`、`spc.compute_capability(values, lsl, usl)`
- Produces: `run_optquest(fit, df, objective, lsl, usl, target_value=None, cpk_min=1.33, bounds=None, n_candidates=200, n_eval_samples=500, seed=42) -> dict`（結構見 spec §4：best_point/best/feasible/baseline/trajectory/top_candidates/...）

- [ ] **Step 1: 寫失敗測試**（`engine/tests/test_optimization.py`）

```python
"""Tests for OptQuest-style parameter optimization."""
import numpy as np
import pandas as pd
import pytest

from process_intelligence_engine.modeling.fitters import ModelFit
from process_intelligence_engine.optimization import run_optquest, _lhs_samples


def _linear_fit():
    return ModelFit(model_type="doe_linear", target="y", inputs=["x1", "x2"],
                    coefficients={"_intercept": 0.0, "x1": 2.0, "x2": -1.0})


def _df():
    rng = np.random.default_rng(1)
    return pd.DataFrame({"x1": rng.uniform(0, 10, 100),
                         "x2": rng.uniform(0, 10, 100),
                         "y": 0.0})


def test_lhs_covers_each_stratum():
    samples = _lhs_samples({"x1": (0.0, 10.0), "x2": (0.0, 10.0)}, n=50, seed=42)
    assert set(samples) == {"x1", "x2"}
    for col, vals in samples.items():
        assert len(vals) == 50
        # 每維 50 分層各一樣本：排序後相鄰間距 ≈ 1/50
        s = np.sort(vals)
        assert s[0] >= 0.0 and s[-1] <= 10.0
        gaps = np.diff(s)
        assert np.all(gaps > 0)  # 無重複層


def test_lhs_single_input_works():
    samples = _lhs_samples({"x1": (0.0, 10.0)}, n=20, seed=42)
    assert len(samples["x1"]) == 20


def test_maximize_yield_finds_high_x1():
    # y = 2*x1 - x2；yield 目標區間 [15, 25] → best 應靠近 2*x1-x2 ∈ [15,25]
    fit = _linear_fit()
    result = run_optquest(fit, _df(), objective="maximize_yield",
                          lsl=15.0, usl=25.0, n_candidates=80,
                          n_eval_samples=200, seed=42)
    assert result["best_point"]["x1"] > 7.0
    assert 0.0 <= result["best"]["yield"] <= 1.0
    assert result["best"]["dpmo"] == pytest.approx((1 - result["best"]["yield"]) * 1e6)
    assert len(result["trajectory"]) == 80
    # 軌跡單調不變差
    bests = [t["best_so_far"] for t in result["trajectory"]]
    assert all(bests[i] >= bests[i - 1] - 1e-9 for i in range(1, len(bests)))


def test_minimize_dpmo_same_direction():
    fit = _linear_fit()
    r = run_optquest(fit, _df(), objective="minimize_dpmo",
                     lsl=15.0, usl=25.0, n_candidates=50,
                     n_eval_samples=200, seed=42)
    assert r["best"]["dpmo"] <= 1e6
    assert r["objective"] == "minimize_dpmo"


def test_hit_target_with_cpk_constraint():
    fit = _linear_fit()
    result = run_optquest(fit, _df(), objective="hit_target",
                          lsl=None, usl=None, target_value=10.0,
                          cpk_min=1.0, n_candidates=60,
                          n_eval_samples=200, seed=42)
    assert "best_point" in result and "feasible" in result
    assert result["best"]["predicted_mean"] == pytest.approx(
        2.0 * result["best_point"]["x1"] - 1.0 * result["best_point"]["x2"], abs=2.0)


def test_missing_spec_raises_for_yield_objectives():
    fit = _linear_fit()
    with pytest.raises(ValueError, match="LSL/USL"):
        run_optquest(fit, _df(), objective="maximize_yield",
                     lsl=None, usl=None, n_candidates=10, seed=42)


def test_inverted_bounds_raise():
    fit = _linear_fit()
    with pytest.raises(ValueError, match="bounds"):
        run_optquest(fit, _df(), objective="hit_target", lsl=None, usl=None,
                     target_value=5.0,
                     bounds={"x1": (10.0, 0.0), "x2": (0.0, 10.0)},
                     n_candidates=10, seed=42)


def test_constant_column_fixed():
    fit = _linear_fit()
    result = run_optquest(fit, _df(), objective="hit_target", lsl=None, usl=None,
                          target_value=5.0,
                          bounds={"x1": (0.0, 10.0), "x2": (3.0, 3.0)},
                          n_candidates=20, n_eval_samples=100, seed=42)
    assert result["best_point"]["x2"] == pytest.approx(3.0)


def test_target_out_of_range_feasible_false():
    # y = 2*x1 - x2 在 x1,x2 ∈ [0,10] 的最大值 20；target 1000 不可達
    fit = _linear_fit()
    result = run_optquest(fit, _df(), objective="hit_target", lsl=None, usl=None,
                          target_value=1000.0, n_candidates=30,
                          n_eval_samples=100, seed=42)
    assert result["feasible"] is False
    assert "best_point" in result  # 仍回最接近點


def test_seed_reproducibility():
    fit = _linear_fit()
    r1 = run_optquest(fit, _df(), objective="maximize_yield", lsl=15.0, usl=25.0,
                      n_candidates=30, n_eval_samples=100, seed=7)
    r2 = run_optquest(fit, _df(), objective="maximize_yield", lsl=15.0, usl=25.0,
                      n_candidates=30, n_eval_samples=100, seed=7)
    assert r1["best_point"] == r2["best_point"]
    assert r1["best"]["yield"] == r2["best"]["yield"]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd engine && uv run --with pytest --with pytest-cov --with pytest-asyncio pytest tests/test_optimization.py -q --no-cov`
Expected: FAIL（ModuleNotFoundError: optimization）

- [ ] **Step 3: 實作 `optimization.py`**

```python
"""OptQuest-style parameter search (LHS + lightweight Monte Carlo evaluation)."""
from __future__ import annotations

from typing import Any

import numpy as np

from .prediction import get_input_ranges, predict_output
from .spc import compute_capability


def _lhs_samples(bounds: dict[str, tuple[float, float]], n: int, seed: int) -> dict[str, np.ndarray]:
    """Latin Hypercube: 每維 n 分層各一樣本，層內 uniform。"""
    rng = np.random.default_rng(seed)
    out: dict[str, np.ndarray] = {}
    for col, (lo, hi) in bounds.items():
        strata = (np.arange(n) + rng.uniform(0.0, 1.0, n)) / n
        rng.shuffle(strata)
        out[col] = lo + strata * (hi - lo)
    return out


def _evaluate_points(fit, df, points: list[dict[str, float]], lsl, usl,
                     n_eval_samples: int, seed: int) -> list[dict[str, Any]]:
    """每個候選點：以該點為 μ、歷史 σ 為波動跑輕量蒙地卡羅 → 指標。"""
    rng = np.random.default_rng(seed)
    input_cols = list(points[0].keys()) if points else []
    sigmas = {c: float(df[c].std(ddof=1) if len(df) > 1 and df[c].std(ddof=1) > 0 else 1.0)
              for c in input_cols}
    feature_names = fit.selected_inputs or fit.inputs
    results = []
    for pt in points:
        samples = {c: rng.normal(pt[c], sigmas[c], n_eval_samples) for c in input_cols}
        outputs = np.array([
            predict_output(fit.model_type, fit.coefficients or {},
                           {c: samples[c][i] for c in input_cols},
                           model=fit.model, feature_names=feature_names)
            for i in range(n_eval_samples)
        ], dtype=float)
        if lsl is not None or usl is not None:
            below = outputs < (lsl if lsl is not None else -np.inf)
            above = outputs > (usl if usl is not None else np.inf)
            ng = float(np.sum(below | above))
            yield_ = 1.0 - ng / n_eval_samples
            dpmo = (ng / n_eval_samples) * 1e6
        else:
            yield_, dpmo = None, None
        cap = compute_capability(outputs.tolist(), lsl=lsl, usl=usl, subgroup_size=1) if (lsl is not None or usl is not None) else None
        cpk = cap.get("cpk") if cap else None
        results.append({"point": pt, "yield": yield_, "dpmo": dpmo,
                        "predicted_mean": float(np.mean(outputs)), "cpk": cpk})
    return results


def _score(metric: dict, objective: str, target_value: float | None) -> float:
    """越小越好（min 依 objective 定義方向）。"""
    if objective == "maximize_yield":
        return -(metric["yield"] if metric["yield"] is not None else 0.0)
    if objective == "minimize_dpmo":
        return metric["dpmo"] if metric["dpmo"] is not None else 1e18
    # hit_target: 距 target 的絕對距離
    return abs(metric["predicted_mean"] - (target_value if target_value is not None else 0.0))


def _feasible(metric: dict, objective: str, cpk_min: float) -> bool:
    if objective == "hit_target":
        if metric["cpk"] is None:
            return True  # 無規格界時僅看距離
        return metric["cpk"] >= cpk_min
    return True


def run_optquest(fit, df, objective, lsl, usl, target_value=None, cpk_min=1.33,
                 bounds=None, n_candidates=200, n_eval_samples=500, seed=42) -> dict:
    if objective not in ("maximize_yield", "minimize_dpmo", "hit_target"):
        raise ValueError("objective must be maximize_yield, minimize_dpmo, or hit_target")
    if objective in ("maximize_yield", "minimize_dpmo") and lsl is None and usl is None:
        raise ValueError("LSL/USL required for yield/DPMO objectives")

    # bounds：None → 資料範圍；驗證顛倒/常數
    if bounds is None:
        ranges = get_input_ranges(df, fit.inputs)
        bounds = {c: (ranges[c]["min"], ranges[c]["max"]) for c in fit.inputs}
    for c, (lo, hi) in bounds.items():
        if lo > hi:
            raise ValueError(f"bounds for {c!r} inverted (min>max)")

    rng = np.random.default_rng(seed)
    points_raw = _lhs_samples(bounds, n_candidates, seed)
    points = [{c: (float(bounds[c][0]) if bounds[c][1] == bounds[c][0] else float(points_raw[c][i]))
               for c in fit.inputs}
              for i in range(n_candidates)]

    metrics = _evaluate_points(fit, df, points, lsl, usl, n_eval_samples, seed)

    # best-to-date 軌跡（越小越好；yield 以負分計）
    trajectory = []
    best_idx = None
    best_score = None
    for i, m in enumerate(metrics):
        s = _score(m, objective, target_value)
        ok = _feasible(m, objective, cpk_min)
        if ok and (best_score is None or s < best_score):
            best_score, best_idx = s, i
        trajectory.append({"step": i, "best_so_far": best_score, "point": dict(points[i]), "feasible": ok})

    if best_idx is None:
        # 全部不可行（hit_target + cpk 約束全滅）→ 回距離最近者，標 feasible=false
        best_idx = int(np.argmin([_score(m, objective, target_value) for m in metrics]))
        best_score = _score(metrics[best_idx], objective, target_value)
        feasible = False
    else:
        feasible = True

    m = metrics[best_idx]
    return {
        "objective": objective,
        "constraints": {"cpk_min": cpk_min},
        "best_point": dict(points[best_idx]),
        "best": {"yield": m["yield"], "dpmo": m["dpmo"],
                 "predicted_mean": m["predicted_mean"], "cpk": m["cpk"]},
        "feasible": feasible,
        "baseline": None,  # handler 層以現況點評估填入
        "trajectory": trajectory,
        "top_candidates": [
            {"point": metrics[i]["point"], "yield": metrics[i]["yield"],
             "dpmo": metrics[i]["dpmo"], "predicted_mean": metrics[i]["predicted_mean"],
             "cpk": metrics[i]["cpk"]}
            for i in sorted(range(len(metrics)), key=lambda i: _score(metrics[i], objective, target_value))[:10]
        ],
        "n_candidates": n_candidates, "n_eval_samples": n_eval_samples, "seed": seed,
        "note": "搜尋結果為模型內插預測，套用前須實驗驗證。",
    }
```

（`baseline` 由 handler 以現況點（各欄 median）補評估；或本函式內直接做——實作時擇一，保持回傳結構。）

- [ ] **Step 4: 跑測試確認通過**

Run: `cd engine && uv run --with pytest --with pytest-cov --with pytest-asyncio pytest tests/test_optimization.py -q --no-cov`
Expected: PASS（10/10）

- [ ] **Step 5: Commit**

```bash
git add engine/src/process_intelligence_engine/optimization.py engine/tests/test_optimization.py
git commit -m "feat(optimization): OptQuest 式 LHS 搜尋 + 輕量蒙地卡羅評估 + 軌跡"
```

### Task 2: 引擎 — IPC handler + policy + baseline

**Files:**
- Modify: `engine/src/process_intelligence_engine/main.py`（`_handle_optquest_run` + dispatch + baseline 評估）
- Modify: `engine/src/process_intelligence_engine/auth/policy.py`（reader+operator 清單加 `optimization/optquest/run`）
- Test: `engine/tests/test_main_optimization.py`

**Interfaces:**
- Consumes: Task 1 `run_optquest`
- Produces: IPC `optimization/optquest/run`，params `{model_id, dataset_id, objective, lsl?, usl?, target_value?, cpk_min?, n_candidates?, n_eval_samples?, seed?}`；回傳 `{success, result: {...run_optquest 回傳, baseline: {...}}}`

- [ ] **Step 1: 寫失敗測試**（`engine/tests/test_main_optimization.py`，setup 仿 `test_main_monte_carlo.py` 的 `_import_csv_for_mc`/`_fit_model`）

```python
"""Tests for optimization IPC handler."""
import pytest
from process_intelligence_engine.main import handle_request


def _setup(tmp_path):
    import numpy as np
    rng = np.random.default_rng(42)
    rows = ["x1,x2,y"]
    for _ in range(100):
        x1 = rng.normal(100, 5)
        x2 = rng.normal(50, 3)
        y = 10 + 2 * x1 - 1.5 * x2 + rng.normal(0, 1)
        rows.append(f"{x1:.4f},{x2:.4f},{y:.4f}")
    path = tmp_path / "opt.csv"
    path.write_text("\n".join(rows), encoding="utf-8")
    did = handle_request("data/import", {"file_path": str(path)})["dataset_id"]
    fit = handle_request("modeling/fit", {"dataset_id": did, "model_type": "doe_linear",
                                          "target": "y", "inputs": ["x1", "x2"]})
    return did, fit["model_id"]


def test_optquest_run_success(tmp_path):
    did, mid = _setup(tmp_path)
    result = handle_request("optimization/optquest/run", {
        "model_id": mid, "dataset_id": did, "objective": "maximize_yield",
        "lsl": 150.0, "usl": 400.0, "n_candidates": 60, "n_eval_samples": 150, "seed": 42,
    })
    assert result["success"] is True
    r = result["result"]
    assert set(r["best_point"]) == {"x1", "x2"}
    assert r["baseline"] is not None and "yield" in r["baseline"]
    assert len(r["trajectory"]) == 60
    import json
    json.dumps(result)


def test_optquest_missing_spec_structured_error(tmp_path):
    did, mid = _setup(tmp_path)
    result = handle_request("optimization/optquest/run", {
        "model_id": mid, "dataset_id": did, "objective": "maximize_yield",
        "n_candidates": 10, "seed": 42,
    })
    assert result["success"] is False
    assert "LSL/USL" in result["error"]["message"]


def test_optquest_unknown_model_structured_error(tmp_path):
    did, mid = _setup(tmp_path)
    result = handle_request("optimization/optquest/run", {
        "model_id": "nonexistent", "dataset_id": did, "objective": "hit_target",
        "target_value": 100.0, "n_candidates": 10, "seed": 42,
    })
    assert result["success"] is False
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd engine && uv run --with pytest --with pytest-cov --with pytest-asyncio pytest tests/test_main_optimization.py -q --no-cov`
Expected: FAIL（Unknown method）

- [ ] **Step 3: 實作 `_handle_optquest_run` + dispatch + policy**

```python
def _handle_optquest_run(params: dict) -> dict:
    """OptQuest 式參數尋優：LHS 搜尋 + 蒙地卡羅評估 + baseline 對比。"""
    from process_intelligence_engine.optimization import run_optquest
    fit = MODEL_REGISTRY.get(params["model_id"])
    df = REGISTRY.get(params["dataset_id"])
    try:
        result = run_optquest(
            fit, df,
            objective=params.get("objective", "hit_target"),
            lsl=params.get("lsl"), usl=params.get("usl"),
            target_value=params.get("target_value"),
            cpk_min=params.get("cpk_min", 1.33),
            n_candidates=params.get("n_candidates", 200),
            n_eval_samples=params.get("n_eval_samples", 500),
            seed=params.get("seed", 42),
        )
    except ValueError as exc:
        return {"success": False, "error": {"code": "OPTQUEST_INVALID_PARAMS", "message": str(exc)}}
    # baseline：以資料現況（各欄 median）為起點評估同結構指標
    from process_intelligence_engine.optimization import _evaluate_points
    base_pt = {c: float(df[c].median()) for c in fit.inputs}
    baseline = _evaluate_points(fit, df, [base_pt], params.get("lsl"), params.get("usl"),
                                params.get("n_eval_samples", 500), params.get("seed", 42))[0]
    result["baseline"] = {"point": base_pt, "yield": baseline["yield"],
                          "dpmo": baseline["dpmo"], "predicted_mean": baseline["predicted_mean"],
                          "cpk": baseline["cpk"]}
    return {"success": True, "result": result}
```
dispatch：`if method == "optimization/optquest/run": return _handle_optquest_run(params)`。
policy：reader 與 operator 清單各加 `"optimization/optquest/run"`（operator 觸發運算，同 monte_carlo/run 層級）。

- [ ] **Step 4: 跑測試確認通過**

Run: `cd engine && uv run --with pytest --with pytest-cov --with pytest-asyncio pytest tests/test_main_optimization.py tests/test_optimization.py -q --no-cov`
Expected: PASS（13/13）

- [ ] **Step 5: Commit**

```bash
git add engine/src/process_intelligence_engine/main.py engine/src/process_intelligence_engine/auth/policy.py engine/tests/test_main_optimization.py
git commit -m "feat(optimization): optimization/optquest/run IPC handler + baseline"
```

### Task 3: 前端 — Prediction 頁 OptQuest 卡

**Files:**
- Modify: `src/lib/engine.ts`（OptQuest 型別 + `runOptQuest()`）
- Modify: `src/features/prediction/Prediction.tsx`（OptQuest 卡）
- Modify: `src/i18n/en.json`、`src/i18n/zh-TW.json`、`src/i18n/es-MX.json`
- Test: `node node_modules/typescript/bin/tsc --noEmit` + `npm run build`

**Interfaces:**
- Consumes: Task 2 的 IPC 結構
- Produces: UI — OptQuest 卡（objective 下拉/target/Cpk 門檻/進階參數/seed；best point 表 + 套用到輸入按鈕；baseline vs best 對比；收斂軌跡 Plotly line；feasible 徽章 + 免責訊息）

- [ ] **Step 1: engine.ts 型別**

```typescript
export interface OptQuestTrajectoryStep {
  step: number
  best_so_far: number | null
  point: Record<string, number>
  feasible: boolean
}
export interface OptQuestMetrics { yield: number | null; dpmo: number | null; predicted_mean: number; cpk: number | null }
export interface OptQuestResult {
  objective: string
  constraints: { cpk_min: number }
  best_point: Record<string, number>
  best: OptQuestMetrics
  feasible: boolean
  baseline: ({ point: Record<string, number> } & OptQuestMetrics) | null
  trajectory: OptQuestTrajectoryStep[]
  top_candidates: ({ point: Record<string, number> } & OptQuestMetrics)[]
  n_candidates: number; n_eval_samples: number; seed: number
  note: string
}
export interface OptQuestRunResult {
  success: boolean
  result?: OptQuestResult
  error?: { code: string; message: string }
}
export async function runOptQuest(params: {
  model_id: string; dataset_id: string; objective: string
  lsl?: number; usl?: number; target_value?: number; cpk_min?: number
  n_candidates?: number; n_eval_samples?: number; seed?: number
}): Promise<OptQuestRunResult> {
  return engineCall<OptQuestRunResult>('optimization/optquest/run', params as unknown as Record<string, unknown>)
}
```

- [ ] **Step 2: Prediction.tsx OptQuest 卡**

- state：`optObjective('maximize_yield'|'minimize_dpmo'|'hit_target')`、`optTarget`、`optCpkMin(1.33)`、`optCandidates(200)`、`optEvalSamples(500)`、`optSeed(42)`、`optResult`、`optLoading`
- 「執行 OptQuest 搜尋」按鈕（`!selectedModel || !importResult` disabled）
- 顯示（optResult 時）：
  - best point 表（input/value）＋「套用到輸入」按鈕：`setInputValues(prev => ({...prev, ...optResult.best_point}))`
  - baseline vs best 對比（yield/dpmo/predicted_mean 兩列）
  - 收斂軌跡圖：Plot `[{x: trajectory.map(t=>t.step), y: trajectory.map(t=>t.best_so_far), type:'scatter', mode:'lines'}]`
  - feasible 徽章（Tag green/red）；`optResult.note` Alert type="warning"
- i18n：`prediction.optquestTitle/optquestRun/optquestObjective/optquestTarget/optquestCpkMin/optquestAdvanced/optquestBestPoint/optquestApply/optquestBaseline/optquestBest/optquestTrajectory/optquestFeasible/optquestInfeasible/optquestNote/optquestError`

- [ ] **Step 3: i18n 三語**（en 為準；zh-TW/es-MX 同步翻譯）

- [ ] **Step 4: 驗證**

Run: `node node_modules/typescript/bin/tsc --noEmit` → EXIT 0
Run: `npm run build` → ✓ built

- [ ] **Step 5: Commit**

```bash
git add src/lib/engine.ts src/features/prediction/Prediction.tsx src/i18n/*.json
git commit -m "feat(prediction): OptQuest 卡（三 objective + 收斂軌跡 + 套用到輸入）"
```

### Task 4: 全量回歸 + 收尾

**Files:**
- Modify: `TASK.md`、`PROGRESS.md`

- [ ] **Step 1: 引擎全量** `uv run ... pytest -q --no-cov` → 全綠（僅既有 golden case 失敗可接受）
- [ ] **Step 2: 前端** `tsc --noEmit && npm run build` → EXIT 0 / ✓
- [ ] **Step 3: TASK.md/PROGRESS.md 記錄 + commit + push**

---

## Self-Review 結論

- Spec 覆蓋：Task 1=optimization.py（LHS/評估/軌跡/三 objective/約束）、Task 2=IPC+baseline、Task 3=前端卡+軌跡圖——spec §1-7 全覆蓋。✓
- Review Focus 5 條對應：單一輸入（test_lhs_single_input_works）、bounds 顛倒（test_inverted_bounds_raise）、無規格界（test_missing_spec_raises/test_optquest_missing_spec_structured_error）、target 不可達（test_target_out_of_range_feasible_false）、特徵順序（_evaluate_points 用 feature_names=fit.selected_inputs or fit.inputs）。✓
- 型別一致：run_optquest 簽名與 handler/前端欄位同名（best_point/best/feasible/baseline/trajectory/top_candidates）。✓
