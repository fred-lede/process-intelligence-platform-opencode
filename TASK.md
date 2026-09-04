# TASK.md

## Completed
### Approval tab — Task 2: Frontend engine.ts approval + report API types and functions
- **Status**: DONE
- `ReportRecord` interface + `listReports()` added after `generateReport()` (line ~495)
- Approval types/functions already existed (lines 937-1004): `ApprovalRecord`, `ApprovalAction`, `ApprovalResourceType`, `SubmitForReviewParams`, `ApproveParams`, `RejectParams`, `ListApprovalRecordsParams` + all 5 wrapper functions
- `npx tsc --noEmit` — clean (no errors)
- **Files changed** — `src/lib/engine.ts`

### Approval tab — Task 1: REPORT_REGISTRY + report/list IPC (commit ffe8dd1)
- **Status**: DONE
- **reporting/registry.py** — `ReportRegistry` in-memory registry (threading.Lock, uuid, sorted by timestamp desc) + module singleton `_REPORT_REGISTRY`
- **main.py** — import registry; `REPORT_REGISTRY.register(...)` inserted immediately before `if output_format == "html":` in `_handle_report_generate` (covers all 3 formats); new `_handle_report_list` + `report/list` dispatch
- **Tests** — new `tests/test_report_registry.py` (2: register+list, empty); `test_main_handlers.py` new `test_handle_report_list_returns_registry` (generate html → list returns Proj X)
- **Verification** — registry 2 passed; full suite **283 passed, 1 skipped** (baseline 280 + 3 new)
- **Files changed** — `engine/src/process_intelligence_engine/reporting/registry.py`, `engine/src/process_intelligence_engine/main.py`, `engine/tests/test_report_registry.py`, `engine/tests/test_main_handlers.py`
### Approval tab — Task 5: 收尾 docs + 最終驗證 + push
- **Status**: DONE
- 全引擎 **284 passed, 1 skipped**；`npx tsc --noEmit` clean；`npm run build` 成功
- spec reviewer 找到 `approval.records` i18n key 缺漏（HIGH）→ 三語各加 `records`；`handleSubmit` fallback `reviewer_role: 'engineer'` → `'reviewer'`（LOW，避免後端拒絕）
- 最終為 24 支 `approval.*` + `nav.approval` 全三語齊備（en/zh-TW/es-MX key set 一致）
- Commits: `2c96032`, `ffe8dd1`, `9e01b00`, `96564c7`, `7fe956f`, `5d8bda9`
- **Files changed** — 見各 task 條目

### Approval tab — Task 4: 路由 + assistantGuide + i18n（commit 7fe956f）
- **Status**: DONE
- `src/types/index.ts` `AppTab` union 加 `'approval'`（於 `'reports'` 後）
- `src/App.tsx` import `Approval` + `if (activeTab === 'approval') return <Approval />`
- `src/components/layout/Sidebar.tsx` 加 `AuditOutlined` + `{ key: 'approval', icon: <AuditOutlined /> }`（reports 後）
- `src/lib/assistantGuide.ts` 加 approval guide（submit / reviewer-admin 權限 / audit trail）
- i18n 三語 `nav.approval` + `approval.*` 19 支新 key（en/zh-TW/es-MX key set 一致）
- 驗證：JSON 有效、三語 approval key set 一致、tsc clean、build 成功

### Approval tab — Task 3b: 新增 Reviewer 角色 + 對齊 canReview（commit 96564c7）
- **Status**: DONE
- **根因**：spec §20 定義 Reviewer（審核模型/報告），但系統角色只有 admin/engineer/viewer，且後端 `approve`/`reject` 只收 `("reviewer","admin")` → 前端 engineer 顯示可審核、後端卻拒絕。user 選「新增 Reviewer 角色」方案
- **Backend**：`auth/models.py` `UserRole` 加 `REVIEWER = "reviewer"`（`_handle_auth_register` 的 `UserRole(role)` 自動接受）
- **Frontend**：`engine.ts:510` `UserRole` 加 `'reviewer'`；Settings register modal role Select 加 Reviewer option + `roleColor` map 加 `reviewer:'purple'`；`Approval.tsx` `canReview` → `currentRole === 'reviewer' || currentRole === 'admin'`（submit 仍所有已登錄 user 可用）
- **Tests**：`test_auth.py` 新增 `test_register_reviewer_role`；full suite **284 passed, 1 skipped**；tsc clean
- **Files changed** — `engine/src/process_intelligence_engine/auth/models.py`, `engine/tests/test_auth.py`, `src/lib/engine.ts`, `src/features/settings/Settings.tsx`, `src/features/approval/Approval.tsx`

### Approval tab — Task 3: Approval.tsx UI（commit 9e01b00）
- **Status**: DONE
- `src/features/approval/Approval.tsx` 完整審核 tab：資源表（modeling/list 的 model + report/list 的 report）Type/Resource/Status/Action 欄；`getApprovalStatus()` 依資源求 status + record 覆寫；pending_review 資源對 reviewer/admin 顯示 Approve/Reject（`canReview`）；Submit modal（type→resource→reviewer→comments→`submitForReview`）；Approve/Reject modal 用 `getCurrentUser()` 身份 + comments；Records card（`approval/records` 完整審計軌跡）
- 已存在 engine.ts approval API（SubmitForReviewParams/ApproveParams/RejectParams/ApprovalRecord/ApprovalStatus + 5 個 wrapper functions）直接沿用，僅補 `ReportRecord` + `listReports()`
- 驗證：tsc clean
- **Files changed** — `src/features/approval/Approval.tsx`

