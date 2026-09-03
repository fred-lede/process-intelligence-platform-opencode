# TASK.md

## Completed
- Monte Carlo 計算引擎核心 (`monte_carlo.py`) — sample_from_distribution, apply_anomalies, predict_output, run_monte_carlo
- 14 tests covering normal/gamma/lognormal/histogram sampling, linear/quadratic prediction, anomaly injection, full simulation with/without bounds
- 234 passed, 1 skipped (88% coverage)
- Monte Carlo IPC handler (`monte_carlo/run`) — main.py import + handler + dispatch
- 5 IPC handler tests (basic, unknown model, with anomalies, no bounds, unknown dataset)

### Phase 0 — 基礎建設
- Tauri 2.0 + React 18 + TypeScript + Python 3.11 專案骨架
- Rust JSON-RPC IPC 通道 + 前端 API 封裝
- i18n en/zh-TW 基礎

### Phase 1 — 資料匯入
- Excel/CSV 匯入（編碼偵測、欄位辨識、品質檢查、分布分析）
- 資料管道 store (Zustand) + UI 4 步流程
- 專案保存/載入

### Phase 2 — 異常情境偵測
- Spec/Control/Engineering 三類異常檢測
- 分析資料包生成

### Phase 3a — 模型中心引擎核心
- metrics.py — RMSE/MSE/MAE/R²/Adjusted R²
- fitters.py — DOE linear/quadratic + random forest + residual hybrid
- registry.py — immutable model versions + status machine
- IPC handlers + 前端 API

### Phase 3b — Model Center UI 與分析
- ModelCenter.tsx — 模型列表 + 比較 + 核取方塊
- DOE Design Library (6種: 完全因析、分式因析、CCD、Box-Behnken、D-optimal、Taguchi)
- 交互作用分析 (熱圖)
- SHAP 可解釋性
- 外插風險評分
- 交叉驗證 + 殘差分析 + 實驗建議

### Phase 4 — 驗證實驗推薦
- model_selection.py — multi-model comparison with CV and composite scoring
- experiment_recommendation.py — 實驗推薦引擎
- Full Validation UI + model comparison table

### Phase 5 — 報告產生
- HTML/Excel 報告產生器
- `report/generate` IPC handler

### Phase 6 — 企業化
- 使用者角色 (Admin/Engineer/Viewer) + 登入/註冊/登出
- 稽核紀錄 (audit log)
- 設定頁面

### Phase 7 — AI 助手整合
- Ollama client (`ollama_client.py`) — chat/generate/list_models/health_check
- AI Provider 設定 (`settings/__init__.py`) — 支援 Ollama/OpenAI/Azure/Custom
- `ai/chat`, `ai/models`, `ai/health` IPC handlers
- AssistantPanel — 聊天 UI + 思考動畫 + Enter 支援
- 模型下拉選單（從 Ollama API 載入，支援搜尋）
- Settings persistence 修復（form.setFieldsValue + enginePing retry）
- 每次 chat 請求同步 base_url + model

### Phase 8 — SPC 統計製程控制
- `spc.py` — I-MR / X-bar+R / X-bar-S 控制圖 + Western Electric 7 規則 + Cp/Cpk/Pp/Ppk 能力指數
- `main.py` — `spc/analyze` + `spc/capability` IPC handlers
- `engine.ts` — SPC TypeScript 類型 + `analyzeSPC()` + `getSPCCapability()` API
- `SPC.tsx` — Plotly 控制圖 + 違規表格 + 能力指數卡片 + i18n en/zh-TW
- Sidebar + App.tsx 路由整合
- 驗證 — 220 passed, 1 skipped (88% coverage), tsc/build clean

### Phase 9 — 蒙地卡羅異常風險模擬
- `monte_carlo.py` — 抽樣引擎 + 異常整合 + DOE 預測 + NG 機率計算
- `main.py` — `monte_carlo/run` IPC handler
- `engine.ts` — SPC/Monte Carlo TypeScript 類型 + `analyzeMonteCarlo()` API
- `MonteCarlo.tsx` — Plotly 直方圖 + CDF + NG 機率卡片 + 百分位數 + 異常風險排名
- i18n en/zh-TW 完整支援
- 驗證 — 239 passed, 1 skipped (88% coverage), tsc/build clean

