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
pip install -e ".[dev]" && pip install -r requirements.txt
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
2. **Python venv 已建立**：執行 `cd engine && python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]" && pip install -r requirements.txt`
3. **Node 模組已安裝**：執行 `npm install`
4. **瀏覽器 WebView**：macOS 內建 WebKit，Windows 需安裝 WebView2 Runtime

若啟動時出現以下錯誤，請檢查：

- **`failed to run cargo metadata`**：Rust 未安裝或 PATH 未設定，執行 `source $HOME/.cargo/env`
- **`engine start failed`**：Python venv 未建立，執行 `cd engine && python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]" && pip install -r requirements.txt`
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
- **AI 助手面板**: 右側可收合，支援 Enter 發送、思考動畫
- **模型下拉選單**: 從 API 載入可用模型，支援搜尋
- **設定持久化**: 修復保存時 api_key/base_url 流失問題

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
- **Español (México)**（es-MX）— 709 keys 完整翻譯（三語 key set 完全一致）

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
| **測試總數** | 250 tests |
| **跳過** | 1 |
| **覆蓋率** | 70% |
| **Commits** | 202 |
| **總代碼行數** | ~15,100 行 |
| **多語言** | 3（en / zh-TW / es-MX） |

## 設計原則

- 不綁定特定產業（非僅車載 ECU）
- 原始資料預設不送往雲端
- 傳統 DOE 永遠保留為回退方案
- 所有自動建議可解釋、可追溯、可人工覆核
- AI 助手支援三語言（en / zh-TW / es-MX）
- 資料上雲前必須遮罩 + 使用者確認 + 審核紀錄
- 製程節點與流程可配置（不寫死產業名稱）

## 技術決策記錄

| 決策 | 選擇 |
|------|------|
| 桌面框架 | Tauri 2.0 |
| Python 版本 | 3.11 (bundled venv) |
| 本地 AI | Ollama (local) + OpenAI/Azure/Custom |
| i18n 語言 | en + zh-TW + es-MX |
| 資料粒度 | 單片產品/單一測試樣本 |
| 模型儲存 | 記憶體 (DatasetRegistry) |
| 雲端策略 | 預設不上雲；上雲前遮罩 + 確認 |
| 製程定義 | JSON 配置（不硬編產業名稱） |
| 流程圖 | SVG 可交互編輯器 |

## 快速測試資料

專案提供預存測試資料：

```
data/test_dataset.csv
```

包含 82 筆資料，4 個輸入變數 (temperature, pressure, time, humidity) + 1 個輸出變數 (yield)，適合測試完整分析流程。

## 版本紀錄

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
- 模型類型選單右側顯示說明文字（含目標欄位與輸入限制）
- 模型表格新增 Equation 欄位 + 各模型適用的 metrics 列（AUC/accuracy/shape_k/AIC）
- Logistic 迴歸支援字串二元目標（OK/NG），前端預先檢查連續目標
- 目標欄位選單：logistic 模式下顯示所有二元欄位（numeric 或文字）

**蒙地卡羅與互動預測（What-if）擴充**
- 支援全部 8 種模型：doe_linear / doe_quadratic / random_forest / xgboost / lightgbm / residual_hybrid / logistic_regression / weibull_regression
- Tree models 使用 `fit.model.predict()` 直接預測；logistic 輸出 P(NG)；weibull 輸出 mean TTF

**i18n**
- processDefine 段新增 `lcl`/`ucl` 翻譯（en/zh-TW/es-MX）
- spc 段新增 `outliers`/`changePoints` 等 6 keys ×3 語
- modelCenter column 段新增 `equation/AUC/accuracy/shape_k/AIC` keys ×3 語
- modelCenter modelType.desc 段新增 6 種模型說明文字 ×3 語

**版本**
- 引擎 `__version__` 與 API 回傳版本同步至 0.3.0
- 前端 About 對話框顯示 v0.3.0

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
