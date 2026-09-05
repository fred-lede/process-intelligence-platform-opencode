# PROGRESS.md

## 2026-09-05 — Task 2: XGBoost + LightGBM fitters（SPEC COMPLIANT）
- **實作**：`fitters.py` 加 `fit_xgboost`/`fit_lightgbm`（auto-select + hyperparams + availability guard）；`main.py` `MODEL_FITTERS` 註冊；`pyproject.toml` 加 `lightgbm>=4.0.0`；3 支新測試
- **修正**：`_handle_modeling_fit` 原僅對 `random_forest` 透傳 hyperparams，擴為 tree models 共用（`n_estimators`/`max_depth`/`min_samples_leaf`/`learning_rate`/`auto_select_features`/`importance_threshold`/`max_features`/`test_size`/`random_state`）
- **驗證**：`test_fitters.py` 12 passed；全引擎 **314 passed, 1 skipped**（baseline 308 + 3 新）

## 2026-09-02 — Phase 0 基礎建設完成

### 完成內容

- [x] 建立 git repo (.gitignore 已設定)
- [x] 建立 Tauri 2.0 + React 18 + TypeScript 專案骨架
- [x] 建立 Python 分析引擎 (venv@3.11.14, 位置 `engine/.venv`)
- [x] 建立 Rust ↔ Python JSON-RPC IPC 通道
  - `engine::EngineManager` — 子進程管理與呼叫
  - `commands::engine_ping/health/call` — Tauri IPC
  - 前端 `lib/engine.ts` — API 封裝
- [x] 前端基礎 UI：
  - 左側導航 (11 個 TAB)
  - 中央工作區
  - 右側 AI 助手面板 (佔位)
  - 專案總覽頁面 (含引擎健康狀態顯示)
