# Process Intelligence Platform

**Languages:** [繁體中文](README.md) · [English](README_En.md)

**作者**: Fred Wang

可解釋、可追溯、可切換模型的製程分析平台。支援 macOS / Windows 桌面應用，結合傳統 DOE 與 AI 輔助分析。

## GitHub

[fred-lede/process-intelligence-platform-opencode](https://github.com/fred-lede/process-intelligence-platform-opencode)

## License

[MIT License](LICENSE) — Copyright (c) 2026 Fred Wang

## 技術架構

- **前端**: React 18 + TypeScript + Ant Design 5 + Zustand + i18next
- **桌面框架**: Tauri 2.0 (Rust)
- **分析引擎**: Python 3.11 或 3.12（不支援 3.13+） (numpy, pandas, scikit-learn, scipy, shap)
- **圖表庫**: Plotly.js
- **資料儲存**: 記憶體 DatasetRegistry (原始資料不上雲)

## 快速開始

### 前置需求

- Rust 1.77+（[安裝指南](https://www.rust-lang.org/tools/install)）
- Node.js 18+
- Python 3.11 或 3.12（專案以 `uv` 管理；不支援 Python 3.13+）
- 系統 WebView (macOS: WebKit / Windows: WebView2)
- **macOS：OpenMP 執行時（libomp）**——xgboost/lightgbm 的 macOS wheel 不會自行 bundle OpenMP，需系統安裝：
  ```bash
  brew install libomp
  ```
  Windows/Linux 不需要（Windows wheel 自帶 `vcomp140.dll`、Linux wheel 已 bundle）。

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

# 建立 Python 3.12 虛擬環境（僅需第一次）
cd engine
uv venv --python 3.12
uv sync --extra dev
cd ..

# 確認 Rust 環境
source $HOME/.cargo/env 2>/dev/null || true
cargo --version

# 啟動開發環境
npm run tauri dev
```

發行建置（安裝檔）必須先凍結分析引擎，否則安裝後的 App 沒有 Python 可用、引擎無法啟動：

```bash
npm run engine:build   # PyInstaller -> src-tauri/resources/engine/
npm run tauri build
```

`npm run build:app` 等同上面兩行。詳見 [部署指南](docs/deployment.md#共通建置流程)。

### 首次部署注意事項

在新電腦上首次部署時，請確保：

1. **Rust 已安裝**：執行 `cargo --version` 確認
2. **Python venv 已建立**：執行 `cd engine && uv venv --python 3.12 && uv sync --extra dev`
3. **Node 模組已安裝**：執行 `npm install`
4. **瀏覽器 WebView**：macOS 內建 WebKit，Windows 需安裝 WebView2 Runtime
5. **macOS 需安裝 libomp**：執行 `brew install libomp`（缺失會導致 xgboost 載入失敗、引擎無法啟動，見下方排錯）
6. **PDF 匯出需安裝 WeasyPrint 系統相依套件**：依作業系統執行 [PDF 報告部署指南](docs/deployment.md#pdf-報告匯出weasyprint)；僅安裝 Python 套件不足以輸出 PDF。
7. **TFT / PyTorch**：時間序列模型階梯已支援 TFT；依 [時間序列深度模型部署指南](docs/deployment-time-series.md) 安裝平台相容的 PyTorch 環境。

若啟動時出現以下錯誤，請檢查：

- **`failed to run cargo metadata`**：Rust 未安裝或 PATH 未設定，執行 `source $HOME/.cargo/env`
- **`engine start failed`**：Python venv 未建立，執行 `cd engine && python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]" && pip install -r requirements.txt`
- **`Failed to load data`**：引擎未就緒，等待 3 秒後自動重試；若持續失敗請檢查 Python 路徑
- **`無法連線分析引擎 … failed to write to engine: Broken pipe (os error 32)`（macOS）**：引擎子進程啟動時 crash。最常見為 macOS 缺少 OpenMP（libomp）→ xgboost/lightgbm import 失敗 → 引擎 module import 中斷。執行 `brew install libomp` 後重新 build + 部署。若 `engine/.venv` 缺少 `lightgbm`，先執行 `uv pip install 'lightgbm>=4.0.0'`


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

### LightGBM GPU 支援（選配）

LightGBM 的 GPU 訓練為**選配功能**，預設使用 CPU。若需啟用 GPU 加速，請確認以下條件後重新編譯：

**前置條件：**
- NVIDIA 顯示卡（不支援 Apple MPS / Metal）
- CUDA Toolkit 11.x 或 12.x（與 LightGBM 版本相容）
- cuBLAS、CUDNN
- CMake 3.16+
- 系統有 GPU 驅動程式

**編譯步驟：**

```bash
# 1. 取得 LightGBM 原始碼（版本需與 requirements.txt 一致）
git clone --recursive https://github.com/microsoft/LightGBM.git
cd LightGBM

# 2. 建立 build 目錄
mkdir build && cd build

# 3. CMake 開啟 GPU 支援
cmake .. -DUSE_GPU=1 \
  -DOpenCL_LIBRARY=/usr/local/cuda/lib64/libOpenCL.so \
  -DOpenCL_INCLUDE_DIR=/usr/local/cuda/include

# 4. 編譯
make -j$(nproc)

# 5. 安裝到專案 venv
cd ../python-package
python setup.py install
```

**Windows：**
```powershell
# 確保 CUDA 已安裝，然後：
git clone --recursive https://github.com/microsoft/LightGBM.git
cd LightGBM
mkdir build && cd build
cmake .. -G "Visual Studio 17 2022" -A x64 -DUSE_GPU=1 -DCMAKE_BUILD_TYPE=Release
cmake --build . --config Release
cd ..\python-package
pip install .
```

**驗證 GPU 是否可用：**
```python
import lightgbm as lgb
import numpy as np
X = np.random.randn(100, 4)
y = np.random.randn(100)
train = lgb.Dataset(X, label=y)
params = {'device': 'gpu', 'verbose': -1}
model = lgb.train(params, train, num_boost_round=10)
print('GPU OK')
```

**常見錯誤：**
- `GPU Tree Learner was not enabled in this build` → pip 版未編譯 GPU，需從原始碼編譯
- `Unknown device type mps` → Apple Silicon 不支援，只能用 CPU
- `CUDA error` → CUDA 版本與 LightGBM 不相容，檢查 CUDA Toolkit 版本

**建議：** 一般用途使用預設 CPU 即可。GPU 加速在資料量超過 10 萬行且 CPU 訓練時間明顯不足時才值得部署。

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
│   └── tests/              # 585 tests
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
- **樹模型（Random Forest / XGBoost / LightGBM）**: 超參數調控（n_estimators, max_depth, min_samples_leaf, learning_rate）+ 自動特徵選取（`_auto_select_features`，基於 feature_importances_ rank + threshold filtering）
- **殘差混合模型**: Y = f_DOE(X) + r_RF(X)（DOE 擷取趨勢 + AI 殘差補償）
- **不可變版本登錄**: 狀態機 draft → pending_validation → validated → approved；單調遞增版本、永不覆寫
- **IPC handlers**: `modeling/fit`、`modeling/list`、`modeling/transition`
- **前端 modeling API**: ModelType/ModelStatus/ModelMetrics/ModelFitDTO 型別 + API 函數

### Phase 3b — UI 增強 ✅

- **模型中心頁面**: 模型配適表單 + 模型列表 + 比較表
- **模型比較增強**: 勾選多模型並排對比、高亮最佳指標
- **樹模型設定卡片**: RF/XGBoost/LightGBM 顯示超參數 Switch + InputNumbers（RF 獨有 min_samples_leaf）；自動特徵選取後更新 selectedInputs 並顯示通知
- **DOE 設計庫**: Full Factorial / Fractional Factorial / CCD / Box-Behnken / D-optimal / Taguchi (L4/L8/L9/L16)
- **交互作用分析**: 二因素交互作用偵測 + 熱圖視覺化
- **SHAP 可解釋性**: 特徵重要性圖 + SHAP 摘要圖（支援 RF / XGBoost / LightGBM）
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
- **SPC 控制圖**: I-MR 控制圖 SVG（Individuals + MR 雙子圖）、能力指數表格、違規統計、優化建議（自動對 output columns 分析）
- **Excel 匯出**: 多 Sheet（專案資訊、欄位角色、模型比較、交互作用矩陣、實驗建議）
- **PDF 匯出**: 使用 WeasyPrint 生成 PDF（需系統圖形庫）
- **報告頁面**: 即時預覽 + 下載功能

### Phase 6 — 企業化 ✅

- **使用者角色**: Admin / Engineer / Viewer 三級權限
- **稽核紀錄**: 登入/登出、模型配適、報告匯出、使用者註冊
- **設定頁面**: 登入/登出、使用者管理、稽核日誌表格
- **權限控制**: 基於角色的功能存取控制

### Phase 7 — AI 助手 ✅

- **Ollama 客戶端**: 聊天/生成/列出模型/健康檢查
- **多 Provider 支援**: Ollama (local) / OpenAI (cloud) / Azure / Custom (自訂 Endpoint)
- **AI 助手面板**: 右側可收合，顯示目前 Provider·模型與思考狀態
- **安全輸入**: 雙 Enter 送出，避免編輯期間誤發訊息
- **跨頁上下文**: SPC、分布、模型、模擬、預測與報告摘要可供助手解讀
- **設定持久化**: 保留模型與 API 金鑰，避免遮罩值覆寫原始金鑰

### Phase 8 — SPC 統計製程控制 ✅

- **控制圖**: I-MR / X-bar+R / X-bar-S（自動根據子群組大小選擇）+ **EWMA / CUSUM**（指數加權移動平均 / 累積和）
- **異常偵測**: **離群值偵測**（IQR + Z-score 雙閾值，繪製藍色圓點）+ **改變點偵測**（CUSUM statistic，繪製綠色三角形）
- **規格線**: LSL/USL 參考線於位置圖（Individuals 直畫、X-bar 標記 (ref)）；離散圖 MR/R/S 不加
- **Western Electric 7 規則**: 違規偵測與表格化顯示
- **能力指數**: Cp / Cpk / Pp / Ppk
- **批量比較**: 多欄位同時分析 + 比較表格 + 各欄獨立控制圖
- **優化建議**: 基於 Cpk/規則違反自動產生 shift/trend/能力不足警示
- **IPC handlers**: `spc/analyze` + `spc/capability` + `spc/batch_analyze`

### Phase 9 — 蒙地卡羅異常風險模擬 ✅

- **抽樣引擎**: Normal / Gamma / Lognormal / Empirical（含直方圖抽樣）
- **異常整合**: 指定異常 + 自然發生風險模式
- **聯合機率**: 支援獨立假設 + Copula 相關矩陣模式
- **NG 機率**: 輸出分布 + 百分位數（P1/P5/P50/P95/P99）
- **預測能力指數**: 模擬結果呈現 Pp / Ppk（simulation-based，引擎 compute_capability 同源）
- **風險排名**: 異常貢獻度排序 + 交互作用熱圖

### Phase 10 — 互動預測 (What-if) ✅

- **Live 滑桿**: 拖曳即時更新預測
- **數值輸入**: 精準輸入 + 範圍限制（基於訓練數據）
- **規格判定**: In Spec / Below LSL / Above USL（含距離邊界顯示）
- **還原預設**: 一鍵恢復至資料平均值

### Phase 11 — 驗證實驗 (Validation Lab) ✅

- **完整驗證**: 跨模型 CV + 殘差分析 + 交互作用 + 實驗建議
- **實驗記錄**: 記錄 planned/actual inputs、predicted/actual output、result（pass/fail）
- **實驗歷史**: 合格率、平均絕對誤差統計 + 排序表格
- **可信度評分**: 六維度（資料覆蓋 / 預測準確 / 統計穩定 / 工程合理 / 驗證程度 / 外插風險）→ 綜合分數 + 等級（production_ready / engineering_reference / exploratory / needs_more_data / not_recommended）

### Phase 11b — 短期補強 ✅

- **Logistic Regression**: 二元 NG 預測（accuracy / recall / AUC）
- **Weibull 迴歸**: 可靠度 / 壽命資料分析（MLE shape k + log(λ)=Xβ）
- **時間序列特徵**: lag / rolling mean / rolling std / drift / 連續超標次數
- **審核工作流**: submit / approve / reject（含 Reviewer 角色）
- **What-if 情境保存**: 儲存與載入預測情境（可比較多個參數設定）

### Phase 11c~11i — 中期擴充 ✅

- **Copula 聯合機率**: 高斯 Copula（相關矩陣）/ 獨立 / 直接指定三種模式
- **GRR 量測系統分析**: AIEM 方法（EV / AV / GRR / PV / TV / %GRR + 判定）
- **雲端去識別化上傳**: SHA-256 雜湊遮蔽 + 高斯噪音 + 強制確認 Modal
- **專案檔案系統**: `project_manifest.json` + 9 個目錄結構 + 製程群組/節點管理
- **製程流程圖**: SVG 可交互編輯器 + 拓撲排序佈局 + 環狀檢測
- **製程流程 × 下游分析整合**: 跨節點關聯鍵（`association_keys`）+ 節點「跳到分析」按鈕（SPC / Monte-Carlo / Exploration）+ 依節點行篩選（`filter_column`/`filter_value`，SPC / MC / 分布 / 序列）

### 多語言 ✅

- **English**（預設）
- **繁體中文**（zh-TW）
- **Español (México)**（es-MX）— 1345 keys 完整翻譯（三語 key set 完全一致，並由 `scripts/check-i18n-parity.mjs` 在 CI 中驗證）

### 模型類型（8 種）

| 類型 | 說明 | 適用場景 |
|---|---|---|
| `doe_linear` | 線性 DOE | 主要效應分析 |
| `doe_quadratic` | 二次 DOE | 曲率 + 交互作用 |
| `random_forest` | 隨機森林回歸 | 非線性殘差補償 + 自動特徵選取 |
| `xgboost` | XGBoost 回歸 | 高維非線性預測 |
| `lightgbm` | LightGBM 回歸 | 高效大資料訓練 |
| `residual_hybrid` | 混合模型 | Y = f_DOE(X) + r_RF(X) |
| `logistic_regression` | Logistic 迴歸 | 二元 NG/OK 預測 |
| `weibull_regression` | Weibull 迴歸 | 可靠度 / 壽命分析 |

## 測試統計

| 項目 | 數值 |
|------|------|
| **引擎測試** | 645 passed / 12 skipped |
| **覆蓋率** | 78%（`pytest --cov`，僅涵蓋 Python 引擎） |
| **Commits** | 881 |
| **應用程式碼行數** | ~32,400 行（`engine/src` + `src` + `src-tauri/src`） |
| **測試程式碼行數** | ~9,800 行（`engine/tests`） |
| **多語言** | 3（en / zh-TW / es-MX，1345 keys 對齊） |

量測方式（可重跑驗證）：

```bash
git rev-list --count HEAD
find engine/src src src-tauri/src -type f \( -name '*.py' -o -name '*.ts' -o -name '*.tsx' -o -name '*.rs' \) | xargs wc -l | tail -1
cd engine && .venv/bin/pytest -q          # addopts 已含 --cov
```

`validate` workflow 每次 push 與 PR 都會執行前端的 typecheck、production build、i18n key 對齊與出貨相依稽核，以及引擎的 pytest 與 Rust 的 `cargo test`。

## 設計原則

- 不綁定特定產業（非僅車載 ECU）
- 原始資料預設不送往雲端
- 傳統 DOE 永遠保留為回退方案
- 所有自動建議可解釋、可追溯、可人工覆核
- AI 助手支援三語言（en / zh-TW / es-MX）
- 資料上雲前必須遮罩 + 使用者確認 + 審核紀錄
- 製程節點與流程可配置（不寫死產業名稱）

## 資料模型範圍

v0.6.0 以 CSV／Excel 表格列為主要輸入，支援單層量測與可選的產品、Lot、機台、站點、製程步驟及子群組 metadata；保留既有單層 CSV 相容性。

## 技術決策記錄

| 決策 | 選擇 |
|------|------|
| 桌面框架 | Tauri 2.0 |
| Python 版本 | 3.12 (`uv` 管理 `.venv`) |
| 本地 AI | Ollama (local) + OpenAI/Azure/Custom |
| i18n 語言 | en + zh-TW + es-MX |
| 資料粒度 | 目前以單層表格資料列／單次量測為主；部分支援時間序列與子群組分析 |
| 模型與模擬紀錄 | `registry/version_chain.jsonl`（`models/`、`simulations/` 為預留目錄） |
| 雲端策略 | 預設不上雲；上雲前遮罩 + 確認 |
| 製程定義 | JSON 配置（不硬編產業名稱） |
| 流程圖 | SVG 可交互編輯器 |

## 快速測試資料

專案提供預存測試資料：

測試資料說明：[繁體中文](data/test_dataset_README.md) · [English](data/test_dataset_README_En.md)

```
data/test_dataset.csv
```

包含 82 筆資料，4 個輸入變數 (temperature, pressure, time, humidity) + 1 個輸出變數 (yield)，適合測試完整分析流程。

## 版本紀錄

### v0.10.4（2026-09-30）

**新功能：設定頁的「測試 CUDA 可用性」**

- 在 `lightgbm_device` 下拉旁新增測試按鈕，回答「**這台機器真的能用 CUDA 嗎**」—— 這是下拉旁的說明文字只能概括陳述、無法針對實際機器回答的問題。
- **逐項顯示結果，不給單一燈號**：驅動程式（`nvidia-smi`／GPU 名稱）、**此版本內含的 CUDA runtime**、torch、booster GPU 支援 —— 每項附上**失敗原因**。因為「CUDA 不可用」有數種成因且處置各異（沒驅動／裝到 CPU 版／torch 未安裝／booster 未編 GPU），單一紅燈無法指出是哪一種。
- **runtime 那列同時是版本檢查**：CUDA 版才帶 `nvidia-*` 函式庫，所以**裝錯版本的使用者能直接看出原因**。
- **`lightgbm_gpu` 顯示為 `?` 而非 ✗**：引擎刻意回報「未知＋原因」（LightGBM 不提供查詢方式，只有實際 trial fit 能確認）。顯示 ✗ 會**誇大探測所知的範圍**；TS 型別也因此為 `boolean | null`，避免 UI 捏造引擎拒絕給出的結論。
- **僅為探測**：不執行任何 GPU 運算，因此通過只代表各項元件齊備，**不代表配適一定能成功** —— 此限制同時寫在 API 與 UI 說明中。
- 引擎端為 `system/device_probe`，授權分類 **VIEWER**（依 `auth/policy.py` 自訂規則：不持久化狀態、無網路輸出，`nvidia-smi` 為本機子行程）。新增 4 個引擎測試，其中一個以 monkeypatch 證明它真的讀取環境而非回傳固定值。
- 驗證：`tsc`／`build`／`check:i18n`／`check:guide` 皆通過（取真實退出碼），引擎套件 667 passed。**桌面上的按鈕行為待使用者實機確認。**

### v0.10.3（2026-09-30）

**報告卡片改為真正「開啟」；Linux 只發 deb／rpm；新增 CUDA 建置入口**

- **報告卡片開啟**（`34da266`）：PDF／Excel 卡片原本會跳存檔對話框，與按鈕上的「開啟」不符。改由新的 Rust `open_report` 指令處理 —— 寫入 app cache 後交棒給系統預設檢視器（`xdg-open`／`open`／`explorer`）。**未採用 opener plugin**：它會拉進 `zbus`、把 `wry` 從 0.55.1 升到 0.57.0、並需要新 capability —— 為了開啟一個檔案去改整個視窗依賴的 webview 層並不划算。寫檔刻意放在 Rust 而非 fs plugin，因為 fs capability 限於「使用者在對話框選的路徑」，cache 路徑不在其中。
- **Linux 產物格式**（`09def32`、`e1bcbd4`）：AppImage 步驟以 linuxdeploy 掃描 PyInstaller 引擎時，無法以 soname 解析 scipy 隨附的 `libquadmath-828275a7.so.0.0.0`（同一 soname 有多份不同雜湊檔名）而中止。Linux 改為只產生 deb 與 rpm，目標固定在 `src-tauri/tauri.linux.conf.json`（Tauri v2 自動合併的平台設定檔），**因此建置指令不需任何平台參數，macOS／Windows 不受影響**。
- **CUDA 建置入口**（`e1bcbd4`）：新增 `npm run build:cuda`（CPU 版維持 `npm run build:app`）。`--with-cuda` 屬於引擎腳本而非 Tauri 旗標，兩者不可混用 —— 詳見 `docs/deployment.md`。
- 文件補充：Linux 建置依賴（含 `libappindicator3-dev` 與 `libayatana-appindicator3-dev` 的互斥差異、`libdbus-1-dev` 的必要性）、AppImage 失敗的真因與**「Tauri 會吞掉 linuxdeploy 訊息，需 `--verbose`」**、以及 `libfuse2` 是常見誤判。
- 驗證：使用者實機確認 PDF／Excel 可直接開啟、`npm run build:app` 於 Linux 完成並只產出 deb／rpm；`cargo check`、`tsc`、`build`、`check:guide`、`check:i18n` 皆通過。

### v0.10.2（2026-09-30）

**修正：Excel 報告匯出失敗（`Cannot convert {} to Excel`）與 HTML／Excel 的呈現不一致**

- **症狀**：報告產生失敗，`engine error: Cannot convert {} to Excel`。
- **根因**：製程定義契約的 `spec` 除 `limits` 外還帶 **`input_ranges`**（欄位 → [下限, 上限]）。規格表把 `spec` 中**除了 `limits` 以外的每個鍵直接寫入儲存格**，而 openpyxl 只接受純量，因此空的 `input_ranges` 以 `{}` 抵達寫入器，讓整份匯出中止。**先重現**：測試在修正前以使用者所見的逐字訊息失敗。
- **修法**：新增 `cell_value()`（轉純量）與 `flatten_rows()`（**展開**巢狀結構，保留內容而非丟棄），`input_ranges` 因此成為 `input_ranges.t = 170.0 – 190.0`。同一防護套用至所有直接寫入原始值的區塊（gate 摘要、模型指標與係數、外推摘要、來源標籤）。
- **HTML 一致性**：HTML 原本不崩，但會把同一欄位 `str()` 成 `{'t': [170.0, 190.0]}`。轉換邏輯改置於 **`base.py`（兩者共用）**，避免兩份實作日後漂移；HTML 的規格列改用同一展開方式。
- 驗證：修改前 RED、修改後 GREEN；新增渲染器一致性測試（斷言兩者輸出相同標籤與值，且 HTML 不得退回 repr）；**完整 engine 套件 663 passed, 12 skipped**。
- 註：PDF 在本專案由 HTML 轉出，隨 HTML 一併修正，但未單獨驗證其輸出。

### v0.10.1（2026-09-30）

**修正：建置腳本會回報「引擎啟動即死」，並在 EPIPE 下存活**

- `build-engine.mjs` 的 smoke test **沒有 `child.on('exit')` 處理器**，因此凍結引擎在回答 `engine/ping` 前就結束時，腳本會**等滿 120 秒**再報「did not answer within 120s」加一段**空白的 stderr** —— 而這正是 macOS Gatekeeper 終止、缺 dylib、架構不符的表現。**唯一能區分「死了」與「慢」的資訊（結束碼）被丟棄。**
- 補上：`exit` 處理器回報 **code 與 signal**（實測提早死亡 **5 毫秒**就報出，不再等 120 秒）；`SMOKE_TIMEOUT_MS` 可調（冷啟動的 Gatekeeper 評估可能超過硬編的 120 秒）；逾時訊息明確說明「**stderr 為空**」。
- **另一個靠實際執行測試才發現的缺陷**：子行程已死時 `child.stdin.write()` 會觸發**未處理的 EPIPE 事件，讓整個 Node 行程以堆疊崩潰**，再次吞掉結束碼。測試第一次執行就炸了 —— 不是讀程式碼發現的。
- 新增 `scripts/test-smoke-timeout.mjs`，用三個 stub 驅動**真正的 `smokeTest()`**：立即結束（報 code 3）、正常回應、靜默掛住。`smokeTest` 改為匯出，`main()` 只在直接執行時啟動，避免 import 觸發整包 PyInstaller 建置。
- **這不修復建置失敗本身，只讓原因可回報。** 註：使用者實測 0.10.1 建置正常、0.10.0 失敗，而兩者引擎二進位僅差版本字串 —— 該次失敗判定為**環境性／暫時性**，機制未證實（已查證建置腳本每次全清 dist/work 快取，排除陳舊快取的可能）。

### v0.10.0（2026-09-30）

**進版：將 0.9.11–0.9.32 的說明工作標記為 minor release**

- 涵蓋：13 頁列舉式說明改寫、en／es-MX 全形標點污染的修正與守衛、被遮蔽 const 的移除（含更正 v0.9.28 的不實記錄）、以及兩件「內容存在但永不顯示」的修正（GRR 的 crossed-only 限制屬資料層、dataImport 的 interpretation 屬渲染層）。
- 版本同步於 `VERSION`、`package.json`、`Cargo.toml`、`Cargo.lock`、`tauri.conf.json`、engine `__init__.py` 共六處，提交前已逐一驗證。
- 註：本條目為補記（進版當時未同步寫入 README）。

### v0.9.32（2026-09-30）

**修正：dataImport 的 `interpretation` 不再被元件覆蓋**

- `GuideModal` 原本對 dataImport 用**三段硬編碼字串取代 `section.interpretation`**，因此 **0.9.18 為該頁三語寫的 interpretation 從未顯示過**。硬編碼內容住在元件內、不在 `guideContent.ts`，這也是**守衛看不到它**、且兩者會各自漂移的原因。
- **先合併、再刪除**：硬編碼那段提到「各欄位的 n、最小值、最大值、平均值、標準差、最佳分布與問題數」，而 guide 版本未提逐欄統計 —— 直接刪除會無聲遺失該指示。故先併入 guide（zh +39／en +128／es-MX +136 字元），再移除硬編碼分支。
- 驗證：元件內已無硬編碼字串且改用 `section.interpretation`（斷言）；**逐欄統計與編碼指引在三語皆存在**（`len` zh 265／en 717／es-MX 746）；`tsc`／`build`／`check:guide`／`check:i18n` 全過。
- 此為「內容存在但永遠不被渲染」問題的**渲染層**案例，與 0.9.26 的 GRR（資料層覆蓋）同類。

### v0.9.31（2026-09-30）

**守衛補強：涵蓋被渲染卻未受保護的 `contract` 欄位**

- `GuideModal` 除了 8 個標準欄位外**也會渲染 `section.contract`**，但該欄位先前**既不在空值檢查、也不在字元完整性檢查內** —— 空的或被全形字元污染的區塊可以無聲上線。目前僅 dataImport 使用（三語分別 128／315／324 字元）。現在只要頁面提供該欄位，兩項檢查都會涵蓋。
- **RED 驗證，並精確區分分支**：注入後 `check:guide` 以 `exit=1` 指名 `dataImport [en]`／`[es-MX]`，還原後恢復綠燈且 `git diff` 為空。**已證明「檢查觸及 contract」；未證明「空值斷言」（該次執行的是字元完整性分支）** —— 此區別已寫入 commit message。
- **附帶的靜態整合驗證**：視窗確實渲染全部 8 個標準欄位 + `contract`；15 個頁面在三語皆有 `nav.*` 標籤。**因此 0.9.11–0.9.30 的說明修改在 UI 中是可達的**，不是寫進沒人顯示的欄位。
- 過程記錄：四次注入失敗全因**未先讀原始碼就猜形狀**（`dataImportContract` 是 `Array<[string, string, string]>`，名稱後接**冒號**型別標註，故 `'const NAME '` 的搜尋靜默不命中，我先後誤設為物件與 backtick 字串）。第一次失敗就該直接 grep 那一行。

### v0.9.30（2026-09-30）

**使用者說明：distribution 補上 k／n 定義與樣本量下限**

- `formula` 用了 k 與 n 卻**都沒定義**，`limits` 也沒有樣本量下限 —— **用幾個點配適的結果，與用幾千點配適的結果看起來一樣權威**。
- 補上（三語）：k 為配適參數個數、n 為樣本數；**AIC／BIC 只衡量相對配適，並不檢定該分布是否正確**；**樣本量小時 AIC／BIC 排序不穩定，最佳分布可能只是偶然，不宜據以設定模擬分布**。
- 來源為 `distributionExtra`（0.9.29 已移除被遮蔽的 `distributionNotes`，extra 現為唯一來源）。腳本**讀取實際字串作為搜尋鍵**而非憑記憶重建，且每處需恰好匹配一次才寫入。
- 驗證：k／n 與樣本量下限在三語皆出現；`tsc`／`build`／`check:guide`／`check:i18n` 全過。**此為覆蓋鏈核對後的最後一個內容缺口。**

### v0.9.29（2026-09-30）

**重構：實際刪除五個被遮蔽的 const，並更正 v0.9.28 的不實記錄**

- **v0.9.28 的 commit message 聲稱完成了這項刪除並附有雜湊證明 —— 兩者都沒發生。** 該 helper 因這些 const 採 **ASI 結尾（無分號）** 而中止，掃描在等一個不存在的 `;`；而我自己的命令鏈中 `;` 與 `&&` 混用，使失敗沒有阻止後續步驟，commit 就這樣帶著不存在的工作推送出去。v0.9.28 實際只含版號與雜湊工具。
- 本版**真正執行刪除**：`processNotes`、`modelCenterTimeSeriesNotes`、`approvalSpcNotes`（其頁面由 `*Detail` 支撐，三語皆 7/7 欄位）、`grrNotes`、`distributionNotes`（其欄位被 `explorationGrrExtra`／`distributionExtra` 完全涵蓋，逐欄位確認）。
- 保留 `explorationGrrExtra`、`distributionExtra`、`trendNotes`、`timeseriesNotes`、`predictionProfilerNotes` —— 它們仍是各自欄位的唯一來源。**先前「9 個死代碼」的說法是錯的：舊不等於死。**
- **證明而非聲稱**：528 格（頁 × 語系 × 欄位）雜湊在刪除前後**逐格完全相同**。commit 前另加斷言：五個名稱確已消失、五個活躍 const 仍在。失敗兩次皆因寫入置於驗證之後，**沒有任何半套修改落地**。

### v0.9.28（2026-09-29）

**雜湊工具（附帶更正說明）**

- 本版實際只包含版號升版與 `scripts/hash-guide-output.mjs`（逐格雜湊工具，用於證明重構不影響輸出）。
- **其 commit message 描述的五個 const 刪除與雜湊證明並未發生** —— 詳見 v0.9.29 的更正。保留此條目是為了不讓 history 出現無法解釋的落差。

### v0.9.27（2026-09-29）

**使用者說明：補上 trend 與 timeseries 沒說出來的失效前提**

- 這兩頁都默默假設了兩個前題：
  - **時間排序必須正確** —— trend 的公式是「末值 − 首值」，timeseries 的 lag 與差分是對「前一期」計算；**資料列或時間戳未排序，這些讀數全部失去意義**，連續同向點與漂移的判讀也一併失真。
  - **循環論證的管制界限** —— 若 UCL／LCL 是用**同一批資料自動算出的 3σ**，則「界線外點數為 0」有一部分是循環論證：**那些點本身就參與了界限的計算**。判定穩定性應使用取自**穩定基準期**的界限。
- timeseries 另補上**資料洩漏**：把輸出自身的滯後值當作預測特徵，模型在訓練資料上表現良好卻無法外推（原先僅 `steps` 提及，`limits` 未說）。
- 內容量（實測）：trend zh 156／en 467／es-MX 494 字元；timeseries zh 143／en 478／es-MX 515；**排序相關用語在三語皆出現**。
- en／es 維持純 ASCII 標點，**全形字元守衛保持綠燈**；`tsc`／`build`／`check:guide`／`check:i18n` 全過。一次性輔助腳本用完即刪。

### v0.9.26（2026-09-29）

**使用者說明：補上 GRR 的適用範圍限制**

- grr 的 `limits` 原先只談樣本量、零件範圍與代表性，但**沒提那個會讓整個結果失效的前提**：引擎實作的是 **AIEM（全距法），只適用於 crossed（零件與操作者交叉）研究**。
- 若資料為 **nested**（零件嵌套於機台／批次／產線內），AIEM 會**高估零件變異、使 %GRR 失真**。三語皆已補上此限制與處置建議（改用嵌套設計的變異數分解）。
- 改的是 **`explorationGrrExtra`** 而非 `grrNotes` —— 說明由覆蓋鏈組成（`grrNotes` → `explorationGrrExtra` → `grrSteps`），改 notes 會通過編譯、畫面不變、等於沒改。
- 驗證：crossed-only 與 nested 用語在三語皆出現；`tsc`／`build`／`check:guide`／`check:i18n` 全過。

### v0.9.25（2026-09-29）

**使用者說明：GRR 補上方法與最低要求、distribution 補上候選清單**

- **grr**：加入引擎實況 —— 方法為 **AIEM（Average and Range／全距法）**、**crossed** 研究；**至少 3 次量測**、**建議至少 10 個零件**才穩健；選用 **X-bar 管制圖**檢視量測穩定度。
- **重要更正**：`data/grr.py` **沒有 ANOVA** 路徑。我先前「ANOVA vs 全距法」的說法是**錯的**，未寫入說明。
- **distribution**：列出 **7 種候選分布** —— normal、lognormal、weibull、gamma、beta、triangular、uniform。
- 改的是 **`grrSteps`／`distributionSteps`**，因為 `steps` 是該欄位的最高優先序來源。
- 內容量（實測）：`AIEM` 與 `至少 3 次量測` 在三語皆出現；7 種分布在三語皆 7/7。
- 驗證：`tsc`／`build`／`check:guide`／`check:i18n` 全過（含全形字元守衛，確認新增文字未污染 en／es-MX）。

### v0.9.23（2026-09-29）

**修正：英文與西班牙文語系中的全形中文標點**

- 11 個說明欄位在 en 與 es-MX 字串內夾帶中日韓全形標點，英文或西語使用者會看到 `%GRR=GRR variation／total variation×100%；%Part=...` 這種公式，以及用中文句號結尾的西語句子。受影響欄位為 distribution、timeseries、grr、prediction，以及資料匯入的資料契約分隔符。
- **以字串常值為單位修正，而非尋找取代**：三語內容在檔案中並排（常在同一行），而全形標點在 zh-TW 文字中是正確用法。規則為：不含中日韓文字的常值即為 en／es 常值，其中的全形標點即為缺陷；zh-TW 常值一律跳過 —— **18 個欄位、640 處全形標點原樣保留**。
- 修復腳本第一次執行時**中止而未寫入**，因為原規則只涵蓋 `；` 與 `／`，而文字中另有全形句號 `。` 與全形直線 `｜`；由於寫入置於守衛之後，沒有任何半套修改落地。補齊對應表後第二次寫入成功。
- 驗證：en／es-MX 殘留全形標點欄位為 **0**；`tsc`／`build`／`check:guide`／`check:i18n` 全過。
- `scripts/fix-cjk-punct.mjs` 保留作為修復記錄；把同類檢查接進 `check:i18n` 為後續工作（目前守衛只比對 key 對齊，抓不到字元污染）。

### v0.9.22（2026-09-29）

**使用者說明：資料資產與核准頁面改為列舉功能**

- 這兩頁都沒有列出可用的操作；核准頁甚至未列出審核會經過哪些狀態，因此無法得知這頁能做什麼、某個狀態代表什麼。
- **資料資產**（三語）：清單欄位（標籤／列數／欄數／檔案大小）與 **8 項資料操作**（import／datasets／detect_fields／quality／readiness／distribution／series／grr）；並寫明**此頁只呈現狀態、不修改資料**，修正資料需重新匯入而產生新的資料集。
- **核准**（三語）：**5 項操作**（submit／approve／reject／status／records）與 **4 種狀態**（draft／pending／approved／rejected）及各自含義；限制寫明**核准不會因之後的變更而自動失效**、**核准不是技術驗證**、未建立獨立帳號時紀錄歸屬意義有限。
- 內容量（實測）：資料資產 en 2,248 字元、zh-TW 729、es-MX 2,653（8/8 操作在三語出現）；核准 en 2,241、zh-TW 799、es-MX 2,323（9/9 操作與狀態在三語出現）。
- 註：原先只把細節放在 commit message，此條目為補記。

### v0.9.21（2026-09-29）

**使用者說明：製程流程頁面改為列舉功能**

- 製程流程原本是剩餘頁面中說明較完整的一頁，但仍未列出可加入的**節點種類**、可能的**節點狀態**，以及畫布實際提供的**操作**。
- 改寫製程流程（三語）：**六種節點**（資料／分析／模型／模擬／驗證／報告）；**三種狀態**（success／warning／blocked）與各自含義 —— **blocked 表示前置條件未滿足**；操作（加入節點、連線、中斷連線、刪除、自動排版）；以及上游版本與假設會傳入下游節點的傳遞規則。
- 限制寫明：流程圖呈現**工作關係，不是正確性也不是因果關係**；上游版本變更會使下游結果過期；**循環或未定義輸入會使流程無法有意義地執行**。
- 內容量（實測）：en 2,483 字元、zh-TW 821、es-MX 2,749。**三種狀態在三語皆出現**（已驗證）。
- 註：原先只把細節放在 commit message，此條目為補記。

### v0.9.20（2026-09-29）

**使用者說明：專案頁面改為列舉功能**

- 先前 project 說明未列出任何一項專案操作，也未說明專案作為容器的用途，因此無法回答兩個真正要緊的問題：一項分析該放進哪個容器，以及交接時必須包含什麼。
- 改寫專案（三語）：**九項操作**（create／open／scan／datasets／manifest／dirs／settings／save_session／save_ui_state）；把資料集、製程定義、模型、實驗與報告收束進單一可追溯容器的理由；工作階段與介面狀態**自動儲存**；以及交接與備份規則。
- 限制寫明：**刪除或移動專案資料夾會使其中所有分析失效**；專案是本機狀態、**不是多人同時協作的機制**（同時開啟可能互相覆寫）；未儲存的變更不會出現在資訊清單。
- 內容量（實測）：en 2,494 字元、zh-TW 799、es-MX 2,627。**九項操作在三語皆出現**（已驗證）。
- 註：原先只把細節放在 commit message，此條目為補記。

### v0.9.19（2026-09-29）

**使用者說明：製程定義頁面改為列舉功能**

- 先前 processDefine 說明未列出任何一種界線、未說明單位規則與操作範圍，因此**沒有傳達這頁存在的理由**：規格界限是要求、管制界限描述穩定性、操作範圍界定可安全外推的區間，混用三者正是這頁要防的錯誤。
- 改寫製程定義（三語）：輸出欄位與單位；LSL／USL／目標值的順序與單位驗證；自動建議規則 **LSL=μ−3s、USL=μ+3s、目標值=μ** 及其「統計參考值而非規格」的性質；**Cpk 為負表示平均值已在規格之外**；逐項輸入的單位與操作範圍；管制界限**手動 LCL／UCL vs 自動 3σ**；設定後品質複查；異常情境；分析資料包；8 步流程。
- 限制寫明：**此頁不驗證假設是否正確，只記錄與傳遞它**；設定值不會被資料自動修正。
- 內容量（實測）：en 3,529 字元、zh-TW 1,013、es-MX 3,833。**LSL／LCL／Cpk 在三語皆出現**（已驗證）。
- 註：原先只把細節放在 commit message，此條目為補記。

### v0.9.18（2026-09-29）

**使用者說明：資料匯入頁面改為列舉功能**

- 先前 dataImport 說明只描述步驟，未列出**任何一種編碼**、欄位角色、品質檢查項或範本欄位 —— 而這頁最常出錯的正是兩件事：編碼誤判造成亂碼，以及角色設錯導致後續分析全面失真。
- 改寫資料匯入（三語）：**6 種編碼**（utf-8／big5／cp950／gb18030／shift_jis／latin-1）與分隔符偵測；**10 種欄位角色**與數值／類別型態、**每欄 AI 信心度**；品質檢查項（缺失值／重複／常數欄位／極端離群值／OK-NG 失衡）；**建模前健檢閘門**與分布配適（AIC／BIC／KS 排序）；工程多層級範本的 7 個追溯欄位；8 步流程。
- 限制寫明：編碼誤判損毀欄位內容、角色或單位設錯會使後續分析失真，且**這類錯誤不會在上游被擋下**，而是以錯誤的圖表與指標呈現。
- 內容量（實測）：en 3,644 字元、zh-TW 1,255、es-MX 3,963。**6 種編碼在三語皆完整出現**（已驗證）。
- 註：原先只把細節放在 commit message，此條目為補記。

### v0.9.17（2026-09-29）

**使用者說明：報告頁面改為列舉功能**

- 先前 reports 說明未區分**三種格式**、未說明 PDF 由 HTML 轉出因而內容一致、未說明 Excel 的每個工作表對應哪個區塊，也未提 draft／approved 狀態與追溯附錄。
- 改寫報告（三語）：HTML（快速預覽）／PDF（歸檔與傳閱，含 WeasyPrint 系統函式庫需求）／Excel（**每個工作表對應一區塊**：SPC 能力與違規、模型比較含 AUC／accuracy／shape_k／AIC、最終模型係數、可信度六維度）；報告為**分析鏈輸出而非重新計算**（缺區塊＝該步驟未執行）；draft／approved 與核准者記錄；Appendix A 版本鏈／B 來源標籤／C 外推警告；以及 10 步流程。
- 內容量（實測）：en 3,907 字元、zh-TW 1,277、es-MX 4,212。**HTML／PDF／Excel 三名稱在三語皆出現**（已驗證；es-MX 檢查回報 `appendix:no` 為偽陰性，西語作「Apéndice」）。
- 註：本版與 v0.9.13 相同，原先只把細節放在 commit message，此條目為補記。

### v0.9.16（2026-09-29）

**使用者說明：設定頁面改為列舉功能**

- 先前 settings 說明未列出**四個角色**與權限階層、未列出**四個 AI 供應商**、未說明 LightGBM 裝置選項、未解釋 noise_std 與 noise_ratio 的差別，也未提「去識別化預覽的警告與假名金鑰」該如何檢核。
- 改寫設定（三語）：**角色階層**（viewer ＜ engineer ＜ reviewer ＜ admin）與各自可做的事，並說明**權限由引擎強制、非僅介面隱藏**；未登入時為本機擁有者（預設 admin）、登入受限帳號後權限真實生效；**四個供應商**（ollama／openai／azure／custom）；LightGBM 裝置（auto／cpu／gpu）；noise_std（絕對 σ）與 noise_ratio（該欄 σ 的比例）；金鑰以遮罩顯示且儲存不會以遮罩值覆寫；稽核日誌涵蓋範圍；以及 10 步流程。
- 限制寫明：**金鑰存於本機**，共用機器不宜設定雲端供應商；稽核為本機紀錄而非不可竄改存證；去識別化降低風險但不保證匿名。
- 內容量（實測）：en 3,794 字元、zh-TW 1,240、es-MX 4,248。**四個供應商與四個角色在三語皆完整出現**（已驗證）。

### v0.9.15（2026-09-29）

**使用者說明：驗證頁面改為列舉功能**

- 先前 validation 說明未列出**五個可信度等級**（production_ready／engineering_reference／exploratory／needs_more_data／not_recommended）、未說明六個維度的名稱、未提 Durbin-Watson 的判讀方式，也沒有把「實驗建議 → 實驗記錄 → 可信度累積」的流程串起來。
- 改寫驗證（三語）：五種建議原因碼（interaction／transformation／range_expansion／new_factor／replicate）與對應處置；k-fold 各折的**離散程度**判讀（平均好但折間差異大＝對切分敏感）；殘差結構（彎曲＝結構不足、擴散＝異方差）；Durbin-Watson 判讀；**六維度名稱**與等級對應用途；planned／actual 與 predicted／actual 的實驗記錄流程；以及 11 步流程。
- 明確寫入**時間序列不可隨機切分**（會高估表現）。
- 內容量（實測）：en 4,142 字元、zh-TW 1,328、es-MX 4,423。

### v0.9.14（2026-09-29）

**使用者說明：Copula 頁面改為列舉功能**

- 先前 copula 說明雖已提及 Sklar 定理與三種模式，但沒有說明**各模式的差異與適用時機**、相關矩陣的半正定要求、尾端相依對 NG 風險的影響，也沒有抽樣前後對照的檢核步驟。
- 改寫 Copula（三語）：三種模式（**gaussian_copula**／**independent**／**direct**）個別說明與適用時機；Sklar 分解與 Pearson／Spearman／Kendall 的角色（前者對非線性單調關係會低估）；高斯 Copula 的 Cholesky → norm.cdf → 反函數流程；相關矩陣須對稱、對角為 1、半正定；**尾端相依對 NG 風險的影響大於整體相關性**；抽樣前後的邊際分布／相關矩陣／尾端對照；以及 10 步流程。
- 內容量（實測）：en 3,585 字元、zh-TW 1,183、es-MX 3,798。三種模式名稱與相關性方法在三語皆以各語言正確形式出現（「高斯」／「獨立」／「直接指定」／「半正定」；es-MX 為「cópula gaussiana／independiente／semidefinida」）。

### v0.9.13（2026-09-29）

**使用者說明：蒙地卡羅頁面改為列舉功能（延續 v0.9.11／v0.9.12）**

- 先前 monteCarlo 說明只描述「模擬」的概念，**沒有列出任何一種抽樣方式**，也未提聯合機率模式、NG 輸出、百分位、模擬基礎能力指數與異常貢獻排名。
- 改寫蒙地卡羅（三語）：**7 種抽樣方式 + auto**（normal／gamma／lognormal／uniform／triangular／empirical／bootstrap／auto），並註明未知名稱會退回自歷史值重抽；NG 機率定義；輸出百分位 P1／P5／P50／P95／P99；模擬基礎 Pp／Ppk（與引擎 `compute_capability` 同源）；獨立抽樣與 Copula 的取捨（**獨立抽樣會低估聯合風險**）；異常貢獻排名；以及 11 步流程。
- 內容量：en 4,139 字元、zh-TW 1,367、es-MX 4,300。**8/8 抽樣方式名稱在三語皆出現**（已驗證）。
- 註：本版原先只把細節放在 commit message（為避免預算中斷導致未提交變更），此條目為補記。

### v0.9.12（2026-09-29）

**使用者說明：SPC 頁面改為列舉功能（延續 v0.9.11）**

- 先前 spc 說明只提到 EWMA／CUSUM 與 I-MR，**未區分 X-bar/R 與 X-bar/S**，也沒提離群值／改變點偵測、批量比較、優化建議、手設界限來源與模型核准的穩定性 Gate。
- 改寫 SPC（三語）：列出 **5 種圖表**（I-MR／X-bar/R／X-bar/S／EWMA／CUSUM，含選擇依據）、σ_within 與 σ_overall 的估計來源、**正確的統計常數**（X-bar/S 用 A3=3/(c4√n) 與 c4 基礎的 B3/B4；X-bar/R 用 A2=3/(d2√n)；I-MR 用 MR̄/d2）、WE 7 規則套用於所繪製統計量（X-bar 圖區間寬度為 σ/√n）、離群值（IQR＋Z 雙閾值）與改變點（CUSUM）的圖示、能力指數的搭配判讀、批量比較的前置一致條件，以及 11 步流程。
- 內容量：en 3,849 字元、zh-TW 1,430、es-MX 4,182。**5 種圖表在三語皆以各語言正確形式列出**（es-MX 為「X-barra/R」等，已逐項確認）。
- 統計常數的描述與 v0.9.5 的修正一致，說明文件不再與程式碼脫節。

### v0.9.11（2026-09-29）

**使用者說明：從「只講原則」改為列舉功能（modelCenter 先行）**

- 先前說明雖然每頁都有內容，但**深度不足**：只解釋目的與原則，不列舉頁面實際提供的選項。實測 modelCenter 的 `principle`／`formula`／`steps` 幾乎全在講時間序列模式，對標準建模只有一句「preserves the existing DOE, AI, and hybrid flows」——**8 種模型類型一個都沒提**。
- 本版改寫 **modelCenter**（三語）：列出 8 種模型類型（doe_linear／doe_quadratic／random_forest／xgboost／lightgbm／residual_hybrid／logistic_regression／weibull_regression，各含目標型態與適用場景）、6 種 DOE 設計範本、SHAP／敏感度／交叉驗證／外推／Prediction Profiler、模型治理與核准流程，以及 12 步操作流程。
- 內容量：en 約 1,695 → **4,752 字元（2.8×）**；zh-TW 1,828、es-MX 5,287。**8/8 模型名稱在三語皆出現**（已驗證）。
- **實作注意**：內容必須放在 return 的**最後**一個 spread。`...modelCenterTimeSeriesNotes` 排在 `...topic` 之後，若把內容寫進 `topics.modelCenter` 會被靜默覆蓋 —— 這是實測確認的，不是推測。
- 限制的寫法照使用者核可的方向偏直言（例如「自動特徵選取可能丟掉工程上重要但本樣本微弱的因子」）。
- 其餘頁面依同一標準待辦，順序：spc → monteCarlo／copula／validation → settings／reports，最後檢視 zh-TW 是否需整體補齊（zh-TW 總量仍明顯少於 en／es-MX）。

### v0.9.10（2026-09-29）

**使用者說明改為可機械驗證，並接入 CI**

- **審查結論：內容本身是完整的。** 逐一呼叫 `getGuideSection()` 驗證 15 個頁面 + `exploration` 的 4 個子頁籤（共 19 個目標）× 3 語系，**全部都有專屬內容**，沒有缺頁或空欄位。
- **但原本無法驗證，且新增頁面會靜默退化成罐頭文字**：
  - `topics` 的型別是 `Record<string, Partial<Record<locale, Partial<GuideSection>>>>` —— 每一層都是 `Partial`，所以少頁面／少語系／少欄位，編譯器都不會報錯。
  - `getGuideSection()` 找不到條目時會回傳 `common[lang]` 通用文字（`base = { ...common[lang], title: '' }`），所以漏寫說明不會有任何錯誤或空白，使用者只會看到「說明目前頁面的用途與結果」這種無意義內容。
  - 內容還分散在 `topics` 資料與約 15 段程式碼中的語言三元運算式（`distributionSteps`／`trendSteps`／`timeseriesSteps`／`grrSteps`／`explorationGrrExtra`／`predictionProfilerNotes`／`approvalSpcNotes`／`dataImportContract`…），因此無法只讀資料回答「說明是否完整」。
- **新增 `scripts/check-guide-coverage.mjs`**（接進 CI）：
  - 頁面清單**從 `src/types` 的 `AppTab` union 解析而來** —— 新增頁面會直接讓檢查失敗，直到補上說明。
  - 呼叫真的 `getGuideSection()`（對話框的唯一出口），斷言 8 個欄位皆非空。
  - 以「不存在的頁面」取得通用 baseline，偵測「只有罐頭文字」的情況（不需匯出 `common`）。
  - **RED 驗證**：暫時加入一個沒有說明的頁面 → 檢查 exit 1 並逐語系指出 `renders only the generic boilerplate (no guide entry?)`。
- `package.json` 新增 `check:i18n` 與 `check:guide` 兩個腳本，CI 的 frontend job 都會執行。
- 未做（建議後續）：把分散在程式碼三元式中的欄位搬回 `topics` 資料、移除 `Partial`、處理未使用的 `title`。目前檢查已能覆蓋這些風險，所以不急。

### v0.9.9（2026-09-28）

**Excel 報告補齊 HTML 已有的區塊**

- `excel.py` 原本只有 102 行（`html.py` 571 行），產出 7 個 Sheet，卻靜默丟棄 `main.py` 已收進 `ReportData` 的資料。實測同一份報告：**Excel 8.8 KB vs HTML 52 KB**；HTML 有 20 個區塊，Excel 只有 7 個。
- **新增 12 個 Sheet**：規格（LSL/USL／目標，原本完全沒有）、資料品質、最終模型（含**係數表**）、SPC（管制界限 + **Cp/Cpk/Pp/Ppk** + σ + 違規數）、SPC 優化建議、分佈配適、異常情境、蒙地卡羅（含百分位與異常貢獻排名）、可信度（六維）、建議製程窗口、治理與追溯（Gate／未確認項目／外推警告／版本鏈步驟）、來源標籤。
- 模型比較由 7 欄擴充為 11 欄（補 AUC／Accuracy／Shape k／AIC）。
- 新增 `tests/test_reporting_excel.py`（14 個測試）：斷言每個有值的區塊都要獨立出現在 workbook 中 —— 缺區塊的檔案「開啟正常」，只有機械化斷言才抓得到。**RED 驗證：修正前 14 項中 9 項失敗**。
- 測試：659 passed / 12 skipped。
- 註：`monte_carlo` 與 `credibility` 目前仍由報告產生端決定是否填入；若該次分析未執行模擬或驗證，對應 Sheet 不會出現（這是預期行為，非遺漏）。

### v0.9.8（2026-09-28）

**README 指標改為實測值**

- 「測試統計」表原本宣稱 585 passed / 1 skipped / 83% 覆蓋率 / 852 commits / ~30,700 行，實測為 **645 passed / 12 skipped / 78% / 881 commits / ~32,400 行應用程式碼**（另有 ~9,800 行測試碼）。已全部更正為量測值。
- 表下補上量測指令，讓這些數字可被重跑驗證；並註明 CI 每次都執行哪些檢查。
- 先前版本紀錄中的數字（例如 v0.3.0 的「345 passed」）保留為當時的歷史紀錄，不回改。

### v0.9.7（2026-09-28）

**i18n key 對齊，並在 CI 加上對齊檢查**

- **es-MX 缺 6 個生效中的 key**：`settings.modelSettings` 與 `settings.lightgbmDevice*`（`lightgbmDevice`／`Auto`／`Cpu`／`Gpu`／`Note`）。它們被 `Settings.tsx:399-416` 的 LightGBM 裝置選單使用，所以西語使用者看到的是原始 key 而非翻譯。已補上。
- **三語的死 key 移除**：`en` 的 `guide.exploration.distribution.*` 與 `zh-TW`／`es-MX` 的 `guideDistribution.*`（各 7 個）**兩者都沒有任何程式引用**。說明視窗的正文來自 `src/components/guide/guideContent.ts`（各語系內嵌文字），i18n 只提供 `guide.labels.*` 與 `guide.generic.*`。因此正解是刪除，而非把舊名改成新名。
- **結果**：三個語系現在都是 **1345 keys，完全對齊**（先前 en/zh-TW 各 1345 但相差 7 個、es-MX 1339）。
- **新增 `scripts/check-i18n-parity.mjs`** 並接入 CI 的 frontend job。缺 key 在執行期不會拋錯（i18next 會顯示原始 key 或退回英文），所以漂移只有使用者回報才會發現 —— 這正是這次的情況。已 RED 驗證：移除一個 key 會 exit 1 並指出 `settings.lightgbmDeviceGpu missing from: es-MX`。
- README 的 key 數宣稱由 709 更正為 1345。

### v0.9.6（2026-09-28）

**模型註冊表治理：讀取改為快照、刪除受狀態限制**

- **`get()` 不再回傳活物件**：原本呼叫端可透過回傳值直接設定 `status = "approved"` 或改寫係數，完全繞過狀態機（而且專案還原路徑 `main.py` 就是這樣做的）。現在回傳**中繼資料的快照**（inputs/metrics/coefficients/status），但**刻意共用配適好的 estimator** —— 深拷貝隨機森林在「走訪所有模型」的處理函式中會造成真實的效能問題，而 estimator 只被 `.predict()` 讀取。
- **`delete()` 受狀態限制**：只有 `draft` 與 `retired` 可刪除；帶有核准權重的模型（`pending_validation`/`validated`/`approved`）會拒絕刪除並提示改用 retire，讓「曾經被核准」的紀錄得以留存。
- **新增 `restore_status()`**：專案重播時還原已持久化的狀態（該狀態不必然能由單一合法轉移抵達）。這是唯一獲准繞過狀態圖的路徑，IPC 處理函式只能用 `transition()`。
- `transition()` 現在回傳快照，且**改動回傳值不會影響已儲存的狀態**。
- **更正一項審閱報告的說法**：報告稱「狀態轉移未寫入版本鏈」—— 實際上 `_handle_modeling_transition` 與 `_handle_modeling_delete` 已經呼叫 `_VERSION_CHAIN.register_entity(...)`（`main.py:744`、`:752`）。所以那項不是缺口。
- 新增／更新 6 個測試，並經 RED 驗證 —— 修正前 5 項失敗。測試 645 passed / 12 skipped。

### v0.9.5（2026-09-28）

**SPC 管制圖統計修正（c4 / d2 誤用、A3 公式、WE 區間寬度、Cp≡Pp）**

- **X-bar/S 的 A3 用錯公式**：程式用 `3/(d2·√n)`（那其實是 A2 的公式）當作 A3，正確是 `3/(c4·√n)`。以 n=5 為例是 0.577 對 1.427 —— **X-bar 管制界限窄了約 2.5 倍**，會持續發出假警報。已新增 `_c4` 常數表（由公式產生，非抄表）。
- **S 圖的 sigma 除數用錯**：`s_bar / d2` 應為 `s_bar / c4`。
- **Western Electric 規則用錯 sigma**：規則是套用在**子群組均值**（被繪製的統計量）上，區間寬度應為 `σ/√n`，原本傳入個別值的 σ，使每個區間寬了 √n 倍。X-bar/R 與 X-bar/S 兩條路徑都修正。
  - 註：X-bar/S 路徑上這兩個錯誤原本**幾乎互相抵銷**（σ 低估 2.5× vs 區間寬 √n≈2.24×，淨效果約 1.1×），所以該圖的實際影響比預期小；**X-bar/R 只有區間寬度這個錯誤**，是真正明顯漏報的那條。
- **individuals 的能力指數**：`sigma_within` 原本直接取整體標準差，導致 **Cp≡Pp、Cpk≡Ppk**（而函式 docstring 自己寫著應由 moving range 估計）。現改為 `MR_bar / d2(2) = MR_bar / 1.128`，與 `compute_i_mr` 一致。
- 新增 `tests/test_spc_control_charts.py`：預期值全部由教科書公式**獨立計算**（非取自模組自身的表），並經 RED 驗證 —— 修正前 6 項中 4 項失敗。
- 測試：640 passed / 12 skipped。

### v0.9.4（2026-09-28）

**引擎 bundle 縮小一半：移除未使用的 polars、預設排除 CUDA 執行期**

- 凍結引擎從 **1332 MB 降至 664 MB**（減少 667 MB）。實測來源：`_internal/nvidia` 452 MB、`_internal/_polars_runtime_32` 211 MB。
- **移除 `polars` 相依**：全 engine 與 tests 完全沒有 `import polars`（先前唯一的 `pl.` 命中是 `lightning.pytorch` 的別名），移除後 634 個測試仍全數通過。
- **CPU / CUDA 產物區分**：Linux 上 xgboost 會拉入約 450 MB 的 `nvidia-*` CUDA 執行期函式庫，而 GPU 訓練是選配、預設關閉，且還需系統 CUDA toolkit 與 NVIDIA 顯卡。**預設產物為 CPU 版**；需要時以 `npm run engine:build:cuda` 建置。CPU 版在 GPU 機器上同樣可執行，只是訓練走 CPU。
- 煙霧測試確認凍結引擎在移除上述項目後仍正常啟動並回應 `engine/ping`。

### v0.9.3（2026-09-28）

**助手輸入框停用時顯示原因**

- 助手需要已開啟的專案才能對話（`projectReady`），但輸入框停用時沒有任何說明，容易被誤認為故障。現在未開啟專案時會在輸入框下方顯示「請先開啟或建立專案」提示（三語）。

### v0.9.2（2026-09-28）

**安全性強化、預測與去識別化修正、引擎隨附打包**

- **權限強制**：126 個 IPC 方法全部納入角色檢查（`auth/policy.py`）。原本角色只被記錄、從未被檢查，且 `authenticate()` 對任何使用者接受任意非空密碼。新增本機信任工作階段（`PROCESS_INTELLIGENCE_LOCAL_ROLE`，出廠 admin），桌面 App 免登入即可使用；登入受限帳號後權限真實生效。未分類方法 fail closed。
- **去識別化**：改為帶金鑰的 HMAC 假名化（128 bits），取代可被列舉還原的無鹽截斷 SHA-256；噪音改為依各欄位尺度縮放；預覽與實際傳送的 payload 共用單一轉換，稽核雜湊現在確實描述傳送的內容（原本有三種情況不一致）。預覽會顯示無效遮罩的警告與金鑰指紋。
- **預測修正**：`residual_hybrid` 原本只回傳殘差而非 DOE 趨勢加殘差（實測 104 的值回傳 -0.00）；模型輸入原本使用排序後的欄位順序而非配適順序，會靜默對調欄位（`prediction.py` 與 `monte_carlo.py`）。新增預測契約版本，舊專案會得到明確的「請重新配適」訊息。
- **引擎隨附打包**：以 PyInstaller 凍結引擎並透過 `bundle.resources` 出貨，執行時由資源目錄解析，開發環境回退路徑會列出所有嘗試過的候選。安裝版不再需要系統 Python。
- **Tauri 安全**：設定 CSP（原本為 `null`）並分離 dev 政策；檔案系統權限收斂至對話框選取的路徑，取代 `**`。補上原本缺少的 `fs:allow-write-file`，修正 PDF／Excel 匯出無法寫檔的問題。
- **依賴**：`plotly.js` 4.1.1 與 `react-plotly.js` 4.1（清除 critical 的 maplibre-gl 公告）；`xlsx` 改用隨附的 SheetJS 0.20.3 tarball（npm registry 版本無可用修補，且 npm 12 預設封鎖遠端 tarball URL）；Vite 8（Rolldown），建置時間 15.6s → 1.8s。
- **CI**：新增 `validate` workflow（typecheck、production build、出貨相依稽核、pytest、cargo test）。僅出貨相依會阻擋 PR。此 workflow 上線後立即找出兩個既有問題：`xlsx` 的遠端 URL 相依，以及一個自 v0.6.0 資料集改版後就腐化的 Rust 時間序列測試。
- **測試**：引擎 634 passed / 12 skipped；`cargo test` 於 CI 通過（含兩個 live-engine 測試）。

### v0.9.1（2026-09-16）

**時間序列深度模型與 DOE／模型核准強化**
- 接入 Temporal Fusion Transformer（TFT），支援 PyTorch／Apple MPS 訓練與預測；沒有 PyTorch 時仍使用既有模型。
- 新增序列感知模擬（sequence-aware simulation）與時間序列最終風險閘門。
- DOE 強化：Pareto、Contour、3D Surface、殘差診斷；Prediction Profiler（Maximize／Minimize／Target）；SPC 穩定性 Gate 與人工覆核稽核。
- 報告新增「DOE 圖表與使用限制」段落；報告匯出失敗時在 UI 顯示錯誤詳細訊息。
- 完整部署細節見 [docs/releases/v0.9.1.md](docs/releases/v0.9.1.md)，TFT 部署見 [docs/deployment-time-series.md](docs/deployment-time-series.md)。

### v0.9.0（2026-09-15）

- 首次支援時間序列深度模型：將 Temporal Fusion Transformer（TFT）接入時間序列模型階梯。
- 序列感知（sequence-aware）模擬流程與時間序列最終風險閘門。
- 詳見 [docs/releases/v0.9.1.md](docs/releases/v0.9.1.md) 與 [docs/deployment-time-series.md](docs/deployment-time-series.md)。

### v0.8.3（2026-09-11）

- 新增依目前頁面切換的使用說明視窗，涵蓋功能目的、統計原理、公式、圖表判讀、限制與工程建議。
- 使用說明支援繁體中文、英文、西班牙文。

### v0.8.2（2026-09-10）

**蒙地卡羅抽樣分布**
- 預設可依資料健檢的 `best_distribution` 自動選擇抽樣方式。
- 支援 `uniform`、`triangular`、`normal` 與 `empirical`（Bootstrap）。
- 仍可手動選擇歷史資料 Bootstrap 或各欄位常態抽樣。
- 模擬結果記錄實際抽樣方式、輸入分布參數與外推風險。

### v0.8.1（2026-09-10）

**敏感度分析與效應量**
- 新增 permutation-RMSE 敏感度分析與標準化效應量表／圖，整合至模型中心、報告與 AI 摘要。
- Excel 報告加入敏感度指標。

### v0.8.0（2026-09-09）

**資料來源健檢與建模前 Gate**
- 匯入並確認 input/output 後，自動檢查缺失值、常數欄位、有效樣本與數值摘要。
- 批次執行候選分布配適，顯示最佳分布、AIC/BIC/KS 與欄位狀態。
- 以可視化圖表呈現資訊、警告與阻擋欄位數，並在模型配適前阻擋重大資料問題。
- AI 助手與報告 metadata 可追溯 readiness 狀態與資料集版本；分布結果不會取代模型驗證。

### v0.7.0（2026-09-09）

- 建立單一 `VERSION` 來源與 `npm run version:sync`，同步前端、Tauri 與 Python 版本。
- 報告 API 統一回傳 dataset、grain/filter、格式與狀態 metadata。
- AI 助手針對 timeout、provider unavailable、回覆格式錯誤與資料集未載入提供可操作提示。
- 完成 SPC、探索分析與蒙地卡羅的多層級篩選與樣本數追溯。
- 發布流程加入跨平台 Tauri 建置矩陣與版本一致性檢查。

### v0.6.0（2026-09-09）

**多層級資料模型（可選）**
- 工程範本延續 `input_*`、`output_*` 與 `result` 欄位，並加入產品／Lot／機台／站點／製程步驟／子群組追溯欄位。
- 匯入時自動偵測 metadata、時間欄位、識別欄位與類別欄位；既有 CSV 不需修改即可使用。
- SPC 支援以 `subgroup_id` 或選定欄位進行子群組分析，並保留 grain／filter 追溯資訊。
- 版本鏈與分析上下文可記錄資料粒度與篩選條件。

### v0.5.0（2026-09-09）

**受控 AI 助手與跨頁分析上下文**
- 支援本機 Ollama 與明確啟用的 OpenAI-compatible Custom Provider
- 雲端傳送前提供去敏預覽、專案同意與可追溯雜湊
- AI 助手僅提出操作草案，所有會改變專案的操作都需人工確認
- SPC、分布、模型、模擬、預測與報告頁面的分析摘要可傳入助手
- AI 回覆支援結構化證據、限制、建議與多語系顯示
- 報告 HTML/PDF/Excel 支援使用者選擇輸出位置

**可靠性與使用體驗**
- Custom Provider 錯誤顯示實際端點與例外類型
- 雲端 AI 請求期間顯示分析引擎處理中狀態
- AI 助手輸入框採雙 Enter 送出，降低誤發訊息
- 模型設定可持久化，並避免遮罩 API 金鑰被覆寫

### v0.4.0（2026-09-06）

**可信分析鏈**
- 新增版本鏈、Gate 確認、模型治理、報告追溯與稽核紀錄
- 專案可重新開啟並恢復資料集、模型與分析狀態
- 報告輸出包含可追溯的資料、模型、模擬與審核資訊
- 支援跨平台部署與 Python 3.12 `uv` 環境

### v0.3.0（2026-09-05）

**統計異常偵測（IQR + Z-score + CUSUM）**
- 引擎 `detect_outliers()`：IQR 與 Z-score 雙閾值，返回 outlier_indices / n_outliers / stats
- 引擎 `detect_change_points()`：CUSUM statistic，返回 change_points / n_change_points
- `spc/analyze` 回傳 `outlier_indices` / `change_points` / `outlier_stats`
- SPC 圖表：藍色圓點標示離群值、綠色三角形標示改變點
- 製程定義手設 LCL/UCL 正確套用到 SPC 圖與趨勢圖
- 6 支新測試；全引擎 345 passed, 1 skipped

**管制界限修復**
- `analyzeSPC()` 新增 `control_limits` 參數，手設界限優先於自動 mean±3σ
- Exploration 趨勢圖：所有 numeric 欄位均顯示自動計算的 UCL/LCL 虛線

**模型中心擴充**
- DOE 圖表與治理：Pareto、主效應、交互作用、Contour、3D Surface、殘差診斷；SPC 穩定性 Gate 與人工覆核稽核紀錄。
- Prediction Profiler 支援 Maximize／Minimize／Target 目標與操作範圍內候選設定建議。
- 模型類型選單右側顯示說明文字（含目標欄位與輸入限制）
- 模型表格新增 Equation 欄位 + 各模型適用的 metrics 列（AUC/accuracy/shape_k/AIC）
- Logistic 迴歸支援字串二元目標（OK/NG），前端預先檢查連續目標
- 目標欄位選單：logistic 模式下顯示所有二元欄位（numeric 或文字）

**蒙地卡羅與互動預測（What-if）擴充**
- 支援全部 8 種模型：doe_linear / doe_quadratic / random_forest / xgboost / lightgbm / residual_hybrid / logistic_regression / weibull_regression
- Tree models 使用 `fit.model.predict()` 直接預測；logistic 輸出 P(NG)；weibull 輸出 mean TTF

**互動預測（What-if）擴充**
- `prediction/predict` 支援全部 8 種模型（tree models 使用 `fit.model.predict()`）
- Logistic 模型：顯示 P(NG) 機率 + 類別 Tag（OK/NG + 低/高風險）
- Weibull 模型：顯示 mean TTF + 壽命 Tag（長/短）
- 修正 compact coefficient key normalize（`x1x2` → `x1_x_x2`）

**DOE 統計推論（ANOVA + p 值）**
- 引擎 `compute_doe_statistics()`：ANOVA F 檢定 + 各係數 t 檢定 + p 值 + 95% 信心區間
- 前端「DOE 統計推論」Card：顯著性表格 + 判讀說明
- 判讀規則（工業標準）：p<0.001 極顯著 / p<0.01 顯著 / p<0.05 邊際顯著 / p≥0.05 不顯著
- 輔助評語：依 R² × 顯著項比例 → Excellent/Good/Moderate/Poor fit

**系統設定 — LightGBM 裝置**
- 設定頁新增「LightGBM Device」下拉選單（auto / cpu / gpu）
- `auto` 預設：先試 GPU，LightGBM 未編譯 GPU 時自動退回 CPU
- README 新增「LightGBM GPU 支援（選配）」章節（含 Windows/Linux 編譯指南）

**Logistic 迴歸修復**
- 支援字串二元目標（OK/NG）：`pd.to_numeric(errors='coerce')` fallback → label encode
- 前端預先檢查：`unique_count > 10` 時跳出 warning，不發請求
- 目標欄位選單：logistic 模式下顯示所有二元欄位（numeric 或文字）

**Weibull 迴歸修復**
- 修正 intercept/feature 索引錯位（`result.x[:-1]` → `result.x[:-2]`）
- 恢復 `np.mean` 遺漏

**i18n**
- processDefine 段新增 `lcl`/`ucl` 翻譯（en/zh-TW/es-MX）
- spc 段新增 `outliers`/`changePoints` 等 6 keys ×3 語
- modelCenter column 段新增 `equation/AUC/accuracy/shape_k/AIC` keys ×3 語
- modelCenter modelType.desc 段新增 8 種模型說明文字（含適用場景）×3 語
- prediction 段新增 `predictedProbability`/`predictedMeanTTF`/`ng`/`ok`/`highRisk`/`lowRisk` ×3 語

**版本**
- 引擎 `__version__`、Tauri 與前端版本同步至 0.5.0
- 前端 About 對話框顯示 v0.5.0

---

### v0.2.0（2026-09-05）

**SPC 深化**
- EWMA / CUSUM 控制圖（檢測小漂移）
- 規格線 LSL/USL 參考線於位置圖
- 多欄位能力比較表格
- 多機台 SPC 比較（跨 dataset）
- 優化建議（Cpk 不足 / 偏移偵測 / 趨勢偵測）
- 報告匯出包含 I-MR 控制圖 SVG
- 修復 UCL/LCL/CL 從未顯示 bug（control_limits 巢狀 vs 扁平）
- 修復 i-mr 未渲染 MR 子圖

**蒙地卡羅**
- 預測能力指數 Pp/Ppk（simulation-based）
- NG 機率風險分級

**AI 模型擴充**
- XGBoost / LightGBM 回歸模型
- Random Forest 自動特徵選取
- 超參數 UI 控制

**AI 助手**
- SPC / MC / Exploration 領域知識增強
- 能力指數解讀指南
- Western Electric 7 規則說明

**效能優化**
- Plotly lazy-load（主 chunk 5.8 MB → 347 kB）
- Vendor chunk 拆分（react / antd / plotly）

**技術債**
- `.coverage` 加入 gitignore
- Tauri icons 追蹤
- filter_value 空字串防護

---

### v0.1.0（2026-09-02）

- 初始版本：Data Import、Process Definition、Exploration、Model Center、Validation、Monte Carlo、SPC、Reports
- 三語支援（en / zh-TW / es-MX）

## 開發者

- **作者**: Fred Wang
- **授權**: MIT License
