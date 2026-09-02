# TASK.md - Process Intelligence Platform

## Completed

- [x] 讀取並理解設計規格書 (2026-09-02-ai-process-risk-platform-design.md, 1043 lines)
- [x] 檢查專案目錄結構（無程式碼，無 git repo）
- [x] 架構檢視 (Section A) — 10 個架構缺口，3 個規格模糊處
- [x] 技術方案建議 (Section B)
- [x] MVP 分階段計畫 (Section C) — Phase 0-6
- [x] 專案目錄結構 (Section D)
- [x] 核心資料模型與模組邊界 (Section E)
- [x] Phase 1 測試策略 (Section F)
- [x] 產品決策問題清單 (Section G)
- [x] 11 項技術決策問答
- [x] **5 項關鍵決策確認** (Tauri 2.0 / Bundled Python / 無本地 AI / en+zh-TW / 單片粒度)

## Phase 0 (基礎建設) — ✅ 完成

- [x] 初始化 git repo + .gitignore
- [x] npm 專案 + 前端依賴 (React/TS, antd, zustand, plotly, AG Grid, i18next)
- [x] Tauri 2.0 骨架 (Rust, package 更名為 process-intelligence-platform)
- [x] Python 引擎 venv (3.11.14) + 依賴 (pandas, polars, scipy, sklearn, xgboost, shap, pyDOE2, gplearn...)
- [x] Python 分析引擎骨架 + JSON-RPC IPC server (`main.py` + ping/health)
- [x] Rust Python 引擎管理器 (`EngineManager` — 子進程 + RPC client)
- [x] Tauri commands (engine_ping / engine_health / engine_call)
- [x] 前端引擎 API 封裝 (`lib/engine.ts`) + 引擎健康狀態 hook
- [x] 基礎 UI 框架 (Sidebar 11 TAB + Content + AssistantPanel)
- [x] i18n 基礎 (en, zh-TW)
- [x] 專案總覽頁面 (含引擎狀態顯示)
- [x] 驗證: tauri dev 啟動、Python IPC 呼叫 (Rust test ✅)

## Phase 1 (資料基礎) — ✅ 完成 (55 tests 全過, 覆蓋率 84%)

- [x] 1.1 Excel/CSV 匯入引擎 (`importer.py`): 編碼偵測(big5/cp950...)、分隔符、Excel 第一 sheet、預覽、型別正規化 `to_dataframe` (空字串→NaN、數值強制轉型)、`ImportResult.to_dto()`/`_data` 全量資料
- [x] 1.2 欄位自動辨識 (`field_detector.py`): identifier/input/output/quality_label/timestamp/category/metadata/sensitive/excluded + reason
- [x] 1.3 資料品質檢查 (`quality.py`): missing/duplicate/constant/outlier(IQR+4分類)/time_order/unbalanced_okng/batch_imbalance
- [x] 1.4 分布配適 (`distribution.py`): normal~empirical、AIC/BIC 排名、KS test、**pdf 密度曲線輸出**
- [x] 1.5 引擎 IPC: 註冊 data/import, datasets, detect_fields, quality, distribution, series + **in-memory dataset registry** + **JSON 安全淨化層 (`_plain_types`)**
- [x] 1.6 前端資料匯入 UI (`DataImport.tsx`): 檔案選擇(dialog plugin) → 匯入 → 預覽 → 欄位辨識 → 角色確認
- [x] 1.7 前端品質檢查 UI: 確認角色後自動執行並顯示報告
- [x] 1.8 前端 Input/Output/規格 UI (`ProcessDefine.tsx`): 輸出欄位、單位、LSL/USL/Target 驗證、輸入參數單位
- [x] 1.9 前端分布/趨勢圖 (`Exploration.tsx`): Plotly 直方圖+配適密度曲線、KS/AIC 表、趨勢圖+規格線
- [x] 1.10 專案保存/載入: `lib/project.ts` (.piproj.json)、fs plugin、重新匯入 source 檔案重建 dataset
- [x] 1.11 端到端驗證: `test_e2e_pipeline.py` (真實子進程 JSON-RPC)、Rust `pings_live_engine` ✅、`tauri dev` 三進程冒煙測試 ✅ (Vite 1420 / Tauri app / Python engine)

### 驗證結果

- 引擎: 55 tests passed (單元 52 + E2E 3), 覆蓋率 84%
- Rust: `cargo test engine::tests::pings_live_engine` ✅
- 前端: `npx tsc --noEmit` ✅, `npm run build` ✅
- App: `tauri dev` 啟動成功，Python 引擎作為子進程運行於 `.venv/bin/python`