- [x] i18n 基礎：en, zh-TW
- [x] UI 風格：工業控制室 × 統計分析工作台 (antd 主題: #2563EB 主色)

### 驗證結果

- Rust `cargo check` ✅
- Rust `cargo test engine::tests::pings_live_engine` ✅ (Rust→Python IPC 打通)
- TypeScript `tsc --noEmit` ✅
- 前端 `npm run build` ✅
- `npm run tauri dev` 完整啟動 ✅
  - Vite (1420) 啟動 ✅
  - Tauri Rust 核心啟動 ✅
  - Python 引擎子進程啟動 (PID 確認) ✅

### 技術棧確認 (2026-09-02)

| 決策 | 選擇 |
|---|---|
| 桌面框架 | Tauri 2.0 |
| Python 引擎 | Bundled venv @ 3.11 |
| Phase 1 本地 AI | 不需要 (延到 Phase 5) |
| Phase 1 i18n | en + zh-TW |
| Phase 1 資料粒度 | 單片產品/單一測試樣本 |

### 下一步 (Phase 1)

- Excel/CSV 匯入 (`engine/src/.../data/importer.py`)
- 欄位自動辨識 (`field_detector.py`)
- 資料品質檢查 (`quality.py`)
- Input/Output/規格設定 UI
- 分布圖表 (直方圖、密度曲線、box plot) + 趨勢圖
- 專案保存與載入

## 2026-09-02 — Phase 1 資料基礎完成

### 完成內容

- [x] 引擎端 (TDD, 全部含測試)：
  - `importer.py` — 編碼偵測 (big5/cp950/gb18030/shift_jis)、分隔符偵測、Excel 第一 sheet、50 列預覽、`to_dataframe` 型別正規化 (空字串→NaN、數值強制轉型 90% 閾值)
  - `field_detector.py` — 欄位角色辨識 (identifier/input/output/quality_label/timestamp/category/metadata/sensitive/excluded) 含 reason
  - `quality.py` — missing/duplicate/constant/outlier(IQR+離群值四分類)/time_order/unbalanced_okng(閾值0.25)/batch_imbalance
  - `distribution.py` — 10 種分布配適、AIC/BIC 排序、KS test、**PDF 密度曲線輸出**
  - `main.py` — **in-memory dataset registry** (資料留在引擎記憶體，符合「原始資料不上雲」原則)、6 個 data/* 方法、`_plain_types` JSON 安全淨化層
- [x] 前端：
  - `@tauri-apps/plugin-dialog` + `plugin-fs` (Cargo + npm + capabilities)
  - `DataImport.tsx` — 4 步流程 (選檔→預覽→辨識→角色確認) + 品質報告
  - `dataPipelineStore.ts` (Zustand) — import/fields/quality/spec 狀態
  - `ProcessDefine.tsx` — 輸出欄位 + 單位 + LSL/USL/Target(含驗證) + 輸入參數單位
  - `Exploration.tsx` — Plotly 直方圖+配適密度曲線 (可切換 top-3)、AIC/BIC/KS 表、趨勢圖+規格線
  - `lib/project.ts` — `.piproj.json` 專案保存/載入 (重新匯入 source 檔案重建 dataset)
  - i18n en/zh-TW 新增全部新 UI 字串
- [x] 端到端測試 (`test_e2e_pipeline.py`)：真實子進程 JSON-RPC 跑完整流程 (含 numpy 型別序列化)

### 驗證結果

- 引擎：**55 tests passed** (單元 52 + E2E 3)，覆蓋率 **84%**
- Rust：`cargo test engine::tests::pings_live_engine` ✅ (實機 Python 子進程)
- 前端：`tsc --noEmit` ✅、`npm run build` ✅
- `npm run tauri dev` 三進程冒煙測試 ✅ (Vite 1420 / Tauri app / Python engine subprocess)

### 待辦 (Phase 2)

- [ ] 異常情境定義 (規格/製程控制/工程情境)
- [ ] 正常分布與異常情境展示
- [ ] 使用者確認分析資料包
- [ ] DOE/AI 混合建模、模型比較、驗證實驗、蒙地卡羅、互動預測、報告

### Known Improvements

- `EngineManager::stop` dead_code warning（待生命週期管理）
- bundle > 500kB (plotly) — 後續 code-split
- AG Grid 已裝但預覽用 antd Table — Phase 2 可切換

## 2026-09-02 — Phase 2 引擎端完成（異常情境 + 分析資料包）

### 完成內容

- [x] 2.1 異常偵測模組 `analysis/anomalies.py`（**TDD：RED→GREEN**，test_anomalies.py 10 tests）：
  - **spec 異常**：輸出欄超 LSL/USL，occurrence_probability 由歷史資料估計 + magnitude_distribution
  - **control 異常**：超管制線（**自動 mean±3σ**，可按欄 LCL/UCL 手工覆寫）+ **連續上升 runs rule**（runs_length=5，含起始索引/總上升量/平均步幅）
  - **engineering 異常**：使用者自訂配方 (target ± tolerance)，source=engineering_input, confidence=0.85
  - 每情境帶 source/confidence/`to_dto()`（JSON 安全純 Python 型別）
  - 自動 3σ 於樣本數 <10 或 σ=0 時跳過；runs 情境獨立於管制線門檻
- [x] 2.2 分析資料包 `build_analysis_package`（TDD）：資料指紋 (dataset_id/source_file/row_count/column_count/field_roles/confirmed_field_count) + 完成度（需 ≥1 output + ≥1 input → `complete`/`missing_requirements`）
- [x] main.py 註冊 `analysis/detect_anomalies` + `analysis/package`（樣本<10 或 無手工限制時行為測試覆蓋）→ test_main_handlers.py +3 tests，總 13 新增

### 驗證結果

- 引擎：**68 tests passed**（原 55 + 新增 13），含全部 Phase 1 回歸
- 覆蓋率上升（anomalies.py 92%）

### 待辦 (Phase 2 前端)

- [ ] 2.3 ProcessDefine 管制線 LCL/UCL 輸入 + 自動 3σ 建議顯示
- [ ] 2.4 異常情境 UI（偵測清單 + 逐項確認 + 工程情境新增表單）
- [ ] 2.5 分析資料包摘要卡（指紋/角色/規格/異常 + 確認）
- [ ] 2.6 驗證：tsc/build/cargo/tauri dev 冒煙 + 更新文件

## 2026-09-02 — Phase 2 完成（異常情境 + 分析資料包）

### 完成內容

- [x] 2.3 前端 ProcessDefine：管制界限區塊（LCL/UCL 手動覆寫 + 自動 3σ 提示標籤，每欄獨立）
- [x] 2.4 前端異常情境 UI：觸發偵測 → 場景表格（類型/方向/發生率/信心度/來源/逐項確認）+ 全部確認 Popconfirm
- [x] 2.5 前端分析資料包摘要卡（row/col/field_roles/spec/異常數 + 完成度檢查，缺 output 或 input 顯示警告）
- [x] 2.6 驗證全部通過

### 驗證結果

- 引擎：**68 tests passed**，覆蓋率 **86%**
- Rust：`cargo test engine::tests::pings_live_engine` ✅
- 前端：`tsc --noEmit` ✅、`npm run build` ✅（plotly 大檔 warning，可後續 code-split）

### 待辦 (Phase 3)

- [ ] DOE 實驗設計（factor/screen/response 範本）
- [ ] AI 混合建模、模型比較、驗證實驗、蒙地卡羅模擬、互動預測、報告匯出

## 2026-09-02 — Phase 3a 完成（模型中心：DOE + AI + 混合模型）

### 完成內容

- [x] 3.1 模型比較指標 `modeling/metrics.py`（TDD）：RMSE, MSE, MAE, R², Adjusted R²；R² 在 ss_tot=0 且有殘差時回傳 -1.0
- [x] 3.2 模型配適器 `modeling/fitters.py`（TDD）：
  - DOE 線性 / DOE 二次（`_design_matrix` 含 intercept + 平方 + 交互項）
  - 隨機樹回歸（sklearn RandomForestRegressor）
  - 殘差混合模型（Y = f_DOE(X) + r_RF(X)，先 shuffle 分 train/test）
  - `ModelFit` dataclass + `to_dto()`（JSON 安全）
- [x] 3.3 不可變版本登錄 `modeling/registry.py`（TDD）：
  - `ModelRegistry`（thread-safe，threading.Lock）
  - 單調遞增版本號、永不覆寫
  - 狀態機：draft → pending_validation → validated → approved；任一狀態可 → retired
- [x] 3.4 main.py IPC handlers（TDD）：`modeling/fit`、`modeling/list`、`modeling/transition`
- [x] 3.5 前端 modeling API：`src/lib/engine.ts` 新增 ModelType/ModelStatus/ModelMetrics/ModelFitDTO 型別 + fitModel/listModels/transitionModel
- [x] Code quality 修正：移除 main.py 未使用 import、registry `_get_unlocked` 改名 + docstring 修正 + 2 補充測試

### 驗證結果

- 引擎：**93 tests passed**（Phase 0-2: 68 + Phase 3a: 25），覆蓋率 **88%**
- Rust：`cargo check` ✅（1 warning, EngineManager::stop dead_code, 非回歸）
- 前端：`tsc --noEmit` ✅、`npm run build` ✅（plotly 大檔 warning，非回歸）

### Commits（phase3-model-center 分支）

| Hash | 說明 |
|------|------|
| da6079d | feat(modeling): add regression comparison metrics |
| 28c8c55 | feat(modeling): DOE linear/quadratic, random forest, residual hybrid fits |
| 419ea2b | feat(modeling): include mse in model comparison metrics |
| d677820 | fix(modeling): correct adj_r2 feature count, always shuffle hybrid split, expose intercept |
| 68c36ef | feat(modeling): immutable model registry with status machine |
| 9761d9b | docs: update TASK.md for Phase 3a model registry |
| ce94297 | refactor(modeling): private lock-holder helper, accurate immutability doc, retire/unknown-status tests |
| be9d996 | feat(modeling): expose modeling/fit, modeling/list, modeling/transition IPC |
| 82ae1bb | chore(modeling): remove unused InvalidStatusTransition import |
| ff735a6 | feat(modeling): add frontend model API types |

### 待辦 (Phase 3b — 模型中心 UI)

- [ ] DOE 設計庫（full factorial / fractional / CCD / Box-Behnken / Latin Hypercube / OptSpace）
- [ ] 交互作用分析（二因素交互、三因素交互）
- [ ] 模型比較 / 模型中心前端 UI
- [ ] 驗證實驗推薦
- [ ] SHAP 可解釋性
- [ ] 外插風險評分
- [ ] Logistic / 計數 / 可靠度模型

## 2026-09-02 — Phase 3b-1 完成（模型中心頁面）

### 完成內容

- [x] `src/stores/modelStore.ts` — Zustand 模型狀態管理（loadModels/fit/transition/selectModel/clearError）
- [x] `src/features/model-center/ModelCenter.tsx` — 模型中心頁面：
  - 模型配適表單（ModelType Select + 目標欄位 + 輸入多選 + 配適按鈕）
  - 模型列表比較表（type/version/status + R²/RMSE/MAE/Adj R² + 狀態切換 Popconfirm）
  - Guard clause（無資料時顯示提示）
- [x] `src/App.tsx` — 路由接線（modelCenter tab render branch）
- [x] `src/i18n/en.json` + `zh-TW.json` — modelCenter section 中英文
- [x] 驗證：`tsc --noEmit` ✅、`npm run build` ✅

### Commits（phase3b-1-model-center-ui 分支）

| Hash | 說明 |
|------|------|
| 6e2485a | feat(model-center): add Zustand model store |
| 4942008 | fix(model-center): clear error state on loadModels |
| c2d611d | feat(model-center): add ModelCenter page component |
| 239a003 | feat(model-center): wire routing + i18n strings |

### 待辦 (Phase 3b-2)

- [ ] 模型比較表（多模型並排指標對比）
- [ ] 交互作用分析（二因素交互）
- [ ] DOE 設計庫（6 種設計）
- [ ] SHAP / 外插風險 / 驗證實驗推薦

## 2026-09-02 — Phase 3b-2 完成（模型比較增強）

### 完成內容

- [x] ModelCenter.tsx 加入 checkbox row selection + Compare 按鈕
- [x] 比較 Card：並排顯示 R²/RMSE/MAE/Adj R²，最佳值綠色高亮 + ★
- [x] i18n：compareButton / compareTitle / compareMetric en+zh-TW
- [x] 驗證：tsc clean ✅、build clean ✅

### Commits

| Hash | 說明 |
|------|------|
| 70e9289 | feat(model-center): add model comparison with checkbox selection and best-value highlighting |

## 2026-09-02 — Phase 3b-6 完成（SHAP 可解釋性）

### 完成內容

- [x] `modeling/shap.py` + `main.py` — IPC handler `modeling/shap/explain` (commit `5ef27f3`)
- [x] `engine.ts` — `SHAPResult` type + `computeSHAP()` API
- [x] `ModelCenter.tsx` — SHAP 分析 Card：
  - 「計算 SHAP」按鈕（含 loading 狀態）
  - 特徵重要性水平長條圖（Plotly bar chart）
  - SHAP Summary 蜂群散點圖（Plotly scatter）
- [x] i18n en/zh-TW 新增 7 個字串（shapTitle, computeSHAP, computingSHAP, shapImportanceTitle, shapImportance, shapSummaryTitle, shapError）
- [x] 驗證：`tsc --noEmit` ✅、`npm run build` ✅

### Commits（phase3b-1-model-center-ui 分支）

| Hash | 說明 |
|------|------|
| 866699e | feat(model-center): add SHAP interpretability visualization |
| 5ef27f3 | feat(shap): expose modeling/shap/explain IPC + frontend API |

### 待辦 (Phase 3b-7)

- [ ] 外插風險評分

## 2026-09-02 — Phase 3b-3 完成（DOE 設計庫）

### 完成內容

- [x] `modeling/doe.py` — 6 種 DOE 設計產生器：
  - Full Factorial（2/3/N levels）
  - Fractional Factorial（Resolution III half-fraction）
  - CCD（Central Composite Design：factorial + axial + center points）
  - Box-Behnken（edge midpoints + center points，≥3 factors）
  - D-optimal（coordinate exchange algorithm，maximize |X'X|）
  - Taguchi（L4/L8/L9/L16 orthogonal arrays）
- [x] `_build_runs` shared helper — coded→actual mapping（-1→low, 0→mid, 1→high）
- [x] `main.py` IPC handler `modeling/doe/generate`
- [x] `engine.ts` — `DOEFactor` / `DOEDesignResult` types + `generateDOEDesign()` API
- [x] 測試：14 DOE tests + 4 IPC tests，全引擎 111 tests (88% coverage)
- [x] 驗證：tsc clean ✅、build clean ✅

### Commits

| Hash | 說明 |
|------|------|
| 26ba9da | feat(doe): full factorial + fractional factorial design generators |
| a04ebd3 | fix(doe): levels>=2 guard, document factor ordering, remove dead import |
| eb7c247 | feat(doe): CCD + Box-Behnken design generators |
| 31be710 | feat(doe): D-optimal + Taguchi design generators |
| bf93182 | feat(doe): expose modeling/doe/generate IPC + frontend API wrapper |

### 待辦 (Phase 3b-4)

- [ ] SHAP 可解釋性
- [ ] 交互作用分析
- [ ] 外插風險評分
- [ ] 驗證實驗推薦

## 2026-09-02 — Phase 3b-4 完成（交互作用分析）

### 完成內容

- [x] `modeling/interactions.py` — 因子效應分解計算
- [x] `main.py` — `modeling/interactions/compute` IPC handler
- [x] `engine.ts` — `InteractionResult` + `computeInteractions()` API
- [x] `ModelCenter.tsx` — 熱圖 Card（抗色強度正比於交互作用強度）
- [x] i18n en/zh-TW 新增 5 個字串
- [x] 驗證：117 tests (89% coverage)、tsc clean、build clean

### Commits

| Hash | 說明 |
|------|------|
| 451cb64 | feat(interactions): two-factor interaction strength computation |
| 07824d3 | feat(interactions): expose IPC + frontend API |
| 9632e7e | feat(model-center): add interaction analysis heatmap |

### 待辦 (Phase 3b-5)

- [ ] SHAP 可解釋性
- [ ] 外插風險評分
- [ ] 驗證實驗推薦

## 2026-09-02 — Phase 3b-5 完成（SHAP 可解釋性）

### 完成內容

- [x] `modeling/shap_explainer.py` — SHAP 值計算（LinearExplainer + TreeExplainer）
- [x] `main.py` — `modeling/shap/explain` IPC handler
- [x] `engine.ts` — `SHAPResult` 型別 + `computeSHAP()` API
- [x] `ModelCenter.tsx` — 特徵重要性條狀圖 + SHAP 摘要圖（Plotly）
- [x] i18n en/zh-TW 新增 6 個字串
- [x] 驗證：123 tests (89% coverage)、tsc clean、build clean

### Commits

| Hash | 說明 |
|------|------|
| 826986c | feat(shap): SHAP value computation for model interpretability |
| 5ef27f3 | feat(shap): expose modeling/shap/explain IPC + frontend API |
| 866699e | feat(model-center): add SHAP interpretability visualization |

### 待辦 (Phase 3b-6)

- [ ] 外插風險評分
- [ ] 驗證實驗推薦

## 2026-09-02 — Phase 3b-7 完成（外插風險評分）

### 完成內容

- [x] `modeling/extrapolation.py` — `compute_extrapolation_risk()`：對每個預測點計算各因子風險（超出訓練範圍的歸一化距離），總風險取 max
- [x] `test_extrapolation.py` — 5 個測試：無外插、上方外插、下方外插、多點、邊界點
- [x] 驗證：128 tests（全 pass）、覆蓋率 **89%**
- [x] `main.py` — `modeling/extrapolation/check` IPC handler
- [x] `engine.ts` — `ExtrapolationResult` 型別 + `checkExtrapolation()` API
- [x] `test_main_extrapolation.py` — 3 個 IPC handler 測試
- [x] 驗證：131 tests（全 pass）、覆蓋率 **89%**、tsc clean

### Commits

| Hash | 說明 |
|------|------|
| de32eff | feat(extrapolation): expose modeling/extrapolation/check IPC + frontend API |
| a738613 | feat(extrapolation): extrapolation risk scoring for predictions |
## 2026-09-02 — Phase 3b-8 Validation & Residual Analysis

### 完成內容

- [x] `validation.py` — cross_validate, analyze_residuals, recommend_experiments
- [x] 5 個測試用例通過
- [x] 全套件 136 tests pass, 88% coverage
- Commit: `89b397c`
- [x] `main.py` — `modeling/validation/analyze` IPC handler
- [x] `engine.ts` — `ValidationResult` type + `analyzeValidation()` API
- [x] `test_main_validation.py` — 2 個 IPC handler 測試
- [x] 驗證：138 tests（全 pass）、覆蓋率 **89%**、tsc clean
- Commit: `6f1a4d6`

## 2026-09-03 — Phase 5 — Report Generation Engine

### 完成內容

- [x] `reporting/models.py` — `ReportData` dataclass（專案資訊、資料來源、欄位角色、品質摘要、模型比較、互動、建議）
- [x] `reporting/base.py` — `ReportGenerator` 抽象基類（`generate()`、`_format_number()`、`_format_percentage()`、`_truncate()`）
- [x] `reporting/html.py` — `HTMLReportGenerator`：完整 HTML 報告（專案資訊、資料來源、欄位角色表格、CSS 樣式）
- [x] `test_reporting.py` — 7 個測試：HTML 結構、樣式、資料建立、空欄位、名稱截斷、百分比格式化、badge 類別
- [x] 驗證：155 tests（全 pass）、覆蓋率 **89%**
- Commit: `ba29efb`

## 2026-09-03 — Phase 6 — User Management & Audit Logging

### 完成內容

- [x] `main.py` — 6 個 auth/audit IPC handlers：`auth/login`、`auth/logout`、`auth/register`、`audit/log`、`users/list`、`auth/current`
- [x] `src/lib/engine.ts` — `UserRole`、`AuthResult`、`UserRecord`、`AuditEntry` 型別 + 6 個前端 API
- [x] `src/features/settings/Settings.tsx` — 使用者管理頁面（登入/登出/註冊 modal、使用者列表、稽核紀錄）
- [x] `src/App.tsx` — `settings` tab 路由
- [x] `engine/tests/test_main_auth.py` — 7 個 IPC handler 測試
- [x] i18n en/zh-TW — settings section 全部字串
- [x] 驗證：181 tests pass (89% coverage)、tsc clean、build clean
- Commit: `571341f`

## 2026-09-03 — Phase 8-9 Monte Carlo IPC Handler

### 完成內容

- [x] `engine/src/process_intelligence_engine/main.py` — import `run_monte_carlo`, add `_handle_monte_carlo_run`, dispatch `monte_carlo/run`
- [x] `engine/tests/test_main_monte_carlo.py` — 5 IPC handler tests (basic, unknown model, with anomalies, no bounds, unknown dataset)
- [x] 驗證：239 tests pass, 1 skipped (88% coverage)、無回歸
- Commit: `af522e2`

### Commits
| Hash | 說明 |
|------|------|
| af522e2 | feat(monte_carlo): add monte_carlo/run IPC handler |

## 2026-09-03 — Phase 10 Interactive Prediction

- [x] `prediction.py` + `main.py` — `prediction/predict` + `prediction/model_info` IPC handlers
- [x] `src/lib/engine.ts` — `PredictionResult`, `ModelInfo`, `InputRange` + API 函數
- [x] `src/features/prediction/Prediction.tsx` — Live 滑桿 + 數值輸入 + 規格判定
- [x] `src/i18n/en.json` + `zh-TW.json` — prediction section
- 驗證：250 tests pass, tsc/build clean

## 2026-09-03 — Phase 11 Validation Lab

- [x] `main.py` — `experiment/record`, `experiment/list`, `experiment/get` IPC handlers
- [x] `src/lib/engine.ts` — `ExperimentRecord` + API 函數
- [x] `src/features/validation/ValidationLab.tsx` — 完整驗證 + 實驗記錄 + 歷史表格
- [x] i18n en/zh-TW — validationLab section
- 驗證：250 tests pass, tsc/build clean

## 2026-09-03 — Phase 11b 短期補強

- [x] **Logistic Regression** — `fitters.py:fit_logistic_regression()`（binary NG prediction, accuracy/recall/AUC）
- [x] **Weibull Regression** — `fitters.py:fit_weibull_regression()`（MLE, shape k + log(λ)=Xβ）
- [x] **時間序列特徵** — `features/time_series.py`（lag/rolling/drift/連續超標）+ 2 IPC handlers
- [x] **審核工作流** — `approval/workflow.py`（submit/approve/reject + status + records）+ 5 IPC handlers
- [x] **What-if 情境保存** — `prediction/scenario/*` IPC + Prediction.tsx Modal
- [x] i18n en/zh-TW：prediction.scenario* / timeSeries* / approval*
- 驗證：250 tests pass, tsc/build clean

## 2026-09-03 — Phase 11c 中期第一批

- [x] **PDF 報告匯出** — `pdf.py` + `main.py` format=pdf handler + `Report.tsx` PDF 按鈕
- [x] **可信度六維評分** — `validation.py:compute_credibility()`（data_coverage/predictive_acc/statistical_stability/engineering_reasonable/validation_degree/extrapolation_risk）
- [x] **Credibility UI** — ValidationLab 表格新增可信度等級欄位 + 分數卡片
- [x] i18n：credibility.*
- 驗證：250 tests pass, tsc/build clean

## 2026-09-03 — Phase 11d Copula 聯合機率

- [x] **copula.py** — 高斯 Copula + 獨立 + 直接指定三種模式（100K Monte Carlo samples）
- [x] **Monte Carlo 整合** — `apply_anomalies()` 支援 Copula 相關性，`run_monte_carlo()` 回傳 `copula` 結果
- [x] **Correlation matrix 驗證** — 正定矩陣檢查 + 失敗自動 fallback
- [x] IPC handler `copula/joint`
- [x] i18n：copula.*
- 驗證：250 tests pass, tsc/build clean

## 2026-09-03 — Phase 11e GRR + 時間序列 UI

- [x] **GRR 引擎** — `data/grr.py`（AIEM 方法：EV/AV/GRR/PV/TV/%GRR + verdict + warnings）
- [x] **GRR IPC** — `data/grr` handler + `analyzeGRR()` TypeScript API
- [x] **時間序列 UI** — Exploration 新增 Time Series tab（lag/rolling/drift 圖表）
- [x] **GRR UI** — Exploration 新增 GRR tab（選欄位 → 分析 → 結果 + 警告）
- [x] i18n：exploration.timeSeriesTab / grr.*
- 驗證：250 tests pass, tsc/build clean

## 2026-09-03 — Phase 11f es-MX 翻譯

- [x] **es-MX.json** — 541 keys，覆蓋全部 22 個 i18n section
- [x] `i18n/index.ts` 註冊 es-MX
- [x] Sidebar 語言選單新增「Español (México)」
- 符合規格 19 多語言要求

## 2026-09-03 — Phase 11g 雲端去識別化

- [x] **deidentify.py** — `DeidentificationEngine`：敏感欄位 SHA-256 雜湊遮蔽 + 數值高斯噪音 + 上傳雜湊
- [x] **IPC handlers** — `cloud/preview` / `cloud/upload` / `cloud/records`
- [x] **Settings UI** — 雲端上傳區塊（noise σ / 預覽表格 / 強制確認 Modal）
- [x] 審核紀錄：operator / provider / model_version / mask_rules / upload_hash / purpose
- [x] i18n：cloud.*
- 符合規格 11A + 24 雲端安全要求

## 2026-09-03 — Phase 11h 檔案系統資料目錄結構

- [x] **project/manifest.py** — `ProjectEngine`：on-disk `project_manifest.json` + 9 目錄自動建立
- [x] **資料模型** — `DatasetRegistration`（checksum/quality/cloud_policy）+ `ProcessGroup` + `ProcessNode`
- [x] **18 IPC handlers** — manifest/create/open/settings/dirs/source-dirs/scan/process-groups/*/process-nodes/*/datasets/*/dataset/register/update
- [x] **TypeScript** — 20 API 函數 + 完整類型
- [x] i18n：project.*（53 keys）
- 符合規格 11A 資料資產管理要求

## 2026-09-03 — Phase 11i 製程流程圖

- [x] **ProcessFlow.tsx** — SVG 流程圖（拓撲排序佈局 + 節點卡片 + 貝茲曲線邊 + 選中高亮）
- [x] **節點管理** — 新增 Modal（名稱/類型/重工政策）+ 刪除
- [x] **連接管理** — 多選連接目標節點 + 斷開連接
- [x] **圖形驗證** — DFS 環狀檢測 + 孤立節點警告（`validate_flow_graph` IPC）
- [x] **Sidebar** 新增「製程流程」導航項目
- [x] i18n：processFlow.*（31 keys）
- 符合規格 11A 製程節點可配置要求

## 2026-09-03 — Interactive Prediction 滑桿修復

- [x] **根因**：`importer.py` `to_dto()` 未輸出 `mean/std/min/max` → 前端拿不到真實統計，離群資料下滑桿範圍變天文數字、bar/藍點卡住
- [x] **引擎**：`to_dto()` 補上 `mean/std/min/max` 欄位
- [x] **Prediction.tsx**：滑桿範圍改 `mean ± 3σ`（含離群 cap 防護）
- [x] **自訂 DraggableSlider**：棄用原生 range / antd Slider（WKWebView 拖曳支援差），改 pointer-capture 拖曳，無 useEffect 競態
- [x] **其他**：移除重複 listModels useEffect；DataImport 移除 deprecated index-based rowKey
- **實機驗證：滑桿拖曳正常、數值合理 ✅**


## 2026-09-04 — 完整 14 項規格報告輸出（§17.2）

- [x] **ReportData 擴充**：新增 `time_range / spec / distribution_fits / anomalies / monte_carlo / credibility / process_window / row_count / column_count` 等欄位
- [x] **handler 組裝**：`_handle_report_generate` 防禦式組裝 14 項（quality / distribution / anomalies / interactions / credibility / recommendations / monte_carlo / propose process window），新增 `_spec_serializable`、`_proposed_process_window` 輔助
- [x] **best_model 回退**：無 validated/approved 模型時退而取第一個模型，避免報告缺最佳模型區塊
- [x] **HTMLReportGenerator 重寫**：渲染全部 14 項內容（資料來源/欄位規格/資料品質/正常與異常分布/模型比較/方程式/交互作用/蒙地卡羅/可信度/建議製程窗口），含 severity badge、防 HTML 注入跳脫、percentile 表、異常貢獻排名
- [x] **前端**：`ReportParams` 新增 `spec/lsl/usl/runs_length/n_simulations/seed/enable_anomalies`；`Report.tsx` 傳入 spec 與蒙地卡羅參數
- [x] 保留既有報告單元測試（truncation、percentage、badge）並補齊格式
- **驗證**：引擎測試 250 passed；smoke 端到端渲染 11 個 section 全出；tsc + vite build 通過

## 2026-09-04 — 報告加入 SVG 圖表

- [x] **charting.py 新增**：輕量 SVG 產生器 `histogram_svg`（直方圖 + 擬合曲線 + LSL/USL 超規線 + NG 區著色）、`heatmap_svg`（交互作用強度熱圖）
- [x] **正常分布（§5）**：各數值欄位直方圖 + 擬合曲線；異常時於同欄標記 threshold 閾值線
- [x] **蒙地卡羅 Output 分布（§10）**：輸出直方圖 + 超規 LSL/USL + NG 區著色
- [x] **交互作用熱圖（§8）**：`interactions.matrix` + `factors` 視覺化
- [x] handler 組裝 `distribution_fits` 補入 fit 的 `histogram`/`pdf`
- 驗證 — 250 passed；smoke 渲染 6 個 SVG（3 分布 + 1 異常 + 1 蒙地卡羅 + 1 熱圖），LSL/USL 標記齊全

## 2026-09-04 — 製程流程圖轉為完整圖形化編輯器（spec 11A，10 tasks）

- [x] **Task 1+2（引擎，TDD）**：`ProcessNode` 新增 `x/y` 欄位（`create_process_node` 透傳）；新增 `engine/tests/test_manifest_nodes.py`（5 測試，含五種資料映射欄位）
- [x] **Task 3**：前端 `ProcessNode` 型別加 `x?: number / y?: number`
- [x] **Task 4（bug 修復，核心）**：節點改為**世界座標** `node.x/y` + 視口 transform `<g translate(pan) scale(zoom)>`；新增 pan（拖背景）/zoom（滾輪 0.5–2）/`fitView()` 初次補償負座標 → 修復「第二個節點被擠出畫布」bug；節點/port 加 `data-node`/`data-node-id`/`data-port`
- [x] **Task 5**：節點拖曳（screen delta / zoom）+ `updateProcessNode` 持久化 + 失敗 rollback
- [x] **Task 6**：縮放控制列（+/-/重設/FitView）+ 自動佈局按鈕（`computeLayout`）+ minimap 疊層（含 viewport 指示框）
- [x] **Task 7**：port 拖曳連線（elementFromPoint hover 偵測 + 虛線草稿 + 提交/取消）
- [x] **Task 8（規格 §11A 節點資料映射）**：屬性面板新增 Data Mapping 區——input/output_data_sources（多重選擇自註冊資料集）+ in_control_parameters / out_quality_outputs / machine_mapping（tags）＋ saveMapping 持久化
- [x] **Task 9（i18n 三語）**：en / zh-TW / es-MX 新增 16 keys；**同時發現並補齊 es-MX 原本完全缺少的整個 processFlow 區塊**（既有 31 + 新 16 全翻譯）
- [x] **Task 10（最終驗證）**：引擎 **255 passed, 1 skipped**；`npx tsc --noEmit` clean + `npm run build` 成功
- **10 tasks 全部 commit 至 main**：`5706bef → fcaa2b5 → f465f0e → 531a59a → 9a8b5a3 → a00ba5b → 6eadc55 → c8240c5 → 2335b58`，每個 task 由 spec reviewer 逐行驗證後才 commit
- **註記**：上表先前 TASK/PROGRESS 計數「250 passed」為引擎舊值，本次實測為 255 passed

- [x] **時間序列數值欄位修復（commit `c5058b5`）**：`tsColumn`/`trendColumn` 預設改為自動落在第一個數值欄（原預設 `spec?.outputField` 可能為非數值如 `result`，導致 `compute_time_features` 於 `astype(float)` 拋錯、前端顯示錯誤 Alert 無輸出）；按鈕 handler 加守衛顯示明確 `valueColNotNumeric` 訊息（en/zh-TW/es-MX 三語）。驗證：三語 JSON 有效、tsc --noEmit clean、npm run build 成功。
- [x] **120s timeout 根因修復（SRP 版規）**：`fit_random_forest`/`fit_residual_hybrid`/cross-validation RF 改為有界樹（`max_depth=10, min_samples_leaf=5`）；`compute_shap` 新增 `max_explain=1000` 封頂實際解釋列數。實測 50k 列 shap 由 `>200s`（封鎖單執行緒引擎迴圈→`engine call timed out after 120s`）降為 **5.55s**。驗證：引擎 267 passed, 1 skipped。

- [x] **時間序列「計算特徵」一直轉圈 根因修復（commit pending）**：使用者回報重啟後仍轉圈、分布/趨勢正常（走同一引擎通道）→ 寫 Rust 集成測試 `time_series_returns_fast_live_engine`（spawn 真實引擎→import CSV→features/time_series）決定性複現 `Timeout(10s)`；reader 臨時加 logging 抓到 `ENGINE_READER_PARSE_FAIL len=8939 err=expected value column 414`。根因：時間序列 `lag`/`roll_std` 前幾列 warm-up 產生 **NaN**，Python `json.dumps` 預設輸出**非標準 `NaN`**（allow_nan=True），Rust `serde_json::from_str` 預設拒收 `NaN` → `continue` 靜默 drop response（mod.rs）→ `recv_timeout` 逾時 → 前端 promise 永不 resolve → 一直轉圈。分布/趨勢資料不含 NaN 故正常。修復：`main.py` `_plain_types`（所有 handler 序列化 choke-point，line 1741 每個 result 都經過）把非有限浮點（`not math.isfinite` → NaN/±Inf）→ `None`（`null`，Rust 接受）。系統性除錯確認：引擎 pipe 直測本來就 2ms 秒回，問題純在「NaN 非標準 JSON 被 Rust 拒收」，非計算複雜度、非 SHAP、非 Timestamp。新增 Rust 集成測試作為迴歸保護（此類超時 bug 引擎測試與前端 build 皆測不出）。驗證：Rust 2 passed（新測試 0.75s vs 修前 10s 超時）、引擎 267 passed 1 skipped、tsc --noEmit clean、npm run build 成功。

- [x] **時間序列結果表只顯示前 6 欄 修復（commit pending）**：計算特徵後 `<Table>` 用了 `tsFeatures.feature_columns.slice(0, 6)` 截斷 → 12 欄只剩 6 欄（`roll_mean_5/10`、`roll_std_5/10`、`drift` 等整欄消失）。user 對「表格分頁 page1/page2 切換時欄位名稱不變」感到困惑——其實跨分頁欄位本就不變，純粹是欄位被截斷、他以為第二個「sheet」該有不同欄位。修復：移除 `slice(0,6)`，改為「時間欄 timeColumn + 原始值欄 tsColumn + 全部 feature_columns」完整顯示，加 `scroll={{x:'max-content'}}` 橫向捲動與 `showSizeChanger:false`；NaN 溫風期列顯示 `—`。驗證：tsc --noEmit clean、npm run build 成功；user 確認表格顯示正常。

- [x] **時間序列圖特徵虛線跑掉/水平 修復（commit pending）**：Plot 的特徵 trace 用 `x: nonNull.map((_, i) => i)`——`filter` 掉溫風期 NaN（前幾列為 null）後，把 x 重新從 0 編號，每個特徵系列因此對不同數量的前導 NaN 做不同位移，與基底資料的 row-index 錯位，虛線被壓成水平錯線。修復：preserve 原始 row index——`tsFeatures.preview.map((r,i)=>({i,v:r[feat]})).filter(p=>p.v!=null)`，用 `p.i` 當 x 座標，使所有特徵系列與基底共用同一 row-index 軸正確對齊。驗證：tsc --noEmit clean、npm run build 成功。

- [x] **時間序列圖缺基底基準線 + 特徵線看水平 修復（commit pending）**：user 反映圖上只有 11 條水平虛線、無實線基底線（且切 tab 回才出現圖）。根因：`compute_time_features` 的 `preview`（time_series.py `feature_cols`）只含 time + 衍生特徵、**不含基底 value 欄** → 前端圖基底 trace `r[baseCol]` 全 undefined → 基準線消失。而特徵數值（delta/roll_std）皆圍繞 ~1.61、span 僅 ~0.005，同一 y 軸下天生看幾乎水平 → 「水平」是 scale 的合理結果；「缺基準線」是真 bug。修復：`preview_df = feature_df.join(result_df[value_columns].reset_index(drop=True))` 把原始 value 欄加回回傳列供圖畫實線參考，`feature_columns`/`n_features` 刻意維持衍生-only 不計基底欄。驗證：preview 含基底欄（output_thickness=1.6102）、n_features 仍 11、Rust 迴歸測試 0.77s pass、引擎 267 passed 1 skipped。

- [x] **Data Asset Management 獨立 tab（規格 §11A，MVP 範圍）**：新增 `src/features/data-assets/DataAssets.tsx` 動作頁——列出引擎 in-memory registry 已匯入資料集（`data/datasets`：來源檔/格式/編碼/列數/欄數）+ 每筆可 expand 顯示 `data/detect_fields` 欄位角色 Tag（reason tooltip）+ 備註/標籤 Input。**備註/標籤存前端 `localStorage`**（key `dataAssets.notes.v1`，以 dataset_id 索引），因引擎 registry 為 in-memory 非持久化。**純前端、無引擎變更**（`data/datasets`/`data/detect_fields` 已存在）。新增 `engine.ts` `DataAsset` interface + `getDataAssets()`（避免與既有 `getDatasets()`——後者走持久化 `project/datasets` manifest——命名衝突）；`assistantGuide.ts` 加 `dataAssets` guide；types/App/Sidebar 路由整合；i18n 三語 `nav.dataAssets` + `dataAssets.*`（en/zh-TW/es-MX）。驗證：三語 JSON 有效、tsc --noEmit clean、npm run build 成功。

- [x] **Copula 獨立 tab + 修補缺失的 IPC handler（Phase 11d，規格 §13/§14.4）**：發現 `copula/joint` 的 dispatch 分支（main.py:1286）參照 `_handle_copula_joint` 但該函式**從未定義**（僅靠運氣？實則是 latent NameError）→ 呼叫 `copula/joint` 會拋錯、且引擎完全無 copula 測試。**Backend**：main.py 新增 `_handle_copula_joint(params)`——讀取 `anomalies`（含 `anomaly_id`/`occurrence_probability`）、`correlation_matrix`、`direct_joints`、`seed`、`n_samples`（預設 100k）→ 呼叫 `compute_joint_probabilities` → `_plain_types(to_dict())`。**Tests**：`test_main_handlers.py` 新增 7 個 `copula/joint` 測試（independent 乘積、single→marginal、empty、direct mode、gaussian copula 回傳 pair_correlations、invalid matrix→fallback independent+warning、JSON serializable）。**Frontend**：新增 `src/features/copula/Copula.tsx`——從 `dataPipelineStore.anomalyScenarios` 多選異常、三種 mode（independent/gaussian_copula/direct）、gaussian 模式編輯相關矩陣（對角=1、對稱）、direct 模式輸入成對聯合機率、`n_samples`/`seed`、執行後顯示 marginal 卡片 + 成對聯合機率/獨立期許值/相關性指數表格 + fallback warning Alert；`engine.ts` `CopulaParams` 補 `n_samples`；types/App/Sidebar 路由整合（`DotChartOutlined`，放 monteCarlo 後）+ `assistantGuide` 加 copula guide；i18n 三語 `nav.copula` + copula UI keys 11 支（en/zh-TW/es-MX）。驗證：引擎 **273 passed, 1 skipped**（含 7 新 copula IPC 測試）、三語 JSON 有效、tsc --noEmit clean、npm run build 成功。

- [x] **Cloud Upload 去識別化設定改進（規格 §11A/§24）**：讓 Settings → Cloud Upload 卡片可選擇真實資料集並逐欄設定遮蔽策略。**Backend**：`deidentify.py` 的 `generate_preview`/`generate_upload_preview` 新增 `strategy_overrides`（`{col: "hash"|"masked"|"noise"}`，優先於 dtype 自動判定；`noise` 僅適用數值欄，非數值則忽略回退自動策略）＋ `apply_masking` 修正為輸出含遮蔽欄位、依每欄策略正確遮蔽（`replace`→"MASKED"，避免數值敏感欄洩漏原始值）；`main.py` 的 `_handle_cloud_preview`/`_handle_cloud_upload` 透傳 `strategy_overrides`。**Tests**：新增 `test_deidentify.py` 5 個策略覆寫單元測試 + `test_main_handlers.py` 2 個 IPC 透傳測試；全引擎 **280 passed, 1 skipped**。**Frontend**：`engine.ts` `CloudPreviewParams`/`CloudUploadParams` 加 `strategy_overrides`；Settings 卡片新增資料集下拉（`getDataAssets()`，取代 hardcode `demo_dataset`）+ 逐欄設定表格（`detectFields([], dataset_id)` 取欄位與 type；分類 transmit/mask/exclude + 遮蔽策略 hash/masked/noise，mask 才啟用策略選單）+ `deriveColumns()` 統一組 preview/confirm params；維持 Preview → Confirm modal → 審計歷史流程。i18n 三語 `cloud` section 補 13 keys（en/zh-TW/es-MX，其中 es-MX 補齊先前缺漏的整個 cloud section）。驗證：tsc --noEmit clean、npm run build 成功、三語 JSON 有效。

- [x] **Approval 獨立審核 tab（規格 §20，審核工作流）**：把模型/報告送審、核可/退回待審資源、檢視完整審核紀錄。**Backend**：新增 `reporting/registry.py`（in-memory `ReportRegistry`，threading lock + uuid + timestamp 排序）+ `_REPORT_REGISTRY`，`_handle_report_generate` 於格式分支前 `register(...)`（三格式皆登記，僅成功產出的報告）；新增 `_handle_report_list` + `report/list` dispatch（與 MODEL_REGISTRY 平行對稱）。審批 workflow（`approval/workflow.py`）沿用未改。**Reviewer 角色**：發現並修正 pre-existing 缺口——spec §20 定義 Reviewer（審核模型/報告）但系統角色只有 admin/engineer/viewer、後端 `approve`/`reject` 只收 `("reviewer","admin")`（前端 engineer 顯示可審核、後端卻拒絕）→ `auth/models.py` `UserRole` 加 `REVIEWER="reviewer"`、前端 `UserRole` 型別加 `'reviewer'`、Settings 註冊介面加 Reviewer 選項、Approval `canReview = reviewer || admin`。**Tests**：新增 `test_report_registry.py` 2 支 + `test_main_handlers.py` 1 支 `report/list` + `test_auth.py` 1 支 reviewer 註冊；全引擎 **284 passed, 1 skipped**。**Frontend**：`engine.ts` 補 `ReportRecord` + `listReports()`（approval/types functions 先前已存在，直接沿用）；新增 `src/features/approval/Approval.tsx`——資源表（model + report）Type/Resource/Status/Action、`getApprovalStatus` 求 status + record 覆寫、pending_review 對 reviewer/admin 顯示 Approve/Reject、Submit modal（type→resource→reviewer→comments）、Approve/Reject modal（`getCurrentUser()` 身份 + comments）、審核紀錄 audit table；types/App/Sidebar 路由整合（`AuditOutlined`）+ `assistantGuide` 加 approval guide；i18n 三語 `nav.approval` + `approval.*` 24 支 key（含 fix `records`）。spec reviewer 驗證：submit/approve/reject/audit trail 齊全、reviewer 角色前後端一致；HIGH 問題 `approval.records` 缺 key 已修（三語各加）+ `reviewer_role` fallback 改 `'reviewer'`。注意：`approve()` 接受從未送審（status None）的資源為 pre-existing workflow 行為，依 YAGNI 未改。驗證：引擎 284 passed 1 skipped、tsc --noEmit clean、npm run build 成功、三語 JSON 有效且 24 支 key 齊備。

- [x] **DataImport 模板下載微調（單按鈕 vs 多輸入單輸出 template）**：a)「模板下載」按鈕位置優化——與「選擇檔案」主按鈕**並排同一列**、由整排垂直次要按鈕改為 `type="link"` 次要鏈接按鈕（`DataImport.tsx`），視覺層次清楚、不佔垂直高度（user 確認此方案）。b) **模板 CSV 改為多輸入、單輸出架構**（回應用戶「多輸入、單輸出的架構」決定）：原本模板含兩個輸出欄（`output_thickness` + `output_pressure`），與平台單輸出 pipeline（`SpecConfiguration` 單一 `outputField` + 一組 LSL/USL/Target）衝突——改為 5 個輸入欄（`input_temperature/voltage/pressure/speed/load`）+ **單一輸出欄**（`output_thickness`）+ `result` OK/NG。i18n 三語 `dataImport.downloadTemplateDesc` 同步標示「多輸入、單輸出」架構（en/zh-TW/es-MX）。**不變更**：單輸出決策維持（下游 detection spec/analysis package/SPC/模型中心/Monte Carlo/預測與後端 `spec: {output_field,...}` 全部 key in 單一輸出；多輸出為無使用場景的彈性，暫不實作）。驗證：tsc --noEmit clean、npm run build 成功、三語 JSON 有效、無 `output_pressure` 殘留。

