# Process Intelligence Platform

**作者**: Fred Wang

可解釋、可追溯、可切換模型的製程分析平台。支援 macOS / Windows 桌面應用，結合傳統 DOE 與 AI 輔助分析。

## GitHub

[fred-lede/process-intelligence-platform-opencode](https://github.com/fred-lede/process-intelligence-platform-opencode)

## License

[MIT License](LICENSE) — Copyright (c) 2026 Fred Wang

## 技術架構

- **前端**: React 18 + TypeScript + Ant Design 5 + Zustand + i18next
- **桌面框架**: Tauri 2.0 (Rust)
- **分析引擎**: Python 3.11（不支援 3.12+） (numpy, pandas, scikit-learn, scipy, shap)
- **圖表庫**: Plotly.js
- **資料儲存**: 記憶體 DatasetRegistry (原始資料不上雲)

## 快速開始

### 前置需求

- Rust 1.77+（[安裝指南](https://www.rust-lang.org/tools/install)）
- Node.js 18+
- Python 3.11（不支援 3.12+）
- 系統 WebView (macOS: WebKit / Windows: WebView2)

### 安裝 Rust（若尚未安裝）

```bash
# macOS / Linux
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Windows
# 下載並執行 https://win.rustup.rs/x86_64
# 或從 Microsoft Store 安裝 Rust
```

安裝後重啟終端機，或執行：

```bash
source $HOME/.cargo/env
```

確認安裝成功：

```bash
cargo --version
# 應輸出：cargo 1.xx.x
```

### 安裝與開發

```bash
# 安裝前端依賴
npm install

# 建立 Python 虛擬環境（仅需第一次）
cd engine
python3 -m venv .venv
# On Windows:
# .venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate
pip install -e ".[dev]"
cd ..

# 確認 Rust 環境
source $HOME/.cargo/env 2>/dev/null || true
cargo --version

# 啟動開發環境
npm run tauri dev
```

### 首次部署注意事項

在新電腦上首次部署時，請確保：

1. **Rust 已安裝**：執行 `cargo --version` 確認
2. **Python venv 已建立**：執行 `cd engine && python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
3. **Node 模組已安裝**：執行 `npm install`
4. **瀏覽器 WebView**：macOS 內建 WebKit，Windows 需安裝 WebView2 Runtime

若啟動時出現以下錯誤，請檢查：

- **`failed to run cargo metadata`**：Rust 未安裝或 PATH 未設定，執行 `source $HOME/.cargo/env`
- **`engine start failed`**：Python venv 未建立，執行 `cd engine && python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
- **`Failed to load data`**：引擎未就緒，等待 3 秒後自動重試；若持續失敗請檢查 Python 路徑


### 測試

```bash
# 前端 type-check
npx tsc --noEmit

# 前端 build
npm run build

# Python 引擎測試
cd engine && .venv/bin/pytest -q

# Rust IPC 測試
cd src-tauri && cargo test engine::tests::pings_live_engine
```

## 專案結構

```
├── src/                    # React 前端
│   ├── features/           #   功能頁面
│   │   ├── project/        #     專案總覽
│   │   ├── data-import/    #     資料匯入
│   │   ├── process-define/ #     製程定義
│   │   ├── exploration/    #     探索分析
│   │   ├── model-center/   #     模型中心
│   │   ├── report/         #     報告產生
│   │   └── settings/       #     系統設定
│   ├── stores/             #   Zustand 狀態管理
│   ├── lib/                #   IPC API 封裝
│   └── i18n/               #   多語言 (en/zh-TW)
├── src-tauri/              # Tauri Rust 後端
├── engine/                 # Python 分析引擎
│   ├── src/process_intelligence_engine/
│   │   ├── main.py         # IPC dispatch + registry
│   │   ├── data/           # importer / field_detector / quality
│   │   ├── analysis/       # anomaly scenarios
│   │   ├── modeling/       # metrics / fitters / registry / doe / interactions / shap / validation
│   │   └── auth/           # 使用者角色與稽核
│   └── tests/              # 181 tests
├── assets/                 # 應用程式圖示
├── data/                   # 測試資料範例
└── docs/                   # 規格文件
```

## 功能總覽

### Phase 1 — 資料基礎 ✅

- **資料匯入**: Excel (.xlsx/.xls) / CSV (編碼偵測 big5/cp950/gb18030/shift_jis、分隔符偵測、預覽)
- **欄位自動辨識**: 角色 + 型態 + AI 信心度 + 可調整確認
- **資料品質檢查**: 缺失值、重複、常數欄位、極端離群值、OK/NG 失衡等
- **製程定義**: 輸出欄位、單位、LSL/USL/目標值 (含驗證)、輸入參數
- **探索分析**: Plotly 直方圖 + 分布配適密度曲線 (AIC/BIC/KS 排序)、趨勢圖 + 規格線
- **專案保存/載入**: `.piproj.json`

### Phase 2 — 異常情境 ✅

- **異常情境偵測**: spec 異常（超規格）+ control 異常（超管制線 mean±3σ + runs rule）+ engineering 異常（使用者自訂）
- **分析資料包**: 資料指紋 + 完成度檢查（output+input 欄位確認）
- **ProcessDefine UI**: 管制界限 LCL/UCL 手動覆寫 + 自動 3σ 建議
- **異常情境 UI**: 偵測觸發 → 場景表格（逐項/全部確認）
- **分析資料包摘要卡**: row/col/field_roles/spec/異常數 + 完成度

### Phase 3 — 模型中心 ✅

- **模型比較指標**: RMSE, MSE, MAE, R², Adjusted R²
- **DOE 模型配適**: 線性 + 二次（含 intercept、平方項、交互項）
- **隨機樹回歸**: sklearn RandomForestRegressor
- **殘差混合模型**: Y = f_DOE(X) + r_RF(X)（DOE 擷取趨勢 + AI 殘差補償）
- **不可變版本登錄**: 狀態機 draft → pending_validation → validated → approved；單調遞增版本、永不覆寫
- **IPC handlers**: `modeling/fit`、`modeling/list`、`modeling/transition`
- **前端 modeling API**: ModelType/ModelStatus/ModelMetrics/ModelFitDTO 型別 + API 函數

### Phase 3b — UI 增強 ✅

- **模型中心頁面**: 模型配適表單 + 模型列表 + 比較表
- **模型比較增強**: 勾選多模型並排對比、高亮最佳指標
- **DOE 設計庫**: Full Factorial / Fractional Factorial / CCD / Box-Behnken / D-optimal / Taguchi (L4/L8/L9/L16)
- **交互作用分析**: 二因素交互作用偵測 + 熱圖視覺化
- **SHAP 可解釋性**: 特徵重要性圖 + SHAP 摘要圖
- **外插風險評分**: 預測超出訓練範圍時警告
- **交叉驗證 + 殘差分析**: k-fold CV、殘差分佈統計、Normality Test、Durbin-Watson

### Phase 4 — 驗證實驗推薦 ✅

- **模型選擇**: 多模型並排比較 + 自動評分推薦
- **實驗推薦引擎**: 基於殘差模式推薦下一步實驗
  - 強交互作用 → 建議交互實驗
  - 殘差偏斜 → 建議轉換
  - 異方差 → 建議範圍擴充
- **完整驗證流程**: `modeling/validation/full` IPC handler

### Phase 5 — 報告產生 ✅

- **HTML 報告**: 專案資訊、欄位角色、模型比較、交互作用、實驗建議
- **Excel 匯出**: 多 Sheet（專案資訊、欄位角色、模型比較、交互作用矩陣、實驗建議）
- **報告頁面**: 即時預覽 + 下載功能

### Phase 6 — 企業化 ✅

- **使用者角色**: Admin / Engineer / Viewer 三級權限
- **稽核紀錄**: 登入/登出、模型配適、報告匯出、使用者註冊
- **設定頁面**: 登入/登出、使用者管理、稽核日誌表格
- **權限控制**: 基於角色的功能存取控制

## 測試統計

| 項目 | 數值 |
|------|------|
| **測試總數** | 181 tests |
| **覆蓋率** | 89% |
| **Commits** | 72 |

## 設計原則

- 不綁定特定產業 (非僅車載 ECU)
- 原始資料預設不送往雲端
- 傳統 DOE 永遠保留為回退方案
- 所有自動建議可解釋、可追溯、可人工覆核
- AI 助手支援多語言 (en/zh-TW)

## 技術決策記錄

| 決策 | 選擇 |
|------|------|
| 桌面框架 | Tauri 2.0 |
| Python 版本 | 3.11 (bundled venv) |
| 本地 AI | 延後 (Phase 5+) |
| i18n 語言 | en + zh-TW |
| 資料粒度 | 單片產品/單一測試樣本 |
| 模型儲存 | 記憶體 (DatasetRegistry) |

## 快速測試資料

專案提供預存測試資料：

```
data/test_dataset.csv
```

包含 82 筆資料，4 個輸入變數 (temperature, pressure, time, humidity) + 1 個輸出變數 (yield)，適合測試完整分析流程。

## 開發者

- **作者**: Fred Wang
- **授權**: MIT License