### DataImport 模板下載微調
- **Status**: DONE
- a)「模板下載」按鈕位置優化：與「選擇檔案」並排、改為 `type="link"` 次要按鈕（`DataImport.tsx`）
- b) 模板 CSV 改為多輸入、單輸出架構：5 輸入（input_temperature/voltage/pressure/speed/load）+ 單一輸出（output_thickness，移除 output_pressure）+ result
- i18n 三語 `dataImport.downloadTemplateDesc` 標示「多輸入、單輸出」
- 驗證：tsc clean、build 成功、三語 JSON 有效、無 output_pressure 殘留
- **Files changed** — `src/features/data-import/DataImport.tsx`, `src/i18n/en.json`, `src/i18n/zh-TW.json`, `src/i18n/es-MX.json`

### 專案儲存 ACL 修復（fs write_text_file not allowed by ACL）
- **Status**: DONE
- 使用者回報：儲存專案時報 `Command plugin:fs|write_text_file not allowed by ACL`
- **根因**：`src/lib/project.ts:48` `saveProjectFile` 呼叫 `writeTextFile`，但 `src-tauri/capabilities/default.json` 只授權 `fs:default`——Tauri 2 的 `fs:default` 僅允許**唯讀** app dirs + mkdir，寫入命令需在 ACL 明確授權；且目標路徑需在 scope 內
- **修復**：capability 追加 `{ "identifier": "fs:allow-write-text-file", "allow": [{ "path": "**" }] }`（grant write_text_file 命令 + 放行 save dialog 使用者選取路徑）
- **驗證**：`cargo check` pass（ACL regenerate 成功；僅既有 dead-code warning `EngineManager::stop`）
- **注意**：需重新 build + relaunch app 才會生效
- **Files changed** — `src-tauri/capabilities/default.json`

<!-- NEXT_ITEM_ANCHOR -->