- [x] **專案儲存 ACL 修復（fs write_text_file not allowed by ACL）**：使用者儲存專案時報錯。根因：`src/lib/project.ts:48` `saveProjectFile` 呼叫 `writeTextFile`（@tauri-apps/plugin-fs），但 `src-tauri/capabilities/default.json` 只授權 `fs:default` —— Tauri 2 的 `fs:default` permission set 僅授予 app 專屬目錄的**唯讀**存取 + mkdir，寫入命令（`write_text_file`）未在 ACL 明確允許，且目標路徑不在 scope 內。修復：capability 追加 `{ "identifier": "fs:allow-write-text-file", "allow": [{ "path": "**" }] }`（grant 命令 + 放行 save dialog 使用者選取路徑）。驗證：`cargo check` pass（ACL regenerate 成功，僅既有 `EngineManager::stop` dead-code warning）。注意：需重新 build + relaunch app 才生效。

- [x] **專案儲存擴展 Tier 1（存異常情境/控制界限/analysis package）**：依 user 建議做第一層——把「使用者決策」狀態收進 `.piproj.json`。**格式 v1→v2**：`ProjectFile` 新增 `anomalyScenarios`（AnomalyScenario[]）、`controlLimits`（ControlLimitsMap）、`analysisPackage`；`buildProjectFile` 加 3 個可選參數（缺省空）。**Rust 端無涉**（純前端）。store 新增 `restoreAnalysis` bulk action——在 `setSpec`（會清空 controlLimits/anomalies/package）之後呼叫還原，`anomalyScenariosConfirmed` 由「所有 scenario 皆 user_confirmed」derive。`ProjectOverview.tsx`：save 帶入 3 state；open 還原（v1 檔案 null fallback 向後相容）。**不存**：模型結果/SPC/蒙地卡羅/預測輸出/報告/審核紀錄（留給 spec §11c project manifest 系統）。驗證：tsc --noEmit clean、npm run build 成功。