## Phase 2 (異常情境與分析資料包) — ✅ 完成 (68 tests, 86% 覆蓋率)

### 引擎端（2.1 + 2.2）— ✅ 完成 (68 tests 全過)

- [x] 2.1 異常偵測模組 `analysis/anomalies.py` (**TDD**: test_anomalies.py 先 RED 後 GREEN):
  - 三類異常全實作：**spec** (超 LSL/USL) + **control** (超管制線 + 連續上升 runs rule) + **engineering** (使用者自訂配方)
  - 管制線：**自動 mean±3σ**，可按欄手工 LCL/UCL 覆寫
  - occurrence_probability 由歷史資料估計、magnitude_distribution 統計摘要、runs 情境含起始索引與總上升量
  - source (historical_observation/engineering_input) + confidence 標記；`to_dto()` JSON-安全
- [x] 2.2 分析資料包 `build_analysis_package` (**TDD**): 資料指紋 (dataset_id/source/row/col/field_roles/confirmed_field_count) + 完成度檢查 (至少需 output+input → `complete`/`missing_requirements`)
- [x] main.py 註冊 `analysis/detect_anomalies` + `analysis/package` handlers，params 全可選 (spec/control_limits/engineering_scenarios/runs_length) → **test_main_handlers.py 增 13 tests**

### 前端（2.3-2.5）— ✅ 完成

- [x] 2.3 前端 ProcessDefine 管制界限 LCL/UCL 輸入 + 自動 3σ 資訊提示（每欄可獨立覆寫）
- [x] 2.4 前端異常情境 UI：觸發偵測按鈕 → 場景表格（類型/方向/發生率/信心度/來源/逐項確認）+ 全部確認 Popconfirm
- [x] 2.5 前端分析資料包摘要卡（row/col/field_roles/spec/異常數 + 完成度檢查，完全缺 output 或 input 時顯示紅標）

### 2.6 驗證 — ✅ 完成

- 引擎：68 tests passed，覆蓋率 86%
- Rust：`cargo test engine::tests::pings_live_engine` ✅
- 前端：`tsc --noEmit` ✅、`npm run build` ✅

## Pending (next milestones)

- **Phase 2 — 異常情境與分析資料包**: ✅ 完成
- Phase 3 — DOE/AI 混合建模: 計劃已寫妥 `docs/superpowers/plans/2026-09-02-phase3-model-center.md`（Phase 3a 引擎核心，待執行）。完整 DOE 設計庫、交互作用 UI、模型比較 UI、驗證實驗 → Phase 3b
- Phase 4 — 模型比較、驗證實驗建議
- Phase 5 — 蒙地卡羅模擬 + 互動預測 (本地 AI)
- Phase 6 — 報告與版本管理

## Notes

- 規格書要求：不寫死製程名稱、資料路徑或 AI Provider
- 規格書要求：原始資料預設不送往雲端（dataset registry 保持資料在引擎記憶體，僅取圖表所需數值）
- 規格書要求：所有自動建議可解釋、可追溯、可人工覆核
- 已知 pending improvements:
  - `EngineManager::stop` dead_code warning（保留待生命週期管理使用）
  - bundle 超過 500kB warning（plotly 體積，後續可 code-split）
  - AG Grid 已安裝但資料預覽目前用 antd Table（Phase 2 可切換）
## Phase 3a 第一塊 — Regression 比較指標 (metrics) — ✅ 進行中

- [x] 建立 `modeling` 子套件首個模組 (TDD)
  - `engine/src/process_intelligence_engine/modeling/__init__.py`
  - `engine/src/process_intelligence_engine/modeling/metrics.py`
  - `engine/tests/test_metrics.py`
  - 指標: RMSE, MSE, MAE, R², Adjusted R² (Wherry), 全 JSON-native float
  - 測試: 6 passed; 全引擎 suite: 74 passed (覆蓋率 86%)
  - commit `da6079d` feat(modeling): add regression comparison metrics
- 修正: R² 在常數響應 (ss_tot=0) 邊界案例，改為 perfect→1.0 / 殘差非零→-1.0（原設計回傳 0.0 無法通過 test_r2_worse_than_mean_is_negative；此為與規格內部矛盾處，多一個 feature 懲罰測試仍通過）

## Phase 3a 第二塊 — Model Fitting (fiters) — ✅ 完成