- Monte Carlo 計算引擎核心 (`monte_carlo.py`) — sample_from_distribution, apply_anomalies, predict_output, run_monte_carlo
- 14 tests covering normal/gamma/lognormal/histogram sampling, linear/quadratic prediction, anomaly injection, full simulation with/without bounds
- 234 passed, 1 skipped (88% coverage)
- Monte Carlo IPC handler (`monte_carlo/run`) — main.py import + handler + dispatch
- 5 IPC handler tests (basic, unknown model, with anomalies, no bounds, unknown dataset)
- **品質檢查補強（commit pending）**：`quality.py` 新增 4 個原本只定義未執行的檢查——`invalid_format`（格式混用）、`unit_mixing`（單位混用）、`input_out_of_range`（超出工程範圍，支援 input_ranges 直用 + 中位數±8×MAD 統計啟發）、`missing_spec`（output 缺 LSL/USL）；`run_quality_checks` 新增可選參數 `input_columns`/`output_columns`/`input_ranges`/`spec`（不傳則略過或統計回退），`_handle_quality` 透傳。**前端**：DataImport 品質呼叫帶 input/output_columns（統計 OOR）；ProcessDefine「儲存並確認」後以確認的規格觸發「品質複查」（they trigger missing_spec 與用控制界限當 range 的 input_out_of_range），新增品質複查 Card+table+i18n 三語 9 keys。引擎測試 264 passed, 1 skipped；前端 tsc/build clean
- **120s time-out 根因（bug fix）**：`fit_random_forest` 無界 `max_depth`/`min_samples_leaf` 使大資料集樹的 leaf 數 ≈ n_train → shap `TreeExplainer` 隨資料量爆炸（實測 50k 列 SHAP **>200s**）。該呼叫在引擎**單一執行緒**迴圈（main.py:1728）同步執行，封鎖後續請求；Rust `engine_call` 120s timeout（commands/mod.rs:41）→ 使用者期間按的 `features/time_series` 逾時報「engine call timed out after 120s」。修復：`fitters.py`/`validation.py` RF 加 `max_depth=10, min_samples_leaf=5`；`shap_explainer.py` `compute_shap` 加 `max_explain=1000` 封頂實際解釋列數（`_explain_sample`），`main.py` 透傳。驗證：50k 端到端 shap 5.55s（vs >200s）；引擎 267 passed, 1 skipped
- **時間序列「計算特徵」轉圈根因（bug fix, commit pending）**：重啟後仍轉圈、分布/趨勢正常→Rust 集成測試 `time_series_returns_fast_live_engine` 決定性複現 `Timeout(10s)`；reader 加 logging 發現 `ENGINE_READER_PARSE_FAIL len=8939 err=expected value column 414`。根因：時間序列 `lag`/`roll_std` 前幾列 warm-up 產生 **NaN**，Python `json.dumps` 預設輸出**非標準 `NaN`**，Rust `serde_json::from_str` 拒收→`continue` 靜默 drop response→`recv_timeout` 逾時→前端一直轉圈（分布/趨勢資料無 NaN 故正常）。修復：`main.py` `_plain_types`（所有 handler 序列化 choke-point）把非有限浮點（NaN/±Inf）→ `null`（Rust 接受）。新增 Rust 集成測試作為迴歸保護。驗證：Rust 2 passed（含新測試 0.75s）、引擎 267 passed 1 skipped、tsc + build clean
- **時間序列結果表只顯示前 6 欄（commit pending）**：計算特徵後表格 `feature_columns.slice(0, 6)` 截斷，只剩 6/12 欄（`roll_mean_5/10`、`roll_std_5/10`、`drift` 等被隱藏）；user 對「分頁 page1/2 切換時欄位不變」感到困惑（其實跨分頁欄位本就不變，只是被截斷他以為有漏）。修復：移除 `slice(0,6)` 截斷，表格改為「時間欄 + 原始值欄 + 全部 feature_columns」，加 `scroll={{x:'max-content'}}` 橫向捲動與 `showSizeChanger:false`。驗證：tsc + build clean，user 確認表格顯示正常
- **時間序列圖特徵虛線跑掉/水平（commit pending）**：特徵 trace 用 `x: nonNull.map((_, i) => i)` —— filter 掉溫風期 NaN 後把 x 重新從 0 編號，導致每個特徵系列的實際 row 位置錯位、與基底資料不對齊（Lag/Delta/roll 對不同數量的前導 NaN 做不同位移），跑掉成水平錯線。修復：preserve 原始 row index——`preview.map((r,i)=>({i,v:r[feat]})).filter(v!=null)`，用 `p.i` 當 x，讓所有特徵與基底共用同一 row-index 軸。驗證：tsc + build clean
- **時間序列圖缺基底基準線 + 特徵線看似水平（commit pending）**：user 反映圖只看到 11 條水平虛線、且初始只有表沒圖（切 tab 後圖才出現）。根因：`compute_time_features` 的 `preview`（time_series.py `feature_cols`）**只含 time + 衍生特徵，不含基底 value 欄** → 前端圖的基底 trace `r[baseCol]` 全為 undefined → 實線基底線整個消失，只剩 11 條特徵虛線；而特徵（delta/roll_std 等）數值皆圍繞 ~1.61 且變化極小（span ~0.005）→ 同一 y 軸下天然幾乎水平。修復：`preview_df = feature_df.join(result_df[value_columns])` 把原始 value 欄加回回傳列（`feature_columns`/`n_features` 刻意維持衍生-only、不計基底欄）→ 圖能畫實線基底線做參考。驗證：preview 含基底欄（`output_thickness`=1.6102）、n_features 仍是 11、Rust 迴歸測試 0.77s pass、引擎 267 passed 1 skipped
- **Data Asset Management 獨立 tab（規格 §11A，MVP）**：新增 `src/features/data-assets/DataAssets.tsx`——列出 `data/datasets` in-memory registry 已匯入資料集（來源檔/格式/編碼/列數/欄數），每筆可 expand 顯示 `data/detect_fields` 欄位角色 Tag（reason tooltip）+ 備註/標籤 Input（存 `localStorage` key `dataAssets.notes.v1`，以 dataset_id 索引）。純前端、無引擎變更；`engine.ts` 新增 `DataAsset` interface + `getDataAssets()`（避免與既有 `getDatasets()`──走持久化 `project/datasets`──命名衝突）；`assistantGuide.ts` 加 `dataAssets` guide；types/App/Sidebar 路由整合；i18n 三語 `nav.dataAssets` + `dataAssets.*`。驗證：三語 JSON 有效、tsc --noEmit clean、npm run build 成功
- **Copula 獨立 tab + 修補缺失的 IPC handler（commit pending）**：`copula/joint` 的 dispatch（main.py:1286）參照 `_handle_copula_joint` 但該函式**從未定義**（latent NameError）→ backend 補 `_handle_copula_joint`（anomalies/correlation_matrix/direct_joints/seed/n_samples → `compute_joint_probabilities` → `_plain_types`）；`test_main_handlers.py` 新增 7 個 copula/joint 測試。**前端**新 `src/features/copula/Copula.tsx`——多選異常（`dataPipelineStore.anomalyScenarios`）、三 mode（independent/gaussian_copula/direct）、gaussian 相關矩陣編輯（對角=1 對稱）、direct 成對聯合機率輸入、n_samples/seed、結果 marginal 卡片 + 成對表格（joint/獨立期許值/相關性指數）+ fallback warning；`engine.ts` `CopulaParams` 補 `n_samples`；types/App/Sidebar（`DotChartOutlined`，monteCarlo 後）+ `assistantGuide` copula guide；i18n 三語 `nav.copula` + copula UI keys 11 支。驗證：引擎 **273 passed, 1 skipped**、三語 JSON 有效、tsc --noEmit clean、npm run build 成功

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

### Phase 10f — Interactive Prediction 滑桿修復 (bug fix)
- *根因*：`importer.py` 的 `to_dto()` 只輸出 `numeric/non_null_count/unique_count`，未輸出 `mean/std/min/max` → 前端拿不到真實統計，滑桿範圍計算失效（離群資料下變成天文數字，bar/藍點卡住不動）
- *修復*：`to_dto()` 補上 `mean/std/min/max` 欄位（dataclass 與計算原已存在，僅漏輸出）
- *Prediction.tsx*：滑桿範圍改用 `mean ± 3σ`（而非資料原始 min/max，避免離群污染）+ spread cap 防護；棄用原生 `<input type=range>` / antd Slider（WKWebView 拖曳支援差），改為自訂 pointer-capture `DraggableSlider`（無 useEffect window-listener 競態）
- *其他*：移除重複 listModels useEffect；DataImport Table 移除 deprecated index-based rowKey
- 引擎測試 250 passed; tsc/build clean
- **實機驗證：滑桿拖曳正常、數值合理 ✅**

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