- [x] **es-MX 翻譯補齊（rebase 至 en 結構）**：檢查 README 的 es-MX 宣告時發現翻譯嚴重落後——**missing 168 keys**（`dataImport`/`project`/`processDefine`/`modelCenter`/`settings`/`monteCarlo`/`nav` 等多個 section 停在舊 schema）+ **stale 184 keys**（es 仍含 en 已移除的舊 key）。用 Node script 以 en.json 為 source of truth rebase：preserve 既有 541 筆西文、新增 168 筆翻譯（含 interpolation 變數一致）、移除 184 筆 stale。驗證：三語全 **709 keys**、0 missing、0 stale、JSON valid、{{var}} 無失配、tsc clean、build 成功。README「541 keys 完整翻譯」→「709 keys 三語 key set 完全一致」。

## 2026-09-05 — 製程流程 × 下游分析整合（FAI，10 tasks complete）

- [x] **Task 1（引擎，TDD）**：`ProjectManifest.association_keys` + `ProjectEngine.set_association_keys()`；test_manifest_nodes **8 passed**；全引擎 **287 passed, 1 skipped**。commit `cd7788e`
- [x] **Task 2（引擎，TDD）**：`project/flow-graph` 支援 `set_association_keys`；全引擎 **288 passed, 1 skipped**。commit `7db24b8`
- [x] **Task 3（engine.ts）**：`FlowGraph.association_keys` 型別 + `setAssociationKeys()`；tsc clean。commit `e0f85dd`
- [x] **Task 4（跳轉基礎設施）**：`processFlowNavStore`（pending/navigate/consume）+ `processFlowContext.ts`（`consumeNodeContext`/`findNodeById`/`dataSourceLoaded`）。commit `570d01c`
- [x] **Task 5（ProcessFlow UI）**：關聯鍵編輯區（`Select mode="tags"`）+ 節點屬性面板跳轉按鈕（SPC/MC/Exploration）＋i18n 三語 8 keys；命名更正 `jumpToSpc`（plan 筆誤 `jumpToSqc`）。commit `b535cd0`
- [x] **Task 6（App 訂閱）**：`useProcessFlowNavStore` pendingTarget → `setActiveTab`（同 tab guard 防迴圈）。commit `26f3b89`
- [x] **Task 7/7b（SPC，引擎 filter TDD + 前端）**：`spc/analyze` 加入 `filter_column`/`filter_value`（df-level mask）；SPC.tsx 消費跳轉上下文（StrictMode-safe）+ 來源 Tag + 節點篩選控制列。**deviation**：plan Step 4 前端 row-filter 不可行（無 data-source/column Select flow）→ user 核准改為引擎端 filter 關鍵參數透傳（數值不高估）。commit `74e44f4` / `c22c283` / `a15e04c`。**HIGH bug 修復（9e3d2b9）**：`consumeNodeContext()` 原在 render phase → dev StrictMode double-render 清空 pending → 移入 mount effect。commits `74e44f4 → b7f3100`
- [x] **Task 8（MC）**：`monte_carlo/run` 引擎 filter（3 新測試）+ MonteCarlo.tsx 消費上下文＋篩選控制；三語 +4 keys。commits `878f821` / `8160797`
- [x] **Task 9（Exploration + 共用 component）**：`data/distribution`/`data/series` 引擎 filter（6 新測試，handler 名為 `_handle_distribution`/`_handle_series`）+ Exploration 消費上下文；抽取共用 `NodeSourceFilter.tsx`（`filterable?: boolean`，time-series/GRR 不顯示 filter 控制）。commits `4ab2313` / `c76aff4` / `62ce296`
- [x] **Task 9.5 code review（909bf76）**：SPC `{name}` 單括號插值修正 + Exploration 篩選控制限定 distribution/trend tabs
- [x] **Task 10 hardening（引擎 zero-row guard + SPC numeric guard）**：`_apply_row_filter` helper 統一 4 handler inline mask + `raise ValueError("No rows match filter")`（4 新測試 RED→GREEN）；SPC 只對 numeric 欄位 `setColumn(pendingCtx.field)`。全引擎 **304 passed, 1 skipped**
- **驗證**：全引擎 `304 passed, 1 skipped`（baseline 287 + 17 新 test）；`npx tsc --noEmit` clean；`npm run build` 成功；三語 `processFlow`/`spc`/`monteCarlo`/`exploration` key-set parity `ok`
- **Commits**：`cd7788e, 7db24b8, e0f85dd, 570d01c, b535cd0, 26f3b89, 74e44f4, c22c283, a15e04c, 9e3d2b9, b7f3100, 878f821, 8160797, 4ab2313, c76aff4, 62ce296, 909bf76` + Task 10 (`feat(engine)` zero-row guard / `fix(spc)` numeric guard / `docs`)
- **Known follow-ups**：time-series / GRR 不套用節點 filter（前端 `filterable=false` 隱藏 + 引擎通道未接）