### Phase 10 — Interactive Prediction (What-if)
- `engine.ts` — `PredictionResult`, `ModelInfo`, `InputRange` TypeScript 類型 + `predictOutput()` + `getModelInfo()` API 函數
- TypeScript compile clean, build clean
- `Prediction.tsx` — 互動預測 UI：模型選擇下拉、Live 滑桿 + 數值輸入、自動預測、規格判定（In Spec / Below LSL / Above USL）、距離邊界顯示、還原預設值
- `importer.py` — `ColumnStats` 新增 `mean/std/min/max` 統計欄位
- i18n en/zh-TW 完整支援
- Sidebar + App.tsx 路由整合
- 驗證 — 250 passed, 1 skipped (88% coverage), tsc/build clean

### Phase 11 — 驗證實驗 (Validation Lab)
- `main.py` — ExperimentRecord + ExperimentRegistry + IPC handlers (record/list/get)
- `engine.ts` — ExperimentRecord type + recordExperiment/listExperiments/getExperiment APIs
- `ValidationLab.tsx` — 完整驗證 + 實驗建議 + 記錄實驗表單 + 實驗紀錄表格
- i18n en/zh-TW 完整支援
- App.tsx 路由整合
- 驗證 — 250 passed, 1 skipped (86% coverage), tsc/build clean

### Phase 11b — 短期任務補強
- **Logistic Regression** — `fitters.py` 新增 `fit_logistic_regression()`（二元 NG 預測，支援 accuracy/recall/AUC）
- **時間序列特徵** — `features/time_series.py`（lag/rolling/drift/連續超標）+ 2 個 IPC handlers
- **What-if 情境保存** — `prediction/scenario/save+list+delete` IPC + `Prediction.tsx` 新增儲存情境 Modal
- **審核工作流** — `approval/workflow.py`（submit/approve/reject + status + records）+ 5 個 IPC handlers
- i18n en/zh-TW：prediction.scenario* / timeSeries* / approval*
- 驗證 — 250 passed, 1 skipped (81% coverage), tsc/build clean

### Phase 11c — 中期任務（第一批）
- **PDF 匯出** — 引擎支援 `report/generate` format=pdf + `Report.tsx` 新增 PDF 按鈕
- **Weibull 迴歸** — `fit_weibull_regression()`（MLE 估計 shape k + log(λ)=Xβ），`MODEL_FITTERS` 註冊
- **可信度評分** — `validation.py:compute_credibility()`（6 維度：資料覆蓋/預測準確/統計穩定/工程合理/驗證程度/外插風險）
- **Credibility UI** — ValidationLab 模型表格新增可信度等級欄位 + 分數細節卡片
- i18n en/zh-TW：credibility.*
- 測試修正：`test_report_generate_unsupported_format` 改為 json
- 驗證 — 250 passed, 1 skipped (80% coverage), tsc/build clean

### Phase 11d — 中期任務（第二批）
- **Copula 聯合機率** — `copula.py`（高斯 Copula + 獨立 + 直接指定三種模式）+ IPC handler `copula/joint`
- **Monte Carlo 整合** — `apply_anomalies` 支援 Copula 相關性輸入，`run_monte_carlo` 回傳 `copula` 結果
- **Correlation matrix 驗證** — 正定矩陣檢查 + 失敗時自動 fallback 到獨立假設
- i18n en/zh-TW：copula.*
- 驗證 — 250 passed, 1 skipped (78% coverage), tsc/build clean

### Phase 11e — 中期任務（第三批）
- **GRR 量測系統分析** — `data/grr.py`（AIEM 方法，EV/AV/GRR/PV/TV/%GRR + verdict）+ IPC handler `data/grr`
- **時間序列 UI** — Exploration 新增 Time Series tab（lag/rolling/drift 圖表 + 特徵表格）
- **GRR UI** — Exploration 新增 GRR tab（選擇測量/零件/操作者欄位，分析結果 + 警告）
- i18n en/zh-TW：exploration.timeSeriesTab/GRR keys, grr.*
- 驗證 — 250 passed, 1 skipped (76% coverage), tsc/build clean