### Process Flow Editor — Task 4: World/Viewport Transform + Pan/Zoom + fitView (bug fix)
- **Bug 根因**：`computeLayout` 以 (0,0) 為中心，兩未連接節點同層時 `startY=-V_GAP/2` 產生負 y 座標，SVG viewport 從 (0,0) 起 → 負座標節點被裁出畫面，且無拖曳/平移可恢復
- **修復**：改為「世界座標」(各節點 `x`/`y` 欄位) + viewport transform `<g transform="translate(pan) scale(zoom)">`
- **新增**：pan（拖背景）/ zoom（滾輪，0.5–2）+ `fitView()` 初次載入時讓所有節點（含負座標）可見；不重新佈局
- **保留**：`computeLayout` 定義（export 以滿足 noUnusedLocals，供後續 auto-layout 重用）但不再用於渲染；節點位置改由 `node.x ?? 0` / `node.y ?? 0`
- **節點/port 新增 data 屬性**：`data-node`（群組）、`data-node-id` + `data-port="out"/"in"`（兩個圓點）；port 拖曳連接留待後續任務
- **移除**：未使用的 `toWorld` helper（tsc noUnusedLocals 會報錯）
- 驗證 — tsc --noEmit clean、npm run build 成功

### Process Flow Editor — Task 5: Draggable nodes + position persistence (commit 9a8b5a3)
- **新增**：拖曳節點（pointer-capture on `<g>` `onPointerDown` → `startNodeDrag`），move 時以 screen delta / zoom 更新 nodes x/y
- **持久化**：`pointerUp` 時 `updateProcessNode` 儲存位置；失敗 rollback 回原位 + `messageApi.error('Failed to save position')`（i18n 留待後續任務）
- **保留**：節點自訂 `data-node` + `handleBackgroundPointerDown` 對 `[data-node]` 跳過 pan → 背景 pan 與節點 drag 不衝突
- **移除**：`toWorld`/`svgRectLeft`/`svgRectTop`（drag 直接用 clientX 差分，未使用，避免 noUnusedLocals）
- 驗證 — tsc --noEmit clean、npm run build 成功

### Process Flow Editor — Task 6: Zoom controls, auto-layout button, minimap overlay (commit a00ba5b)
- **Zoom 控制列**：+/- 按鈕（×1.25/×0.8，範圍 0.5–2）、百分比顯示（點擊重置為 100%）、Fit View 按鈕（FullscreenOutlined）
- **Auto Layout 按鈕**：呼叫 `computeLayout` 重新佈局 → 更新 nodes x/y → 持久化 → fitView 對齊
- **Minimap**：SVG 右下角 140×96px，節點以 `NODE_COLORS` 色塊顯示，藍色框顯示當前 viewport 可見區域（worldVisible origin/size 計算）
- **新增 import**：ZoomInOutlined, ZoomOutOutlined, FullscreenOutlined, ApartmentOutlined
- **i18n keys**：`processFlow.zoomFit` / `processFlow.autoLayout`（尚未加入翻譯檔，顯示 raw key）
- 驗證 — tsc --noEmit clean、npm run build 成功

### Process Flow Editor — Task 7: Drag from port to connect nodes (commit 6eadc55)
- **Port 連接拖曳**：`onPointerDown` 在 OUT/IN port 圓點啟動 `startConnect`，記錄來源節點 + world 座標
- **連接草稿**：`connectDraft` + `connectCursor` 狀態追蹤拖曳中的臨時連線
- **hover 偵測**：`handlePointerMove` 中透過 `document.elementFromPoint` + `[data-port]` 命中測試偵測目標 port，`hoverTarget` 狀態
- **提交/取消**：`handlePointerUp` 中若 `hoverTarget` 存在且非自身 → `handleConnect` 建立邊；否則取消
- **臨時虛線**：拖曳中渲染 dashed blue bezier（`svga` + `strokeDasharray="4 2"`）
- **座標轉換**：新增 `clientToWorld` helper（screen → world via svgRef.getBoundingClientRect + pan/zoom）
- **port 圓點屬性**：僅保留 valued form `data-port="out"` / `data-port="in"`（無重複 bare `data-port`）
- 驗證 — tsc --noEmit clean、npm run build 成功

---
**專案總體**：
- **代碼行數**：~15,100 行
- **Commits**：220+
- **測試**：255 passed, 1 skipped（70% coverage）
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

### Phase 11j — 完整 14 項規格報告（§17.2）
- **ReportData 擴充**：time_range/spec/distribution_fits/anomalies/monte_carlo/credibility/process_window 等欄位
- **handler 組裝**：`_handle_report_generate` 防禦式組裝 14 項 + `_spec_serializable`/`_proposed_process_window` 輔助
- **best_model 回退**：無 validated/approved 時退而取第一個模型
- **HTMLReportGenerator 重寫**：渲染全部 14 項（severity badge / 防注入 / percentile / 異常貢獻排名）
- **前端**：`ReportParams` + `Report.tsx` 傳入 spec/lsl/usl/蒙地卡羅參數
- 驗證 — 250 passed, 1 skipped (70% coverage), tsc/build clean, smoke 渲染 11 section（commit a565cc9）

### Process Flow Editor — Task 8: Node data mapping panel (規格 §11A) (commit c8240c5)
- **資料映射區塊**：屬性面板「Connect to」之前加入，5 個 selects：
  - `input_data_sources` / `output_data_sources`：`Select mode="multiple"`，options 來自已註冊資料集（`getDatasets()`）
  - `in_control_parameters` / `out_quality_outputs` / `machine_mapping`：`Select mode="tags"`（自由輸入）
- **saveMapping**：`updateProcessNode(id, { [field]: vals })` 持久化 + optimistic graph 更新；失敗 `messageApi.error`
- **驗證** — tsc --noEmit clean、npm run build 成功（spec reviewer 逐行核對 5 selects + persist 正確）