- [x] 建立 `modeling/fitters.py` (TDD: 先 RED 後 GREEN)
  - `engine/src/process_intelligence_engine/modeling/fitters.py`
  - `engine/tests/test_fitters.py`
  - `ModelFit` dataclass + `to_dto()` (JSON-安全)
  - `fit_doe_linear` / `fit_doe_quadratic` (`_design_matrix` 含 intercept/平方/交互項)
  - `fit_random_forest` (sklearn, n_estimators)
  - `fit_residual_hybrid` (Y = f_DOE(X) + r_RF(X)，單一共享索引 scheme)
  - 指標共用 `metrics.py` 的 RMSE/MAE/R²/Adj R² (4 個 import 全數使用)
  - 測試: 6 passed; 全引擎 suite: 80 passed (覆蓋率 87%)
  - commit `28c8c55` feat(modeling): DOE linear/quadratic, random forest, residual hybrid fits
- 待續: Phase 3a DOE 設計庫、AI 模型 (xgboost) 封裝、模型比較、驗證

## Phase 3a 第三塊 — Immutable Model Registry (registry) — ✅ 完成

- [x] 建立 `modeling/registry.py` (TDD: 先 RED `ModuleNotFoundError` 後 GREEN)
  - `engine/src/process_intelligence_engine/modeling/registry.py`
  - `engine/tests/test_model_registry.py`
  - `ModelRegistry` in-memory thread-safe registry (`threading.Lock` + `_version_counter`)
  - 不變版本: `register()` 指派單調遞增 version + uuid model_id + status="draft"
  - 狀態機 (spec 12.5): draft → pending_validation → validated → approved；任一狀態可 → retired
  - `InvalidStatusTransition` + `TRANSITIONS` 表；`get_unlocked()` 為刻意不加鎖的 helper（`transition` 已持鎖，`Lock` 非可重入，改用 get() 會 deadlock，不使用 RLock）
  - 測試: 6 passed; 全引擎 suite: 86 passed (覆蓋率 87%, registry 93%)
  - commit `68c36ef` feat(modeling): immutable model registry with status machine
- 待續: Phase 3a DOE 設計庫、AI 模型 (xgboost) 封裝、模型比較、驗證

## Phase 3a 第四塊 — Modeling IPC handlers (main.py 暴露) — ✅ 完成

- [x] main.py 註冊三個新 RPC handlers: `modeling/fit`, `modeling/list`, `modeling/transition`
  - 新增 `modeling/fitters` / `modeling/registry` imports
  - module-level `MODEL_REGISTRY = ModelRegistry()` + `MODEL_FITTERS` map (四種 fitter)
  - `_handle_modeling_fit` / `_handle_modeling_list` / `_handle_modeling_transition`
  - dispatcher 於 `analysis/package` 之後新增三個分支
  - DTO 輸出經 `_plain_types` JSON 安全化
  - `engine/tests/test_main_modeling.py` (5 tests): fit DTO、residual_hybrid、unknown type 拋錯、transition+list、invalid transition 拋錯
  - TDD: 先 RED (`ValueError: Unknown method: modeling/fit`) 後 GREEN
  - 測試: 5 passed; 全引擎 suite: 93 passed (覆蓋率 88%)
  - commit `be9d996` feat(modeling): expose modeling/fit, modeling/list, modeling/transition IPC
- 待續: Phase 3a DOE 設計庫、AI 模型 (xgboost) 封裝、模型比較、驗證

## Code Quality Fixes

- [x] 移除 `main.py` 中未使用的 `InvalidStatusTransition` import (commit `82ae1bb`)
  - 5 modeling tests passed; 93/93 full suite passed (no regression)

## Phase 3a 第五塊 — Frontend Modeling API Types — ✅ 完成

- [x] `src/lib/engine.ts` 新增 Phase 3 modeling 類型與 API 函數
  - `ModelType` (doe_linear/doe_quadratic/random_forest/residual_hybrid)
  - `ModelStatus` (draft/pending_validation/validated/approved/retired)
  - `ModelMetrics` (rmse, mse, mae, r2, adj_r2) — mse 匹配引擎端新增欄位
  - `ModelFitDTO` 完整接口
  - `fitModel()` / `listModels()` / `transitionModel()` 三個 API 函數
  - commit `ff735a6` feat(modeling): add frontend model API types
  - `npx tsc --noEmit` ✅ 無錯誤

## Next
- 繼續 Phase 3a 依 `docs/superpowers/plans/2026-09-02-phase3-model-center.md` 執行其餘引擎核心模組
