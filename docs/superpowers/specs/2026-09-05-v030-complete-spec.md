# v0.3.0 完整規格書 (Final Spec)

**版本**: v0.3.0
**日期**: 2026-09-05
**作者**: Fred Wang
**狀態**: 完整實作並部署

---

## 目錄

1. [系統架構](#1-系統架構)
2. [功能模組總覽](#2-功能模組總覽)
3. [資料匯入與角色分配](#3-資料匯入與角色分配)
4. [製程定義](#4-製程定義)
5. [模型中心（8 種模型）](#5-模型中心8-種模型)
6. [統計推論與模型驗證](#6-統計推論與模型驗證)
7. [互動預測（What-if）](#7-互動預測what-if)
8. [SPC 統計製程控制](#8-spc-統計製程控制)
9. [蒙地卡羅模擬](#9-蒙地卡羅模擬)
10. [探索分析](#10-探索分析)
11. [系統設定](#11-系統設定)
12. [多語言支援](#12-多語言支援)
13. [API 端點總覽](#13-api-端點總覽)
14. [技術決策記錄](#14-技術決策記錄)
15. [部署指南](#15-部署指南)

---

## 1. 系統架構

### 1.1 技術棧

| 層級 | 技術 |
|---|---|
| 前端框架 | React 18 + TypeScript |
| UI 元件庫 | Ant Design 5 |
| 圖表 | Plotly.js（lazy-load）|
| 狀態管理 | Zustand |
| 多語言 | i18next（en / zh-TW / es-MX）|
| 桌面框架 | Tauri 2.0（Rust）|
| 分析引擎 | Python 3.11 + uv venv |
| 數學計算 | NumPy、pandas、scipy、scikit-learn |
| 強化學習 | XGBoost、LightGBM（可選 GPU）|
| 可解釋性 | SHAP |
| 報告匯出 | HTML、Excel、PDF |

### 1.2 資料流程

```
CSV/XLSX 匯入 → 欄位偵測 → 角色分配（input/output/quality_label）
    ↓
製程定義（LSL/USL、管制界限）→ 模型配適（8 種模型）
    ↓
驗證分析（ANOVA、SHAP、交互作用）→ 互動預測 → 蒙地卡羅 → 報告產生
```

### 1.3 專案規模

| 項目 | 數值 |
|---|---|
| 引擎測試 | 345 passed, 1 skipped |
| 前端 TypeScript | tsc clean |
| 前端程式碼行數 | ~15,100 行 |
| 引擎程式碼行數 | ~5,000 行 |
| i18n 語言 | 3（en / zh-TW / es-MX）|
| i18n keys 總計 | 300+ |
| Engine IPC 端點 | 85+ |
| 前端 API 函數 | 96 個 |

---

## 2. 功能模組總覽

| 模組 | 頁面 | 核心功能 |
|---|---|---|
| 資料匯入 | `data-import/` | 檔案上傳、欄位偵測、角色分配、品質檢查 |
| 製程定義 | `process-define/` | 規格界限（LSL/USL）、管制界限（LCL/UCL）|
| 模型中心 | `model-center/` | 8 種模型配適、比較、驗證、統計推論 |
| 互動預測 | `prediction/` | What-if 分析、情景儲存 |
| SPC 控制圖 | `spc/` | I-MR / Xbar-R / EWMA / CUSUM + 異常偵測 |
| 蒙地卡羅 | `monte-carlo/` | 風險模擬、NG 機率、預測能力指數 |
| 探索分析 | `exploration/` | 分布、趨勢、時間序列、GRR |
| 報告產生 | `report/` | HTML / Excel / PDF 匯出 |
| 系統設定 | `settings/` | AI 提供者、LightGBM Device、用戶管理 |
| 驗證實驗室 | `validation/` | 實驗記錄、模型比較 |

---

## 3. 資料匯入與角色分配

### 3.1 支援格式

- CSV（UTF-8、GB2312）
- Excel（.xlsx、.xls）

### 3.2 欄位角色（Field Role）

| 角色 | 用途 | 影響功能 |
|---|---|---|
| `input` | 輸入變數 | DOE、回歸模型、交互作用分析 |
| `output` | 連續輸出 | 回歸模型、SPC、蒙地卡羅 |
| `quality_label` | 二元標籤 | Logistic 迴歸（OK/NG）|
| `identifier` | 批次/序號 | 分組分析 |
| `timestamp` | 時間戳記 | 時間序列分析 |
| `category` | 分類變數 | 分群分析 |

### 3.3 品質檢查

系統自動檢查：
- 格式混用（數字/文字混雜）
- 單位混用（不同單位輸入）
- 輸入超出工程範圍
- 輸出缺少規格界限

### 3.4 範例資料

內建測試資料 `data/test_dataset.csv`：
- 13 欄 × 45 行
- 含 5 個輸入變數 + 連續輸出 + 二元標籤（OK/NG）
- 適用全部 8 種模型測試

---

## 4. 製程定義

### 4.1 規格界限（Spec Limits）

- **LSL**（Lower Specification Limit）：下規格限
- **USL**（Upper Specification Limit）：上規格限
- **Target**：目標值
- 關係：LSL ≤ Target ≤ USL

### 4.2 管制界限（Control Limits）

- **手動設定**：在製程定義頁設定每欄位的 LCL/UCL
- **自動計算**：mean ± 3σ
- **優先級**：手設 > 自動計算
- **套用到**：
  - SPC 控制圖
  - 探索趨勢圖
  - 蒙地卡羅 NG 判定

### 4.3 異常情境（Anomaly Scenarios）

- 基於規格界限和管制界限偵測異常
- 支援工程模板自訂

---

## 5. 模型中心（8 種模型）

### 5.1 模型類型總覽

| # | 模型類型 | 目標欄位 | 訓練時間 | 適用場景 |
|---|---|---|---|---|
| 1 | `doe_linear` | 連續 | 快 | 主要效應分析、基準模型 |
| 2 | `doe_quadratic` | 連續 | 快 | 反應面最佳化、交互作用 |
| 3 | `random_forest` | 連續 | 中 | 非線性、特徵重要性 |
| 4 | `xgboost` | 連續 | 中 | 高維、精度優先 |
| 5 | `lightgbm` | 連續 | 快 | 大資料集、高效訓練 |
| 6 | `residual_hybrid` | 連續 | 中 | 線性趨勢 + 非線性殘差 |
| 7 | `logistic_regression` | 二元 | 快 | OK/NG 分類、機率預測 |
| 8 | `weibull_regression` | 正連續 | 中 | 可靠度、失效時間分析 |

### 5.2 各模型詳細規格

#### 5.2.1 DOE 線性（doe_linear）

- **方法**：最小二乘回歸（sklearn LinearRegression）
- **公式**：Y = β₀ + β₁X₁ + β₂X₂ + ...
- **輸入限制**：至少 3 個輸入
- **輸出指標**：R²、Adj R²、RMSE、MAE
- **統計推論**：ANOVA F 檢定、係數 t 檢定、p 值

#### 5.2.2 DOE 二次（doe_quadratic）

- **方法**：含交互作用項和平方項的最小二乘回歸
- **公式**：Y = β₀ + ΣβᵢXᵢ + ΣβᵢⱼXᵢXⱼ + ΣβᵢᵢXᵢ²
- **輸入限制**：至少 2 個輸入
- **適用場景**：反應面最佳化、捕捉曲線效應

#### 5.2.3 隨機森林（random_forest）

- **方法**：決策樹集成（sklearn RandomForestRegressor）
- **超參數**：n_estimators=200, max_depth=10, min_samples_leaf=3
- **自動特徵選取**：支援
- **輸出指標**：R²、RMSE、MAE、特徵重要性

#### 5.2.4 XGBoost（xgboost）

- **方法**：梯度提升樹
- **超參數**：n_estimators=200, max_depth=6, learning_rate=0.1
- **自動特徵選取**：支援
- **適用場景**：高維資料、預測精度優先

#### 5.2.5 LightGBM（lightgbm）

- **方法**：梯度提升樹（按葉片生長）
- **超參數**：n_estimators=200, max_depth=6, learning_rate=0.1
- **裝置設定**：CPU / GPU（auto/fallback）
- **自動特徵選取**：支援
- **適用場景**：大型資料集（10 萬+ 行）

#### 5.2.6 殘差混合（residual_hybrid）

- **方法**：DOE 線性/二次 + 隨機森林殘差補償
- **公式**：Y = f_DOE(X) + r_RF(X)
- **輸出指標**：R²、RMSE、MAE、Adj R²
- **適用場景**：同時需要可解釋性與精度

#### 5.2.7 Logistic 迴歸（logistic_regression）

- **方法**：邏輯回歸（sklearn LogisticRegression）
- **目標**：二元分類（0/1 或 OK/NG）
- **輸出**：P(NG) 機率 [0, 1]
- **支援字串標籤**：OK/NG 自動 label encode
- **輸出指標**：Accuracy、Recall、AUC
- **前端顯示**：機率 % + 類別 Tag（OK/NG + 低/高風險）

#### 5.2.8 Weibull 迴歸（weibull_regression）

- **方法**：Weibull 分佈最大似然估計
- **公式**：log(λ) = β₀ + β₁X₁ + ...，shape k 為常數
- **目標**：嚴格大於 0 的連續變數（失效時間）
- **輸出**：mean TTF = λ · Γ(1 + 1/k)
- **前端顯示**：平均失效時間 + 壽命 Tag（長/短）
- **防護**：log_lambda clamp ±700 防止 overflow

### 5.3 模型卡片指標

| 模型類型 | 顯示指標 |
|---|---|
| Regression（6 種）| R²、RMSE、MAE、Adj R² |
| Logistic | AUC、Accuracy、Recall |
| Weibull | AIC、Shape k、Mean TTF |

### 5.4 模型生命周期

```
draft → pending_validation → validated → approved → retired
  ↓           ↓              ↓           ↓
任意狀態可直接 retired
```

### 5.5 模型操作

| 操作 | 說明 |
|---|---|
| Fit | 配適新模型 |
| Transition | 切換狀態 |
| Delete | 刪除模型（需確認）|
| Compare | 比較多個模型 |
| SHAP | 計算可解釋性 |
| Extrapolation | 檢查外推風險 |
| DOE Statistics | ANOVA + p 值推論 |

---

## 6. 統計推論與模型驗證

### 6.1 ANOVA F 檢定

適用於 `doe_linear` 和 `doe_quadratic` 模型：

- **整體模型顯著性**：F 統計量 + p 值
- **判讀規則**：
  - p < 0.001：極顯著 (highly significant)
  - p < 0.01：顯著（significant）
  - p < 0.05：邊際顯著（marginally significant）
  - p ≥ 0.05：不顯著（not significant）

### 6.2 係數 t 檢定

每個係數的統計顯著性：
- 標準誤（Standard Error）
- t 統計量
- p 值
- 95% 信心區間

### 6.3 拟合評語（Fit Interpretation）

依 R² × 顯著項比例自動評級：

| 條件 | 評級 | 說明 |
|---|---|---|
| R²≥0.9, p<0.001, 70%+ 項顯著 | Excellent | 模型高度顯著，解釋力強 |
| R²≥0.7, p<0.05, 50%+ 項顯著 | Good | 模型統計顯著，預測力合理 |
| R²≥0.5, p<0.10 | Moderate | 顯示部分顯著性，需改進 |
| p≥0.05 且 R²<0.5 | Poor | 缺乏統計顯著性，建議重新設計實驗 |
| 其他 | Marginal | 檢視個別係數，考慮簡化模型 |

### 6.4 交叉驗證

- 5-fold CV（可調整）
- 回傳每 Fold 的 R² 和 RMSE
- 平均指標

### 6.5 殘差分析

- **常態性檢定**：KS 檢定（有 p 值）
- **Durbin-Watson 檢定**：自相關檢測
  - DW < 1.5：正自相關
  - DW > 2.5：負自相關
  - 1.5 ≤ DW ≤ 2.5：無自相關
- **偏度/峰度**：偏態和厚尾檢測
- **Q-Q 圖**：常態性視覺化
- **殘差 vs 預測值圖**：異變異檢測

### 6.6 實驗建議

自動產生的改進建議（三語）：
- `recInteraction`：強交互作用
- `recTransformationRightSkewed`：右偏殘差
- `recTransformationLeftSkewed`：左偏殘差
- `recTransformationHeavyTails`：厚尾殘差
- `recRangeExpansion`：殘差變異隨輸入增大
- `recNewFactor`：缺失輸入因子
- `recReplicate`：建議重複中心點

---

## 7. 互動預測（What-if）

### 7.1 功能

- 拖動滑桿調整輸入值
- 即時顯示預測結果
- 與規格界限比較（LSL/USL 標記）

### 7.2 模型適配

| 模型類型 | 預測結果含義 |
|---|---|
| Regression（6 種）| 數值輸出 |
| Logistic | P(NG) 機率 + 類別 Tag |
| Weibull | Mean TTF（平均失效時間）|

### 7.3 情景儲存

- 儲存預測參數組合
- 可命名和備註
- 可回溯比較

---

## 8. SPC 統計製程控制

### 8.1 控制圖類型

| 圖型 | 適用 | 管制線 |
|---|---|---|
| I-MR | 單筆數據 | UCL/LCL/CL（X）+ UCL（MR）|
| Xbar-R | 分組數據（子群 2-10）| UCL/LCL/CL（Xbar + R）|
| Xbar-S | 分組數據（子群 2-10）| UCL/LCL/CL（Xbar + S）|
| EWMA | 小漂移偵測 | UCL/LCL/CL |
| CUSUM | 小漂移偵測 | CUSUM 統計量 |

### 8.2 Western Electric 7 規則

1. 1 點超出 3σ
2. 2/3 點超出 2σ
3. 4/5 點超出 1σ
4. 8 點連續同側
5. 6 點連續趨勢
6. 15 點連續在 ±1σ 內
7. 14 點連續交錯

### 8.3 異常偵測

- **IQR 離群值**：Q1 - 1.5×IQR / Q3 + 1.5×IQR
- **Z-score 離群值**：\|z\| > 3.0
- **CUSUM 改變點**：C⁺ 或 C⁻ > H

### 8.4 圖表標記

| 標記 | 圖形 | 含義 |
|---|---|---|
| 離群值 | 🔵 藍色圓點 | IQR/Z-score 偵測 |
| 改變點 | 🔺 綠色三角形 | CUSUM 偵測 |
| 違規點 | ❌ 紅色 X | WE 規則違反 |
| UCL/LCL | 橙色虛線 | 管制界限 |
| CL | 綠色虛線 | 中心線 |

### 8.5 能力指數

- Cp、Cpk、Pp、Ppk
- 風險分級：≥1.33 綠 / ≥1.0 橘 / <1.0 紅

---

## 9. 蒙地卡羅模擬

### 9.1 支援模型

全部 8 種模型（tree models 使用 `fit.model.predict()`）：
- `doe_linear` / `doe_quadratic`：系數公式預測
- `random_forest` / `xgboost` / `lightgbm`：訓練模型直接預測
- `residual_hybrid`：DOE + RF 殘差組合
- `logistic_regression`：sigmoid → P(NG)
- `weibull_regression`：mean TTF = λ·Γ(1+1/k)

### 9.2 輸入分布

- 從歷史數據自動偵測分佈（normal / gamma / lognormal）
- 可手動指定分佈類型
- 支持異常注入（anomaly injection）

### 9.3 輸出指標

- NG 機率（%）
- 平均輸出值
- 中位數
- 百分位數（p1/p5/p50/p95/p99）
- 預測能力指數（Pp/Ppk）
- 直方圖 + CDF

### 9.4 Logistic 模型特化

- `ng_probability` = 預測機率均值
- 無需 LSL/USL 即可計算 NG 機率

### 9.5 Weibull 模型特化

- `output_mean` = 平均失效時間（mean TTF）
- 防護 overflow（log_lambda clamp ±700）

---

## 10. 探索分析

### 10.1 分布分析

- 直方圖 + 密度曲線
- 分佈擬合（normal / exponential / weibull / gamma / lognormal / beta）
- KS 檢定 p 值

### 10.2 趨勢圖

- 顯示所有 numeric 欄位的趨勢線
- 自動計算並顯示 UCL/LCL 管制線（橙色虛線）
- 與製程定義手設界限聯動

### 10.3 時間序列特徵

- Lag、Rolling mean/std
- Drift 檢測
- Change point 檢測

### 10.4 GRR 分析

- 精確度（EV）、量具變異（AV）、GRR
- %GRR 評級：<10% 綠 / 10-30% 橘 / >30% 紅

---

## 11. 系統設定

### 11.1 AI 提供者設定

- Ollama（本地）/ OpenAI / Azure / Custom
- API Key 安全處理（前端不持久化 masked key）
- 連線測試

### 11.2 LightGBM 裝置設定

| 選項 | 說明 |
|---|---|
| Auto（預設）| 先試 GPU，失敗自動退回 CPU |
| CPU | 強制 CPU 訓練 |
| GPU | 強制 GPU（需 NVIDIA CUDA + 編譯版）|

**注意事項**：
- Apple MPS 不支援 LightGBM GPU
- GPU 需從原始碼編譯 `cmake -DUSE_GPU=1`
- pip 版預設為 CPU

### 11.3 用戶管理

- 登錄 / 註冊 / 登出
- 角色權限（admin / engineer / viewer）
- 審計日誌

---

## 12. 多語言支援

### 12.1 支援語言

| 語言 | 代碼 | 覆盖率 |
|---|---|---|
| 英文 | en | 100% |
| 繁體中文 | zh-TW | 100% |
| 西班牙文 | es-MX | 100% |

### 12.2 關鍵 i18n Keys

- `modelCenter.doeStatisticsTitle` — DOE 統計推論
- `modelCenter.doeFitExcellent/Good/Moderate/Marginal/Poor` — 擬合評語
- `modelCenter.dwPositiveAutoCorr/NegativeAutoCorr/NoAutoCorr` — DW 解釋
- `modelCenter.recInteraction/TransformationRightSkewed/...` — 實驗建議
- `modelCenter.lightgbmDeviceAuto/Cpu/Gpu` — LightGBM 裝置
- `prediction.predictedProbability/PredictedMeanTTF/NG/OK/HighRisk/LowRisk` — 預測輸出

---

## 13. API 端點總覽

### 13.1 資料相關（15+）

| 端點 | 功能 |
|---|---|
| `data/import` | 匯入 CSV/XLSX |
| `data/datasets` | 列出資料集 |
| `data/series` | 取得時間序列數據 |
| `data/quality` | 品質檢查 |
| `data/detect` | 欄位偵測 |

### 13.2 模型相關（12+）

| 端點 | 功能 |
|---|---|
| `modeling/fit` | 配適模型 |
| `modeling/list` | 列出模型 |
| `modeling/transition` | 狀態遷移 |
| `modeling/delete` | 刪除模型 |
| `modeling/interactions/compute` | 交互作用分析 |
| `modeling/shap/explain` | SHAP 可解釋性 |
| `modeling/extrapolation/check` | 外推風險檢查 |
| `modeling/validation/analyze` | 交叉驗證 + 殘差分析 |
| `modeling/validation/full` | 完整驗證（含實驗建議）|
| `modeling/stats` | ANOVA + 係數 p 值 |
| `modeling/doe/generate` | DOE 設計表生成 |

### 13.3 SPC 相關（8+）

| 端點 | 功能 |
|---|---|
| `spc/analyze` | 單欄 SPC 分析 |
| `spc/analyze/batch` | 多欄批量 SPC |
| `spc/analyze/multi_dataset` | 跨資料集 SPC 比較 |
| `spc/capability` | 能力指數 |

### 13.4 蒙地卡羅（3）

| 端點 | 功能 |
|---|---|
| `monte_carlo/run` | 執行模擬 |

### 13.5 設定（5）

| 端點 | 功能 |
|---|---|
| `settings/get` | 取得設定 |
| `settings/update` | 更新設定 |
| `settings/test_connection` | 測試 AI 連線 |
| `engine/ping` | 引擎存活檢查（回傳 version）|
| `engine/health` | 引擎健康檢查 |

### 13.6 其他（20+）

- 預測、報告、雲端上傳、審核、流程圖等

---

## 14. 技術決策記錄

| 決策 | 選擇 | 原因 |
|---|---|---|
| 桌面框架 | Tauri 2.0 | 小型打包、原生效能 |
| Python 版本 | 3.11 | 相容性最佳，不支援 3.12+ |
| 模型儲存 | 記憶體（DatasetRegistry）| 單一使用者桌面應用 |
| LightGBM GPU | 可選，需重新編譯 | pip 版預設 CPU，MPS 不支援 |
| 統計推論 | OLS + t-test | DOE 模型有解析解 |
| 樹模型預測 | `model.predict()` | 不適用系數公式 |
| API Key 安全 | 前端不持久化 masked key | 避免存儲遮罩後的值 |
| 多語言 | i18next + JSON | 標準化、可擴展 |

---

## 15. 部署指南

### 15.1 前置需求

- Rust 1.77+
- Node.js 18+
- Python 3.11
- 系統 WebView（macOS: WebKit / Windows: WebView2）

### 15.2 LightGBM GPU 編譯（選配）

```bash
# macOS/Linux
git clone --recursive https://github.com/microsoft/LightGBM.git
cd LightGBM && mkdir build && cd build
cmake .. -DUSE_GPU=1
make -j$(nproc) && cd ../python-package && python setup.py install

# Windows
git clone --recursive https://github.com/microsoft/LightGBM.git
cd LightGBM && mkdir build && cd build
cmake .. -G "Visual Studio 17 2022" -A x64 -DUSE_GPU=1
cmake --build . --config Release
cd ..\python-package && pip install .
```

### 15.3 快速開始

```bash
npm install
cd engine && python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]" && pip install -r requirements.txt
cd ..
npm run tauri dev
```

### 15.4 CI/CD

- GitHub Actions 自動建置 4 平台（macOS aarch64/x86_64、Ubuntu、Windows）
- Tag push `v*` 觸發 Release
- 產出 `.dmg`、`.deb`、`.AppImage`、`.msi`

---

## 附錄 A：v0.3.0  commits 列表

```
ff76ebc fix(experiment_recommendation): restore settings field
021b3a3 fix(i18n): replace hardcoded English with i18n keys
b308710 fix(i18n): fix DW key lookup and recommendations
f28f262 feat(model-center): add delete button for fitted models
1ed57ce fix(model-center): fix TS type for recommendation
e44dd1b fix(i18n): localize DW interpretation and recommendation
ae04e28 fix(i18n): multilingual DOE fit interpretation
52de052 feat(modeling): add ANOVA F-test and coefficient p-values
3ea6f08 feat(prediction): adapt output card for logistic/weibull
7d4c780 docs: add LightGBM GPU compilation guide
c9e872f feat(settings): add LightGBM device selector
...（共 32 筆 commits）
```

## 附錄 B：測試統計

| 項目 | 數值 |
|---|---|
| 引擎測試 | 345 passed, 1 skipped |
| 測試覆蓋率 | 78% |
| 前端 TypeScript | clean |
| 前端 Build | ✓ built in ~11s |