### Process Flow Editor — Task 9: i18n 三語 keys (commit 2335b58)
- **en / zh-TW / es-MX** 三語新增 16 keys：autoLayout / autoLayoutDone / autoLayoutError / saveError / dataMapping / inputDataSources / outputDataSources / selectDataSources / controlParameters / qualityOutputs / machineMapping / typeOrSelect / zoomIn / zoomOut / zoomReset / zoomFit
- **移除 raw key 顯示**：Task 6/8 新增但尚未本地化的 keys 現在全部有翻譯
- **es-MX 補齊**：發現 es-MX 原本**完全缺少整個 `processFlow` 區塊**（前幾次 commit 未同步）→ 依 en/zh-TW 補齊完整 processFlow（既有 31 keys + 新 16 keys 全翻譯），與其他語系一致
- **驗證** — 三檔 JSON 有效、程式化檢查所有 `t('processFlow.*')` 引用 keys 三語皆存在、tsc --noEmit clean

### Process Flow Editor — Task 10: 最終整合驗證 (全部完成)
- **引擎**：`cd engine && .venv/bin/python -m pytest tests/ -q` → **255 passed, 1 skipped**
- **前端**：`npx tsc --noEmit` clean + `npm run build` 成功（chunk 大小警告為既有，非本次造成）
- **全部 10 Tasks commit 至 main**：5706bef(T1) fcaa2b5(T2) f465f0e(T3) 531a59a(T4) 9a8b5a3(T5) a00ba5b(T6) 6eadc55(T7) c8240c5(T8) 2335b58(T9)

### AI 助手「思考中」動畫未顯示 (bug fix)
- **根因（Console 證據確認）**：加入 `console.log` 診斷後確認 `handleSend` 正常執行、`loading=true` 確實多次 re-render、`aiChat` **即時 resolve**（`success: true`，本機 Ollama 毫秒級回應）→ 狀態機與渲染皆正常，問題純粹是「回應太快，loading true 的視覺期間太短，使用者感知不到」
- **修復 1**：loading 指示器由「訊息串底部的 bubble」改為**面板頂部固定綠色橫幅 banner**（`padding/borderBottom/background #ecfdf5` + Spin + 粗體綠字），不依賴訊息串 scroll 位置
- **修復 2**：`finally` 內最小顯示時間由 400ms 提高到 **900ms**，即使即時回應也保證使用者清楚地看到「思考中」橫幅
- **診斷**：以常駐 DOM 的 `DEBUG-STRIP-A` 橘色條驗證 —— user 確認**橘條與綠條均正常渲染**，證明面板該位置渲染無礙；**實機驗證：送出訊息時頂部綠色「思考中」橫幅正常出現 ✅**
- **最終定案（真正根因）**：user 觀察確認「AI 回答瞬間一次顯示，綠條出現時間過短」→ 因本機 AI 即時回應，`loading` 期間幾乎為零。**修復**：`handleSend` 改為「先讓「思考中」橫幅顯示滿 `MIN_THINK_MS=800ms`，才把 assistant 回覆 append 進訊息串」→ 產生可感知的「思考中 → 回答」順序（即使 AI 毫秒級回應）。`finally` 只負責等待剩餘時間，回覆真正 commit 改到等待之後
- **清理**：移除 DEBUG 橘條、`loadingBarRef` 與 `showLoadingBar` 命令式切換（與 `loading` 驅動的 inline style 衝突），回歸純 `{loading && banner}` + 800ms 最小思考顯示
- 驗證 — tsc --noEmit clean、npm run build 成功

### Cloud Upload de-identification strategy_overrides (Task 3 — IPC wiring)
- **Status**: DONE
- **Scope** — `_handle_cloud_preview` and `_handle_cloud_upload` in `main.py` now extract `strategy_overrides = params.get("strategy_overrides", {})` and pass it via keyword args to `generate_upload_preview`
- **Tests** — 2 new: `test_handle_cloud_preview_passes_strategy_overrides` (verifies noise_config entry for a noise override), `test_handle_cloud_preview_and_upload_consistent` (verifies hash override + upload record)
- **Full suite** — 280 passed, 1 skipped
- **Commit** — `dd76028`
- **Files changed** — `engine/src/process_intelligence_engine/main.py`, `engine/tests/test_main_handlers.py`

### Cloud Upload de-identification strategy_overrides (Task 1)
- **Status**: DONE_WITH_CONCERNS
- **deidentify.py** — `generate_preview` 新增 `strategy_overrides: dict[str, str] | None = None` 參數，支援 per-column masking 策略覆蓋（hash / masked / noise）
- **Bug fix** — 修正上傳 hash 計算中 `upload_data[col]` → `df[col]`（masked 欄位不在 transmitted 中，原碼 KeyError）
- **噪聲配置** — noise_std>0 時 transmitted 數值欄自動加噪，`strategy_overrides={"col":"noise"}` 亦可主動啟用
- **測試** — `test_deidentify.py` 4 個案例：2 passed（noise/噪聲忽略），2 failed（hash/masked 輸出）因 `apply_masking` 只含 `transmitted_columns`，masked 欄位未列入輸出 DataFrame → Task 2 需修正
- **全量** — 275 passed, 2 failed（新測試 apply_masking 限制）, 1 skipped（既有）
- **Commit** — `4fc6fd6`
- **Files changed** — `engine/src/process_intelligence_engine/data/deidentify.py`, `engine/tests/test_deidentify.py`

