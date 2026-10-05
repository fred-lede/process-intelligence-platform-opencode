# OptQuest 式參數尋優設計（spec）

**日期**：2026-10-05
**狀態**：DRAFT — 等待使用者審查
**脈絡**：Crystal Ball 對照缺口盤點後的第三個大項（Overlay/龍捲風/百分位已交付）

## 1. 目標

在已訓練的 DOE/迴歸模型上，於輸入變數範圍內自動搜尋「穩健設計」最佳參數組合：滿足品質約束（Cpk ≥ 門檻 或 不良率 ≤ 上限）下，找出良率最高 / DPMO 最低 / 最接近目標值的設定點 μ。收斂過程以 best-to-date 軌跡圖呈現（對應 OptQuest Best-to-Date Chart）。

## 2. 三種 Objective（使用者選擇：全部三種可選）

| Objective | 評估方式 | 說明 |
|---|---|---|
| `maximize_yield` | 每個候選點跑輕量蒙地卡羅，最大化 P(LSL ≤ Y ≤ USL) | 六標準差核心；需 LSL/USL |
| `minimize_dpmo` | 最小化 DPMO = (1 − yield) × 1e6 | 與 maximize_yield 同源（單調等價），但排名/軌跡顯示以 DPMO 為軸 |
| `hit_target` | 預測值趨近 target_value + Cpk 約束 | Cpk < 門檻的候選標記為 constraint violation，不進 best 追蹤（或顯式降級） |

- `maximize_yield` 與 `minimize_dpmo` 評估值相同（yield），僅報表軸與 best 判定方向不同——實作上共用評估，省一半計算。
- `hit_target` 允許無 LSL/USL（僅 target 距離）；有規格界時套 Cpk 約束。

## 3. 搜尋演算法（使用者選擇：方案 1 輕量隨機搜尋；未來可擴充）

**Latin Hypercube Sampling（LHS）+ 逐點蒙地卡羅評估 + best-to-date 軌跡**：

1. 每個輸入變數取操作範圍（`get_input_ranges` 的 min/max，可由使用者覆寫 bounds）。
2. LHS 產生 `n_candidates` 個候選點（預設 200；純 numpy 實作，無新依賴——`permuted strata + uniform within-cell`）。
3. 每個候選點：以該點為 μ、以資料歷史 σ（各欄 std，可由使用者以公差收緊幅度覆寫）為波動，跑輕量蒙地卡羅（預設 `n_eval_samples=500`/點）→ yield/DPMO/predicted_mean/Cpk。
4. best-to-date 軌跡：逐候選記錄目前最佳（objective 方向性判定 + 約束過濾）。
5. 回傳：best point、best 指標、軌跡（for 圖）、候選分佈摘要（可選 top-N 表）。

**擴充點（未來）**：演算法抽成 `search_algorithms/` 套件，LHS 為第一個實作；遺傳演算法/scipy differential_evolution 之後以同介面加入（`search(fit, bounds, objective, constraints, rng) -> SearchResult`），不改 handler 介面。

**效能預算**：200 候選 × 500 樣本 = 10 萬次 predict（DOE 線性為 numpy 向量式，秒級；tree model 逐點 predict 較慢——候選評估走 batch predict（`fit.model.predict(X_matrix)`），必要時對 tree models 降 n_eval_samples）。

## 4. 引擎介面

新模組 `engine/src/process_intelligence_engine/optimization.py`：

```python
def run_optquest(
    fit, df, objective: str,                 # "maximize_yield"|"minimize_dpmo"|"hit_target"
    lsl: float | None, usl: float | None,
    target_value: float | None = None,
    cpk_min: float = 1.33,                    # hit_target 的約束門檻
    bounds: dict[str, tuple[float, float]] | None = None,   # None → get_input_ranges
    n_candidates: int = 200,
    n_eval_samples: int = 500,
    seed: int = 42,
) -> dict
```

回傳：
```python
{
  "objective": ..., "constraints": {"cpk_min": ...},
  "best_point": {col: value}, "best": {"yield": ..., "dpmo": ..., "predicted_mean": ..., "cpk": ...},
  "feasible": bool,          # best 是否滿足約束
  "baseline": {...同 best 結構, 以資料現況（各欄 median）為起點},
  "trajectory": [{"step": i, "best_so_far": ..., "point": {...}, "feasible": bool}],
  "top_candidates": [top 10 表],
  "n_candidates": ..., "n_eval_samples": ..., "seed": ...,
  "note": "搜尋結果為模型內插預測，套用前須實驗驗證。"
}
```

IPC：`optimization/optquest/run`（main.py handler + policy reader+operator——operator 屬寫類觸發運算，與 `monte_carlo/run` 同級）。

## 5. 前端

- **位置**：Prediction（What-if）頁新增 OptQuest 卡（與 profiler 建議同頁）。
- 控制項：objective 下拉（三選一）、target_value（hit_target 時）、Cpk 門檻、候選數/評估樣本數（進階摺疊）、bounds 覆寫（進階）、seed。
- 顯示：best point 表（含「套用到輸入」按鈕回填 What-if 輸入欄）、baseline vs best 對比、**收斂軌跡圖**（step vs best_so_far，Plotly line）、feasible/violation 徽章。
- i18n 三語同步（en/zh-TW/es-MX）。

## 6. 測試策略（TDD）

- 引擎：LHS 覆蓋（每維等分層）、已知線性模型的 best 逼近解析解（如 y=2x1 在 [0,10] → best x1≈10 for maximize）、約束過濾（cpk_min 排除不可行點）、軌跡單調性（best_so_far 不變差）、seed 重現性、objective 三模式。
- IPC：成功/壞參數結構化錯誤/policy 分類。
- 前端：`tsc --noEmit` EXIT 0 + build。

## 7. 全域約束

- 純 numpy（無新 Python 依賴）；演算法介面預留未來擴充。
- 引擎 IPC 為 stdin/stdout JSON；全部回傳 plain Python types。
- 不改既有 `monte_carlo/run`、`prediction/*` 行為。
- 搜尋結果 UI 必須標註「模型內插預測，套用前須實驗驗證」（對應既有 profiler 的謹慎語言慣例）。

## 8. Review Focus（spec 未明說、最可能咬人的輸入）

1. **單一輸入變數**（n=1）：LHS 退化为 1 維——照常運作，不得崩潰。
2. **bounds 顛倒（min>max）或常數欄（min==max）**：validator 回結構化錯誤／該維固定。
3. **無 LSL/USL 且 objective=maximize_yield/minimize_dpmo**：無法算 yield → 回結構化錯誤（需規格界），不得靜默跑。
4. **target 無法達成**（範圍外）：hit_target 回 feasible=false 與最接近點，不虛報成功。
5. **tree model 的 batch predict 特徵順序**：必須用 `fit.selected_inputs or fit.inputs` 的 fitted 順序（既有 `predict_output` 慣例，避免欄位錯位）。
