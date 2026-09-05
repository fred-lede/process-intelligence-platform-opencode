# HANDOFF.md

## Milestone: 製程流程 × 下游分析整合（ProcessFlow ↔ Downstream Analysis）完成

**日期**: 2026-09-05

**里程碑**: 10-task ProcessFlow↔downstream-analysis integration 全部完成並 merge 至 main（含 Task 10 hardening）。

### 交付內容

- **引擎**：`ProjectManifest.association_keys` + `set_association_keys()`；`filter_column`/`filter_value` df-level mask 統一為 `_apply_row_filter` helper（SPC analyze / monte_carlo run / data distribution / data series 4 handler，含 zero-row `ValueError("No rows match filter")` 守衛）
- **前端**：`processFlowNavStore` + `processFlowContext.ts` 跳轉基礎設施；ProcessFlow 關聯鍵 UI + 跳轉按鈕；App 訂閱切 tab；SPC / Monter-Carlo / Exploration 消費跳轉上下文（StrictMode-safe）+ 共用 `NodeSourceFilter` 元件（`filterable` 控制 time-series/GRR 不顯示 filter）
- **i18n**：三語（en / zh-TW / es-MX）`processFlow`/`spc`/`monteCarlo`/`exploration` key-set parity `ok`
- **驗證**：全引擎 **304 passed, 1 skipped**；`npx tsc --noEmit` clean；`npm run build` 成功

### Commits（本里程碑）

`cd7788e, 7db24b8, e0f85dd, 570d01c, b535cd0, 26f3b89, 74e44f4, c22c283, a15e04c, 9e3d2b9, b7f3100, 878f821, 8160797, 4ab2313, c76aff4, 62ce296, 909bf76` + Task 10 (`feat(engine)` zero-row guard / `fix(spc)` numeric guard / `docs`)

### Known Follow-ups

1. **time-series / GRR 不套用節點 filter**：Exploration time-series/GRR tabs 前端 `filterable=false` 隱藏控制，引擎通道未接（有意範圍裁剪）
2. **dev StrictMode 一次性跳轉語意**：`consume()` 為破壞性清空（production 正常，dev 有既有 mount-effect 守衛）
3. **數值欄 filter 比較注意**：`astype(str) == str(value)` 對數值欄（`50.0` vs `"50"`）可能 0 列；現已由 zero-row `ValueError` 明確提示（不靜默）

### 下一步方向（供後續任務參考）

- 節點篩選延伸至 time-series / GRR
- 引擎 `filter_value` 空字串（`""`）防護
- 跳轉前未載入資料時「資料載入後自動補選」fallback
## 2026-09-05 — SPC Batch Analyze + Suggestions
- **Commit**: `9af8153`
- **引擎**: `spc.py` 新增 `compute_spc_suggestions()` + `main.py` 新增 `spc/batch_analyze` IPC handler
- **測試**: 4 支新增，全引擎 326 passed / 1 skipped
- **Files**: `spc.py`, `main.py`, `tests/test_spc.py`, `tests/test_main_spc.py`

## 2026-09-05 — SPC 深化（EWMA/CUSUM + 規格線 + 多欄位 + 報告）

### SPC 管制線修復 + 規格線 + MR 子圖
- **Commit**: `ed0f273` / `8c67ec7` / `2b9709c` / `bb65f12` / `1d2cb57`
- **修復**：`analyzeSPC` 攤平巢狀 `control_limits`（`{x:{ucl,lcl,cl}, mr:{...}}` → 前端 flat key）；i-mr 補畫 MR 子圖（右軸紫線）；規格線 LSL/USL 加在 Individuals / X-bar 圖（紅實線）；管制線圖例全部開啟（移除 12 處 `showlegend:false`）
- **Files**: `engine/src/process_intelligence_engine/spc.py`（flattenControlLimits）、`src/features/spc/SPC.tsx`

### SPC 深化：EWMA / CUSUM
- **Commit**: `a2d0f03` / `673ecf0` / `36cb950`
- **引擎**: `compute_ewma()` / `compute_cusum()` + IPC `spc/analyze` dispatch；參數 `ewma_lambda`/`ewma_L`/`cusum_k`/`cusum_H`
- **前端**: SPC 選單新增 EWMA/CUSUM 選項 + 參數控制 UI + plotly 繪圖；i18n 11 keys ×3 語
- **測試**: 6 支新增
- **Files**: `spc.py`, `main.py`, `test_spc.py`, `test_main_spc.py`, `SPC.tsx`, `engine.ts`, i18n×3

### SPC 批次分析 + 優化建議
- **Commit**: `9af8153`
- **引擎**: `compute_spc_suggestions()` — Cpk < 1.0（error）、Cpk < 1.33（warning）、Rule 4 shift（error）、Rule 5 trend（warning）、EWMA/CUSUM small_shift（warning）；`spc/batch_analyze` handler
- **測試**: 4 支新增
- **Files**: `spc.py`, `main.py`, `test_spc.py`, `test_main_spc.py`