### Settings cloud upload strategy default fix + history population (commit 5aae6ec)
- **Issue 1 (strategy mismatch)** — `loadCloudFields` initialized non-sensitive fields with strategy `'masked'`, but UI `?? 'hash'` fallback displayed `'hash'`. Fix: changed line 77 `strat[f.name] = 'hash'` (was `isSensitive ? 'hash' : 'masked'`) so stored value matches UI display when field is reclassified transmit→mask.
- **Issue 2 (cloudHistory)** — Already correctly implemented (lines 640-641: `const records = await listCloudUploadRecords(); setCloudHistory(records.records)`). No change needed.
- **Verification** — `npx tsc --noEmit` clean, `npm run build` success (built in 10.06s)

- **Cloud Upload 去識別化設定改進（規格 §11A/§24）— DONE + 已驗證**：Settings → Cloud Upload 卡片可選擇真實資料集並逐欄設定遮蔽策略。**Backend**：`deidentify.py` `strategy_overrides`（`{col:"hash"|"masked"|"noise"}`，優先於 dtype 自動判定，`noise` 僅數值欄）+ `apply_masking` 輸出含遮蔽欄並依策略正確遮蔽（避免數值敏感欄洩漏）；`main.py` `cloud/preview`/`cloud/upload` 透傳。**Tests**：`test_deidentify.py` 5 個 + `test_main_handlers.py` 2 個；引擎 **280 passed, 1 skipped**。**Frontend**：`engine.ts` params 加 `strategy_overrides`；Settings 新增資料集下拉（取代 `demo_dataset`）+ 逐欄分類/策略表格（`detectFields([], id)` 取欄位）+ `deriveColumns()`；i18n 三語 13 keys（es-MX 補齊整個 cloud section）。驗證：tsc --noEmit clean、npm run build 成功、三語 JSON 有效。**Commits**：`4fc6fd6`、`592ded9`、`dd76028`、`d5fb16d`、`5aae6ec`。

### Approval tab — Task 3: Frontend Approval.tsx review UI component
- **Status**: DONE
- **Component** — `src/features/approval/Approval.tsx` (387 lines)
  - On mount: `getCurrentUser()` (role), `listUsers()` (reviewers), `load()` fetches models/reports/records
  - Resource table: models + reports merged, columns: Type, Resource(label), Status(Tag), Action
  - Status resolution: `getApprovalStatus()` per resource, overridden by latest record action
  - Action column: Approve/Reject buttons if `pending_review && canReview` (admin||engineer); muted text if pending && !canReview
  - Submit modal: type selector, resource dropdown, reviewer dropdown, comments textarea → `submitForReview()`
  - Approve/Reject modal: Alert label + comments textarea → `approveResource()`/`rejectResource()` with current user identity
  - Records card: full audit table (time/type/resource/action/reviewer/comments)
- **Reviewer identity** — `canReview = currentRole === 'admin' || currentRole === 'engineer'` (engine.ts UserRole has no 'reviewer'; 'engineer' is the review-capable role)
- **tsc** — clean (no errors)
- **Commit** — `9e01b00`
- **Files changed** — `src/features/approval/Approval.tsx`

## In Progress / Next
### Cloud Upload de-identification — Tasks 4 & 5: engine types + UI dataset selection + per-column masking strategy
- **Status**: DONE
- **engine.ts** — Added `strategy_overrides?: Record<string, string>` to both `CloudPreviewParams` and `CloudUploadParams`
- **Settings.tsx** — Dataset selector (`Select` from `getDataAssets`), per-column `Table` with classification (transmit/mask/exclude) and masking strategy (hash/masked/noise) selects; `deriveColumns()` helper computes sensitive/excluded/overrides for both preview and confirm calls; Preview button disabled until dataset selected; hardcoded `demo_dataset` replaced with `cloudDatasetId`
- **i18n** — 13 new keys in `cloud` section across en/zh-TW/es-MX (`dataset`, `selectDataset`, `field`, `dataType`, `classification`, `strategy`, `transmit`, `mask`, `exclude`, `strategyHash`, `strategyMasked`, `strategyNoise`, `noDataset`); es-MX cloud section was missing entirely, added full cloud section
- **Verification** — `npx tsc --noEmit` clean, `npm run build` success, JSON parse 3 locales ok
- **Commit** — `d5fb16d`
- **Files changed** — `src/lib/engine.ts`, `src/features/settings/Settings.tsx`, `src/i18n/en.json`, `src/i18n/zh-TW.json`, `src/i18n/es-MX.json`
### 探索分析「時間序列」時間欄位無法選取 (bug fix)
- **根因**：`Exploration.tsx` 時間欄位 `<Select>` 的 `options` 邏輯**顛倒**——`numericColumns.length > 0 ? [] : 全部欄位`。若資料集有數值欄（幾乎必有）→ 下拉**全空** → `timeColumn` 永遠無法選取 →「時間序列」按鈕 disabled。`timeColumn` 初始亦為 `undefined` 且從不自動選。
- **後端無需改**：`compute_time_features`（time_series.py:35）對任何傳入欄位做 `pd.to_datetime` 再 sort，不要求 `timestamp` role。
- **修復**：新增 `timestampColumns` memo——優先取 fields 中 `role==='timestamp'` 的欄位，否則回退到「非數值欄」；`<Select>` options 改用 `timestampColumns`；新增 useEffect 於資料載入時自動選第一個時間欄位。tsc --noEmit clean、npm run build 成功

