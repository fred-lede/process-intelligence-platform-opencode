# Process Intelligence Platform

可解釋、可追溯、可切換模型的製程分析平台。支援 macOS / Windows 桌面應用，結合傳統 DOE 與 AI 輔助分析。

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
│   │   └── data/          # importer / field_detector / quality / distribution
│   └── tests/             # 55 tests (含 test_e2e_pipeline.py 子進程 E2E)
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
- **驗證**: 引擎 55 tests (覆蓋率 84%)、Rust↔Python IPC 測試、tauri dev 三進程冒煙測試

### 資料流 (Phase 1)

```
匯入 → engine dataset registry (記憶體, 資料不上雲)
     → 欄位辨識 → 角色確認 → 品質檢查
     → 製程定義 (output/規格) → 分布配適 + 趨勢圖
     → 專案保存 (.piproj.json, 重開時重新匯入重建 registry)
```

## 設計原則

- 不綁定特定產業 (非僅車載 ECU)
- 原始資料預設不送往雲端
- 傳統 DOE 永遠保留為回退方案
- 所有自動建議可解釋、可追溯、可人工覆核