## 2026-09-05 — SPC EWMA/CUSUM 控制圖

- [x] **引擎（commit `a2d0f03`）**：`spc.py` 新增 `compute_ewma()`（EWMA 統計量 + 常數控制界限 + 違規偵測）與 `compute_cusum()`（兩邊 CUSUM 統計量 + 違規偵測）；`main.py` `_handle_spc_analyze` 加入 `ewma`/`cusum` 分支（支援 `ewma_lambda`/`ewma_L`/`cusum_k`/`cusum_H` 參數）
- [x] **前端（commit `673ecf0`）**：`engine.ts` `SPCAnalysisResult` 新增 `z_values`/`c_plus`/`c_minus`/`ewma_lambda`/`ewma_L`/`cusum_k`/`cusum_H`/`ucl`/`lcl`/`cl` optional fields；`analyzeSPC` params 加 lambda/L/k/H；`SPC.tsx` CHART_TYPES 加 `'ewma'`/`'cusum'`；子群組大小後加條件參數控制列；`buildPlotData` 加 ewma（Z(t) 線 + UCL/LCL/CL + 違規點）與 cusum（C⁺/C⁻ 雙線 + H limit + 違規點）分支；i18n 三語 spc 各 +11 keys（共 44 keys）
- [x] **修正欄位名稱（commit `36cb950`）**
- **驗證**：全引擎 **322 passed, 1 skipped**；`npx tsc --noEmit` clean；`npm run build` 成功