### 時間序列「計算特徵」失敗/卡住 (bug fix)
- **根因**：`features/time_series.py` drift 計算無條件引用 `roll_mean_5`（line 57），但 rolling window 只在 `w <= len(series)` 時才建立。當資料列數 < 5（`window_sizes` 含 5）→ `roll_mean_5` 不存在 → `KeyError`；實測 rows=3、4 拋 KeyError，rows≥5 正常 0.001s 完成。
- **後端已驗證**：in-process 直呼 `_handle_time_series` 對各種列數**皆快速回應**（成功或立即錯誤），Rust bridge 對 error 會 reject → 前端 `finally` 應停止轉圈；故主要缺陷為 drift KeyError。
- **修復**：drift 改用「實際已建立的最大 window」（`max(w for w in window_sizes if roll_mean_w in feature_cols)`），無可用 window 時回退 0-drift，不再硬編碼 `roll_mean_5`。
- **新增**：`tests/test_time_series.py` 3 個案例（全 window / <5 列不拋錯 / 部分 window 用最大可 fit 者）。引擎 267 passed, 1 skipped

### 時間序列「數值欄位」預設為非數值 → 報錯無輸出 (bug fix)
- **根因**：`Exploration.tsx` 的 `tsColumn`/`trendColumn` 預設都初始為 `spec?.outputField`。范術語 CSV 範本的 output 可能是非數值欄（如 `result` pass/fail）→ `compute_time_features` 對非數值欄 `astype(float)` 拋錯 → 前端出現紅色錯誤 Alert、無輸出。
- **修復**：新增 useEffect 確保 `tsColumn`/`trendColumn` 落在 `numericColumns`（否則自動改為第一個數值欄）；按鈕 handler 加守衛——`tsColumn` 非數值時顯示明確訊息 `exploration.valueColNotNumeric` 而不呼叫後端。
- **i18n 三語**：`exploration.valueColNotNumeric`（en/zh-TW/es-MX）。
- 驗證：三語 JSON 有效、tsc --noEmit clean、npm run build 成功
- **CSV 範本下載 + 明確分類 input/output（DataImport）**：`DataImport.tsx` 之 `buildTemplateCsv()`（3 operator × 5 part × 3 reps = 45 列，欄位：lot/serial_no/datetime/machine/operator/part/**input_temperature/input_voltage/output_thickness/output_pressure**/result）+ `handleDownloadTemplate()`（Blob + a.download）；匯入來源卡片「無檔」狀態新增「下載 CSV 範本」按鈕（含 Tooltip）；i18n 三語 `downloadTemplate`/`downloadTemplateDesc`。**前綴分類**：欄位名加 `input_`/`output_` 前綴清楚標示角色，引擎實測 `output_*` → output(0.85)、`input_*` → input(0.7)，證實「輸出不限良率、可為其它物理量」。**強制輸出欄位**：`handleConfirmAll`/`handleFinish(next)` 驗證 fields 至少一個 role=output，否則 `message.error`（i18n `dataImport.errNoOutput`）阻擋並提示；input 保留自動偵測+手動可改。涵蓋 分佈/趨勢/時間序列/GRR。tsc/build clean
- **跨平台 Release CI（commit 1e5c5c2 + tag v0.1.0）**：新增 `.github/workflows/release.yml`（tauri-action）—— tag push `v*` 或手動 dispatch 觸發，4 個 matrix job 平行建置：macOS aarch64 / macOS x86_64 / ubuntu-22.04 / windows-latest；產出附到 GitHub Release（draft、`.msi`/`.exe`、`.dmg`、`.AppImage`/`.deb`）；`.gitignore` 新增 `release/`。**狀態：push 成功、tag v0.1.0 已推送，Actions「release」run in_progress（Windows 版由此自動產出）**
- **macOS 本機 dmg**：`npm run tauri build` 成功產出 `.app`，但內建 create-dmg 之 Finder/AppleScript 美化步驟失敗；改用 `hdiutil create` 直接產乾淨 `.dmg`：`release/Process-Intelligence-Platform_0.1.0_aarch64.dmg`（arm64、8.9MB、含拖到 Applications 標準安裝版）
- **AI 助手對話區捲動 + 常駐捲軸**：Sider 設 `height:100vh + overflow:hidden`（對齊螢幕高度）；訊息區 `flex:1, minHeight:0, maxHeight:calc(100vh - 118px), overflowY:auto`（硬性高度上限，內容超過即出現捲軸，可上拉看舊對話、自動置底顯示最新）；`global.css` 新增 `.assistant-messages::-webkit-scrollbar` 強制顯示 8px 灰捲軸（macOS overlay scrollbar 預設隱藏）。**實機驗證：訊息超過一屏即出現灰捲軸 ✅**
- **AI 助手依導航上下文回答（spec §7.3 / §16.1）**：新增 `src/lib/assistantGuide.ts`（`buildAssistantSystemPrompt(activeTab)` + 12 個 tab 的精準使用/圖表說明：名稱、用途、操作步驟、關鍵圖表判讀、權限邊界）；`AssistantPanel` 接收 `activeTab` prop，每次送訊時在 payload 前端插入 `role:'system'` 系統提示（當前頁面說明 + 整體工作流程 + 建議式回答準則）；`App.tsx` 傳入 `activeTab`。tsc/build clean
- **AI 回答語言對應介面語言**：`buildAssistantSystemPrompt(activeTab, language)` 新增語言指令 —— `zh*`→繁體中文、`es*`→西班牙文、其餘→英文；`AssistantPanel` 以 `i18n.language` 帶入每次送訊的 system 提示。tsc/build clean
- **AI 助手移除 Enter 送出 + 清除對話按鈕**：移除 Input `onPressEnter`（避免誤送，僅可點 Send）；標題列新增 `ClearOutlined` + `Popconfirm` 清除對話（i18n 三語 `assistant.clear`/`clearConfirm`）；loading 中停用。tsc/build clean
- **AI 解讀目前頁面真實數據/圖表（spec §16.1「解釋目前頁面與圖表」）**：
  - 新增 `src/stores/assistantContextStore.ts`：Zustand store，`context: Record<AppTab,string>` + `setContext(tab, summary)`
  - 新增 `src/lib/assistantData.ts`：各頁面數據摘要 builder（DataImport 欄位/規格、Exploration 分布/趨勢/時序/GRR、ModelCenter 交互/SHAP/外插/CV/完整驗證、SPC 控制圖/能力指數、MonteCarlo NG機率/百分位/異常排名、Prediction 輸入與預測值、Validation 模型比較/實驗通過率、Reports 是否產生）
  - 8 個 feature 頁面各自呼叫 `setContext(tab, buildXxxContext(...))`，把當下實際結果寫入共享 store
  - `buildAssistantSystemPrompt(activeTab, language, dataContext?)`：該頁有真實數據時追加 `CURRENT PAGE DATA`，指示 AI 解讀實際數值、指出健康/風險、給具體下一步（而非只列功能）
  - `AssistantPanel` 讀取 `context[activeTab]` 併入每次送的 system 提示
  - 驗證 — tsc --noEmit clean、npm run build 成功