### Phase 11f — 多語言 es-MX
- **Español (México) 翻譯** — `es-MX.json`（541 keys，22 sections）
- `i18n/index.ts` 註冊 es-MX
- Sidebar 語言選單新增「Español (México)」選項
- 符合規格 19 多語言要求
- tsc/build clean

### Phase 11g — 雲端去識別化上傳 (spec 11A, 24)
- **deidentify.py** — `DeidentificationEngine`：敏感欄位 SHA-256 雜湊遮蔽、數值高斯噪音、上傳雜湊計算
- **IPC handlers** — `cloud/preview`（預覽遮罩結果）+ `cloud/upload`（確認上傳並記錄）+ `cloud/records`（上傳紀錄查詢）
- **Settings UI** — 雲端上傳區塊：noise σ 調整、預覽表格（傳輸/遮罩/排除欄位）、確認 Modal（強制確認機制）
- **審核紀錄** — operator、provider、model_version、mask_rules、upload_hash、purpose
- i18n en/zh-TW：cloud.*（20 keys）
- 驗證 — 250 passed, 1 skipped (74% coverage), tsc/build clean

### Phase 11h — 檔案系統資料目錄結構 (spec 11A)
- **project/manifest.py** — `ProjectEngine`：on-disk `project_manifest.json` + 9 個目錄自動建立
- **資料模型** — `DatasetRegistration`（checksum/quality/cloud_policy）+ `ProcessGroup` + `ProcessNode`
- **18 個 IPC handlers**：manifest/create/open/settings/dirs/source-dirs/scan/process-groups/group/create/update/delete/templates/nodes/node/create/update/delete/datasets/dataset/register/update
- **TypeScript** — 20 API 函數 + 完整類型（ProjectManifest/ProcessGroup/ProcessNode/DatasetRegistration/ScanResult）
- **i18n** en/zh-TW：project.*（53 keys）
- 驗證 — 250 passed, 1 skipped (71% coverage), tsc/build clean

### Phase 11i — 製程流程圖 (spec 11A)
- **ProcessFlow.tsx** — SVG 流程圖：拓撲排序佈局 + 節點繪製 + 箭頭邊 + 選中高亮
- **節點管理**：新增 Modal（名稱/類型/重工政策）+ 刪除（含確認）
- **連接管理**：多選連接目標節點 + 斷開連接
- **圖形驗證**：環狀檢測 + 孤立節點警告（`validate_flow_graph` IPC）
- **Sidebar** 新增「製程流程」導航項目
- **i18n** en/zh-TW：processFlow.*（31 keys）
- 驗證 — 250 passed, 1 skipped (70% coverage), tsc/build clean

---
**專案總體**：
- **代碼行數**：~15,100 行
- **Commits**：202
- **測試**：250 passed, 1 skipped（70% coverage）
- **Phase 0–11i**：全部完成 ✅
- **多語言**：en / zh-TW / es-MX（3 種）✅
- **模型類型**：6 種（linear / quadratic / RF / hybrid / logistic / weibull）✅
- **AI 助手**：4 種 provider（Ollama / OpenAI / Azure / Custom）✅
- **SPC**：I-MR / X-bar+R / X-bar-S + WE 7 規則 + Cp/Cpk/Pp/Ppk ✅
- **蒙地卡羅**：正常/異常抽樣 + Copula 聯合機率 + NG 機率 ✅
- **驗證實驗**：Full validation + 實驗建議 + 實驗記錄 + 可信度評分 ✅
- **GRR**：AIEM 方法 + 判定 + 警告 ✅
- **時間序列**：lag/rolling/drift/連續超標 ✅
- **審核工作流**：submit/approve/reject（Reviewer 角色）✅
- **雲端去識別化**：遮罩預覽 + 強制確認 + 審核紀錄 ✅
- **專案檔案系統**：project_manifest.json + 9 目錄 + 製程群組/節點 ✅
- **製程流程圖**：SVG 可交互編輯器 + 拓撲佈局 + 環狀檢測 ✅