# Process Intelligence Platform

**作者**: Fred Wang

可解釋、可追溯、可切換模型的製程分析平台。支援 macOS / Windows 桌面應用，結合傳統 DOE 與 AI 輔助分析。

## GitHub

[fred-lede/process-intelligence-platform-opencode](https://github.com/fred-lede/process-intelligence-platform-opencode)

## 技術架構

- **前端**: React 18 + TypeScript + Ant Design 5
- **桌面框架**: Tauri 2.0 (Rust)
- **分析引擎**: Python 3.11+ (Polars, scipy, scikit-learn, xgboost, statsmodels)
- **本地 AI**: Ollama (Phase 5 整合)
- **資料儲存**: SQLite (metadata) + Parquet (分析資料)

## 快速開始

### 前置需求

- Rust 1.70+
- Node.js 18+
- 系統 WebView (macOS: WebKit / Windows: WebView2)

### 開發

```bash
npm install
npm run tauri dev
```

### 測試

```bash
# 前端 type-check + build
npx tsc --noEmit
npm run build

# Python 引擎 (單元 + 端到端子進程測試)
cd engine && source .venv/bin/activate && pytest

# Rust (引擎即時通訊測試)
cd src-tauri && cargo test engine::tests::pings_live_engine
```

## 專案結構

```
├── src/            # React 前端
│   ├── features/   #   - project / data-import / process-define / exploration
│   ├── stores/     #   - dataPipelineStore (import→fields→quality→spec)
│   ├── lib/        #   - engine.ts (IPC API) / filePicker / project (save/load)
│   └── i18n/       #   - en.json / zh-TW.json
├── src-tauri/      # Tauri Rust 後端 (EngineManager, dialog/fs plugins)
├── engine/         # Python 分析引擎
│   ├── src/process_intelligence_engine/
│   │   ├── main.py        # IPC dispatch + dataset registry + JSON 淨化
│   │   ├── data/          # importer / field_detector / quality / distribution
│   │   ├── analysis/      # anomaly scenarios / analysis package
│   │   └── modeling/      # metrics / fitters / registry (DOE + AI + hybrid)
│   └── tests/             # 93 tests (含 test_e2e_pipeline.py 子進程 E2E)
├── ai/             # AI 服務層 (Phase 5)
├── projects/       # 使用者專案 (gitignore)
└── docs/           # 規格文件
```

## Phase 1 功能 (已完成 ✅)

- **資料匯入**: Excel (.xlsx/.xls) / CSV (編碼偵測 big5 等、分隔符偵測、預覽)
- **欄位自動辨識**: 角色 + 型態 + AI 信心度 + 可調整確認
- **資料品質檢查**: 缺失值、重複、常數欄位、極端離群值、OK/NG 失衡等
- **製程定義**: 輸出欄位、單位、LSL/USL/目標值 (含驗證)、輸入參數
- **探索分析**: Plotly 直方圖 + 分布配適密度曲線 (AIC/BIC/KS 排序)、趨勢圖 + 規格線
- **專案保存/載入**: `.piproj.json`
- **驗證**: 引擎 93 tests (覆蓋率 88%)、Rust↔Python IPC 測試、tauri dev 三進程冒煙測試

### 資料流 (Phase 1)

```
匯入 → engine dataset registry (記憶體, 資料不上雲)
     → 欄位辨識 → 角色確認 → 品質檢查
     → 製程定義 (output/規格) → 分布配適 + 趨勢圖
     → 專案保存 (.piproj.json, 重開時重新匯入重建 registry)
```

## Phase 2 功能 (已完成 ✅)

- **異常情境偵測**: spec 異常（超規格）+ control 異常（超管制線 mean±3σ + runs rule）+ engineering 異常（使用者自訂）
- **分析資料包**: 資料指紋 + 完成度檢查（output+input 欄位確認）
- **ProcessDefine UI**: 管制界限 LCL/UCL 手動覆寫 + 自動 3σ 建議
- **異常情境 UI**: 偵測觸發 → 場景表格（逐項/全部確認）
- **分析資料包摘要卡**: row/col/field_roles/spec/異常數 + 完成度
- **驗證**: 引擎 68 tests (覆蓋率 86%)

## Phase 3a 功能 (已完成 ✅)

- **模型比較指標**: RMSE, MSE, MAE, R², Adjusted R²
- **DOE 模型配適**: 線性 + 二次（含 intercept、平方項、交互項）
- **隨機樹回歸**: sklearn RandomForestRegressor
- **殘差混合模型**: Y = f_DOE(X) + r_RF(X)（DOE 擷取趨勢 + AI 殘差補償）
- **不可變版本登錄**: 狀態機 draft → pending_validation → validated → approved；單調遞增版本、永不覆寫
- **IPC handlers**: `modeling/fit`、`modeling/list`、`modeling/transition`
- **前端 modeling API**: ModelType/ModelStatus/ModelMetrics/ModelFitDTO 型別 + API 函數
- **驗證**: 引擎 93 tests (覆蓋率 88%)

## 設計原則

- 不綁定特定產業 (非僅車載 ECU)
- 原始資料預設不送往雲端
- 傳統 DOE 永遠保留為回退方案
- 所有自動建議可解釋、可追溯、可人工覆核