- **待使用者手動 E2E（`npm run dev`）**：切到有數據的頁面（如 SPC/MonteCarlo 跑完）問 AI「解讀這個結果」，確認用真實數據判讀；AI 回答語言對應介面語言（en/zh-TW/es-MX）；拖曳節點 → 位置持久化；port 拖曳連線；縮放/自動佈局/minimap；資料映射編輯後重載保持 —— 自動化驗證（255 passed / tsc / build）已全數通過，僅剩互動式畫布之人工確認
- **進度註記**：原 TASK.md 標註「250 passed」實際為引擎舊計數，本次 255 passed（含新增 manifest 節點測試）

### Process Flow Editor — 響應式全視窗佈局 (commit baffe58)
- **根容器**：`<Space>` 改為 flex column，`height: calc(100vh - 48px)`（對應 Content padding 24×2）→ 填滿中央區域高度
- **Diagram Card**：`flex:1 + display:flex column`，body `flex:1`；畫布 container 由固定 `height:500` 改為 `flex:1` → ResizeObserver 自動依可用高度縮放 SVG（畫布填滿剩餘空間）
- **Properties Card**：`height:100% + display:flex column`，body `flex:1 + overflow:auto` → 屬性面板填滿高度、內容過長可捲動
- 驗證 — tsc --noEmit clean、npm run build 成功

### Process Flow Editor — 灰色繪圖區填滿視窗 (commit 32e9e93)
- **根因**：`<svg>` 用顯式像素 `width={viewportSize.w} / height={viewportSize.h}` 指定尺寸，若 ResizeObserver 量到偏小值（flex 高度未完全解析時），灰色繪圖區就比卡片小
- **修復**：SVG 改為 CSS `width:100%; height:100%` 填滿 container（container 為 `flex:1` 填滿 card body）→ 灰色繪圖區必定覆蓋整個 Diagram 卡片；`viewportSize` 仍由 ResizeObserver 量測供 pan/zoom/minimap 數學使用
- 驗證 — tsc --noEmit clean、npm run build 成功

### Process Flow Editor — 連線拖曳修正 + minimap 角落校正 (commit 9b77d6d)
- **連線無法連上（主要 bug）**：port 圓點有 `onPointerUp={(e)=>e.stopPropagation()}`，而 `startConnect` 把 pointer 捕獲到來源 port 圓點 → pointerup 冒泡到來源圓點即被 stopPropagation 擋住，SVG 上層 `handlePointerUp`（負責提交/取消連線）永遠收不到 → 連線永不建立。**修復**：移除兩個 port 的 `onPointerUp` stopPropagation
- **連線目標太難命中**：原 hover 只認 5px 的 port 圓點，極難精準。**修復**：`elementFromPoint` 同時接受整個目標節點 `[data-node]`（fallback），落在節點本體即可連到該節點；並新增綠色高亮框提示連接目標
- **minimap 不在角落**：minimap `translate` 用 `viewportSize`，若量測偏小則不到角落。**修復**：改用實際 SVG 尺寸 `svgRef.getBoundingClientRect()`（回退 viewportSize）定位 → 貼齊真實右下角
- 驗證 — tsc --noEmit clean、npm run build 成功

### 規格符合度稽核 (research-only, no code changes)
- 對象：main spec `2026-09-02-ai-process-risk-platform-design.md`（§4/§6/§10-18/§20-22）+ 四個 sub-spec。
- 完成稽核檔案：App.tsx、Sidebar.tsx、types/index.ts、lib/engine.ts、lib/project.ts、AssistantPanel.tsx、engine main.py 全部 handler、spc.py、reporting/{models,base,html,pdf,excel,charting}.py、data/quality.py、project/manifest.py。
- 結論：Phase 0–11j 全數達成；但存在「backend-only」未接 UI 的功能（approval/copula 前端未呼叫）、data asset management 無獨立 tab、quality 4 檢查內建常量未執行、SPC X-bar 需使用者人工確認。
- 詳見完整稽核報告（IMPLEMENTED / PARTIAL / NOT-DONE per feature）。
