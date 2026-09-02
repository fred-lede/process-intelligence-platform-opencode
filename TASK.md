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
- `spc.py` — I-MR / X-bar+R / X-bar+S 控制圖 + Western Electric 7 規則 + Cp/Cpk/Pp/Ppk 能力指數
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

### Phase 9 — Monte Carlo 模擬
- `engine.ts` — TypeScript 類型 + `analyzeMonteCarlo()` API 函數
- `MonteCarlo.tsx` — 模擬 UI：模型選擇、參數設定、NG 機率、百分位數、直方圖 + CDF、異常排名表格
- i18n en/zh-TW（nav + monteCarlo section）
- Sidebar + App.tsx 路由整合
- 驗證 — 239 passed, 1 skipped (88% coverage), tsc/build clean

### Phase 10 — Interactive Prediction (What-if)
- `engine.ts` — `PredictionResult`, `ModelInfo`, `InputRange` TypeScript 類型 + `predictOutput()` + `getModelInfo()` API 函數
- TypeScript compile clean, build clean

## In Progress
- None

## Pending
- None

---
**測試狀態**：239 passed, 1 skipped (88% coverage)
**Code Stats**：~4,100 lines total
**Commits**：88 (main branch fully deployed)
