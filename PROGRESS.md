# PROGRESS.md

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