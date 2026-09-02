# TASK.md

## Completed

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

### Phase 8 — SPC 計算引擎
- `spc.py` — I-MR、X-bar/R、X-bar/S 管制圖
- Western Electric 七規則檢測
- 製程能力分析 (Cp/Cpk/Pp/Ppk)
- 11 個測試全部通過

### Phase 9 — SPC IPC Handler
- `spc/analyze` — I-MR / X-bar-R / X-bar-S 管制圖分析
- `spc/capability` — 製程能力分析
- 7 個測試全部通過

### Phase 10 — SPC 前端 API
- `engine.ts` 新增 SPC 類型 (SPCCapability, SPCViolation, SPCCtrlLimits, SPCAnalysisResult, SPCCapabilityResult)
- 新增 `analyzeSPC()` 和 `getSPCCapability()` 函數

### Phase 11 — SPC 前端頁面
- `src/features/spc/SPC.tsx` — I-MR / X-bar-R / X-bar-S 控制圖 + Plotly
- Western Electric 七規則違規表格
- 製程能力分析 (Cp/Cpk/Pp/Ppk) 與色標評級
- i18n en/zh-TW 完整支援
- Sidebar 新增 SPC 選單項目
- App.tsx 路由綁定

## In Progress
- None

## Pending
- None

---
**測試狀態**：220 passed, 1 skipped (88% coverage)
**Code Stats**：~3,993 lines total
**Commits**：83 (main branch fully deployed)