### SPC 多欄位比較
- **Commit**: `673ecf0` / `36cb950`
- **前端**: `SPCBatchResult` + `analyzeSPCBatch()`；「多欄位比較」模式 toggle；Select multiple columns → 比較表格（Cp/Cpk/Pp/Ppk + violations）+ 各欄獨立控制圖
- **i18n**: +11 keys ×3 語

### SPC 報告匯出
- **Commit**: `b09aaa3` / `fbd5b3b` / `fe66be0` / `e4b5b57`
- **引擎**: `ReportData.spc_results` + `charting.py` `control_chart_svg()`（I-MR SVG 雙子圖）+ `html.py` `_render_spc()`；`_handle_report_generate` 自動對 output columns 跑 I-MR
- **前端**: `ReportParams.spc_columns?`；i18n +4 keys
- **測試**: 2 支新增

## 2026-09-05 — 蒙地卡羅預測能力指數

- **Commit**: `bb1b019` / `27eb722` / `a08c7e3` / `1d2cb57` / `43e8b9d`
- **引擎**: `run_monte_carlo` 回傳 `capability`（reuse `compute_capability`，subgroup_size=1 → Pp/Ppk 語意）
- **前端**: `MonteCarloResult.capability?`；「預測能力指數」卡片（Pp/Ppk + σ，≥1.33 綠 / ≥1.0 橘 / <1.0 紅）；AI context 一行
- **測試**: 2 支新增；引擎 306 passed
- **Polish**: σ 精度 `.toFixed(3)` → `.toFixed(2)`；context guard 補 `sigma_overall != null`

## 2026-09-05 — 2.0 AI 模型擴充（XGBoost / LightGBM + 自動特徵選取）

- **Commit**: `cb49b49` / `2073d53` / `c94e11e` / `f0d4979` / `2b71112` / `7404acf`
- **引擎**: `fit_xgboost()` / `fit_lightgbm()` + `pyproject.toml` 加 lightgbm；`_auto_select_features()` helper（feature_importances_ top-K）；`fit_random_forest` 暴露超參數（n_estimators/max_depth/min_samples_leaf/auto_select_features）
- **前端**: `ModelCenter` 樹模型設定卡片（Switch + InputNumber）；`SPCCapability` 共用；i18n +8 keys ×3 語
- **SHAP**: `shap_explainer.py` 支援 xgboost/lightgbm（TreeExplainer 通用）
- **測試**: +8 支；引擎 322 passed
- **Files**: `fitters.py`, `shap_explainer.py`, `main.py`, `test_fitters.py`, `test_shap_explainer.py`, `pyproject.toml`, `ModelCenter.tsx`, `engine.ts`, i18n×3

## 2026-09-05 — AI 助手領域知識增強

- **Commit**: `8b37832` / `9b116f1` / `983fd74`
- **`assistantGuide.ts`**: SPC/MC/Exploration 三頁新增完整領域知識（控制圖選擇指南、能力指數解讀、WE 7 規則、NG 機率分級、GRR 標準）
- **`assistantData.ts`**: `buildSpcContext` 加 Cpk 狀態（GOOD/MARGINAL/POOR）+ URGENT/WARNING 建議分級；`buildMonteCarloContext` 加 risk level（HIGH/MEDIUM/MODERATE/LOW）+ Ppk 狀態

## 2026-09-05 — 技術債修復

| 項目 | Commit | 說明 |
|---|---|---|
| `.coverage` gitignore | `1dd82ee` | `git rm --cached` 移除已追蹤的 .coverage |
| Tauri icons | `4f64e6d` | 追蹤 android/ios 圖示（35 檔） |
| filter_value 空字串 | `212a0aa` | `_apply_row_filter` 拒絕 `""`，+1 測試 |
| Chunk 優化 | `12741ec` + `9b682a2` | Plotly lazy-load + manualChunks（主 chunk 5,851→347 kB，-94%） |

## 當前狀態

- **引擎**: **339 passed, 1 skipped**
- **前端**: tsc clean、build 成功（無警告）
- **i18n**: 三語 parity ok（25 top-level keys, 內部 key 一致）
- **Commits**: `cd7788e..212a0aa`（共 22 個 commits 於 main）

## 已知限制

1. **jump-before-import fallback**：跳轉時資料未載入 → `numericColumns=[]` → 不自動選欄（既定行為，非阻塞）
2. **Plotly 4.3 MB**：lazy-loaded 後按需載入；初始載入已降至 347 kB
3. **dev StrictMode 跳轉語意**：`consume()` 破壞性清空（production 正常）