## 2026-09-05 — SPC 規格線（LSL/USL reference lines）

- [x] **位置圖加規格線、離散圖不加**：SPC.tsx 新增 `addSpecLines(ref?)`—只加在縱軸單位＝量測值的圖：i-mr **Individuals** 直畫（legend：`LSL`/`USL`）、xbar-r / xbar-s **X-bar** 標記 `LSL (ref)`/`USL (ref)`（參考線語意）——紅實線（`#f5222d`，user 反映黑線不佳後改）與 UCL/LCL 橘 dash 明顯區別、縱跨首尾 x；**MR / R / S 離散圖不加**（依 user 批准的逐張判定）。`spec.lsl`/`spec.usl` 各側獨立，僅畫已提供的側；純前端、無引擎/i18n 變更。驗證：`npx tsc --noEmit` clean、`npm run build` 成功。README Phase 8 補「規格線」一列。commits `8c67ec7` / `2b9709c`

## 2026-09-05 — SPC UCL/LCL 從未顯示的 bug 修復

- [x] **根因**：引擎 `compute_i_mr`/`compute_xbar_r`/`compute_xbar_s` 回傳**巢狀** `control_limits`（`{'x': {ucl/lcl/cl}, 'mr'(或 r/s): {...}}`，spc.py:145/211/283），但前端 `SPCCtrlLimits` 型別與 SPC.tsx/assistantData.ts 讀取的是**扁平** key（`x_ucl`/`i_ucl`/`i_center`…）→ 執行時全 `undefined` → `cl.x_ucl != null` 恆 false → UCL/LCL/CL 三條線**從 Phase 8 起從未畫出**；連 AI context 也一直是「UCL=null/LCL=null」（assistantData.ts:149 `!== null` 對 undefined 為真）。使用者回報規格線後追查發現（本次規格線功能無涉，讀的是 spec.lsl/usl）。
- [x] **修法**：`engine.ts` `analyzeSPC` 內新增 `flattenControlLimits(res)`——依 `chart_type` 把巢狀 group（`x`→i-mr 時 `i_*`、否則 `x_*`；`mr`/`r`/`s`→對應 prefix）攤平為 `*_ucl/*_lcl/*_center`，`chart_type` 一併帶上；單一 choke point，SPC.tsx 與 assistantData.ts 同時修好。無引擎/i18n/測試變更。
- [x] **side note**：i-mr 目前**只畫 Individuals 圖**（`yaxis2` 僅在非 i-mr 建立，SPC.tsx:254-256），MR 落點資料有計算但未 render——獨立於本次的既有範圍缺口，待 user 決定是否補。
- [x] **補 i-mr MR 子圖（user 要求）**：SPC.tsx i-mr 分支於 violations 後新增 MR 子圖——紫色 `#722ed1` lines+markers、`yaxis:'y2'`、x 對齊 `i+1`（mr[k] 對應點 k vs k-1 間距）；MR UCL（橘 dash）+ MR CL（綠 dash）條件式畫入（mirror R/S）；`plotLayout.yaxis2` 改為**一律建立**（不再限定非 i-mr）。驗證：`npx tsc --noEmit` clean、`npm run build` 成功。README Phase 8「控制圖」一列提及 i-mr 含 MR 子圖（I-MR 原本就如此宣稱，實作到位）。

## 2026-09-05 — 蒙地卡羅預測能力指數（Pp/Ppk, simulation-based）

- [x] **引擎（commit `bb1b019`）**：`run_monte_carlo` 回傳新增 `capability`——reuse `spc.compute_capability`，`subgroup_size=1` → σ within = overall σ → pp/ppk 為**整體 σ 語意**（simulation-based predicted capability）；spec 未**同時**設定 LSL+USL 時 pp/ppk 回傳 None（`compute_capability` 既有行為）；新增 2 測試（`test_main_monte_carlo.py` 11 passed）
- [x] **前端（commit `27eb722`）**：MonteCarlo 頁新增「預測能力指數（模擬）」card——Pp/Ppk antd `Statistic` + σ overall 註記，色彩閾值 ≥1.33 綠 / ≥1.0 橘 / <1.0 紅（mirror SPC `capacityColor`）；AI 助手 context 新增 `Predicted capability (simulation)` 一行；i18n 三語 `monteCarlo` +4 keys（30→34）
- [x] **驗證**：引擎 **306 passed, 1 skipped**（2 新測試 RED→GREEN）；`npx tsc --noEmit` clean；`npm run build` 成功；三語 i18n parity `ok`；spec reviewer APPROVE（capColor 閾值/hex 與 SPC 完全一致、`capability?: SPCCapability | null` 防禦型別 + 雙重 null-guard、rel tolerance 實測 justified）
- **Commits**：`bb1b019`（feat(engine): monte carlo predicted capability via compute_capability）/ `27eb722`（feat(monte-carlo): predicted capability card, AI context, i18n）

## 2026-09-05 — Task 1: Engine — Auto feature selection + RF hyperparameter exposure

- [x] **引擎（commit `cb49b49`）**：`fitters.py` 新增 `_auto_select_features` helper（快速 RF rank + threshold filtering，預設 threshold=0.01, max_features=5）；`fit_random_forest` 加 `auto_select_features`/`importance_threshold`/`max_features` 參數 + 改預設 `n_estimators=200, min_samples_leaf=3`；`ModelFit` 加 `selected_inputs` field + `to_dto()` 輸出；`main.py` `_handle_modeling_fit` 僅對 `random_forest` 透傳 RF hyperparams（其他 fitter 不受影響）
- [x] **測試（新增 2）**：`test_fit_random_forest_auto_select_features`（noise 被過濾，剩 ≤2 個 features）；`test_fit_random_forest_hyperparameters`（n_estimators=50, max_depth=5 → R² > 0.5）
- [x] **驗證**：引擎 **308 passed, 1 skipped**（baseline 306 + 2 新測試）；無回歸
- **Files changed**：`engine/src/process_intelligence_engine/modeling/fitters.py`, `engine/src/process_intelligence_engine/main.py`, `engine/tests/test_fitters.py`

## 2026-09-05 — 2.0 AI 模型擴充（Random Forest 完善 + XGBoost / LightGBM）

### 完成內容

- [x] **引擎 — `_auto_select_features` helper**（commit `cb49b49`）：
  - `fitters.py` 新增 `_auto_select_features(df, target, max_features=5, importance_threshold=0.01)`（快速 RF rank + threshold filtering）
  - `fit_random_forest` 暴露超參數：`n_estimators=200, max_depth=None, min_samples_leaf=3, auto_select_features, importance_threshold, max_features`
  - `ModelFit` 加 `selected_inputs` field + `to_dto()` 輸出
  - `main.py` `_handle_modeling_fit` 僅對 `random_forest` 透傳 RF hyperparams
- [x] **引擎 — XGBoost / LightGBM fitters**（commit `2073d53`）：
  - `fit_xgboost` / `fit_lightgbm`（共用 `_auto_select_features` + 相同 hyperparameter 介面）
  - `MODEL_FITTERS` 註冊 `"xgboost"` / `"lightgbm"`
  - `pyproject.toml` 加 `lightgbm>=4.0.0`（`xgboost` 早已存在）
  - `c94e11e`：補 empty-input guard（`if not selected_inputs: raise ValueError`）mirror RF
- [x] **SHAP 支援 XGBoost / LightGBM**（commit `7404acf`）：
  - `shap_explainer.py` 型別分派改 `fit.model_type in ("random_forest", "xgboost", "lightgbm")` 共用 `_compute_shap_tree`
- [x] **前端 — Tree Model Settings 卡片**（commit `f0d4979` / `2b71112`）：
  - `engine.ts` `ModelFitDTO` 加 `selected_inputs?`；`fitModel` params 加 7 個 hyperparameter
  - `ModelCenter.tsx`：Switch + InputNumbers（RF/XGBoost/LightGBM 顯示；minSamplesLeaf 僅 RF）；auto-select 後更新 selectedInputs + 通知
- [x] **i18n**：`modelCenter` 新增 8 keys × 3 語（treeModelAdvanced / autoFeatureSelect / nEstimators / maxDepth / minSamplesLeaf / learningRate / featureSelected / featureImportance）
- [x] **測試**：新增 8 支（RF auto-select、hyperparameters、edge case、XGBoost/LightGBM fit、SHAP）
- [x] **驗證**：引擎 **316 passed, 1 skipped**（baseline 304 + 12 新）；`npx tsc --noEmit` clean；`npm run build` 成功
- **Commits**：`cb49b49` / `2073d53` / `c94e11e` / `f0d4979` / `2b71112` / `7404acf`
- [x] **引擎 — SPC 批量分析 + 優化建議**（commit `9af8153`）：
  - `spc.py` 新增 `compute_spc_suggestions()`（檢查 Cpk/Rule4 shift/Rule5 trend/EWMA-CUSUM small_shift）
  - `main.py` 新增 `_handle_spc_batch_analyze`（`spc/batch_analyze` IPC，支援 i-mr/ewma/cusum 多欄）
  - 新增 4 支測試；全引擎 **326 passed, 1 skipped**（baseline 322 + 4）
  - **Files changed** — `engine/src/process_intelligence_engine/spc.py`, `engine/src/process_intelligence_engine/main.py`, `engine/tests/test_spc.py`, `engine/tests/test_main_spc.py`

## 2026-09-05 — SPC 批量分析 + 優化建議（multi-column + suggestions）

- [x] **引擎（commits `9af8153` / `641bd13` / `19f6549`）**：`spc.py` 新增 `compute_spc_suggestions()`（檢查 Cpk<1.0 error / Cpk<1.33 warning、Rule 4 shift、Rule 5 trend、EWMA/CUSUM small shift）；`main.py` 新增 `_handle_spc_batch_analyze`（`spc/batch_analyze` IPC，支援 i-mr/ewma/cusum 多欄批量分析並附 suggestions）；3 個 fixup commit 修正 indentation / chart_type consistency / xbar error / EWMA test
- [x] **前端（commit `678af29`）**：`engine.ts` 新增 `SPCSuggestion`/`SPCBatchResult` 型別 + `analyzeSPCBatch()`；`SPC.tsx` 加 `batchMode`/`selectedColumns`/`batchResult` state、批次切換按鈕、批次分析 UI、`handleBatchAnalyze`、`buildPlotData` 重構為接受 result 參數、`buildPlotLayout` 改為函數、比較表格 + 各欄圖表；`assistantData.ts` 補 suggestions 行；i18n 三語各 +7 keys（batchAnalyze/singleAnalysis/compareColumns/selectColumns/suggestions/noSuggestions/column）
- [x] **驗證**：全引擎 **327 passed, 1 skipped**（baseline 322 + 5）；`npx tsc --noEmit` EXIT 0；`npm run build` `✓ built in 10.43s`；三語 parity `ok count: 51`
- **Commits**：`9af8153` / `641bd13` / `19f6549` / `678af29`
