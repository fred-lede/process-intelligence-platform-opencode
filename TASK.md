# TASK.md

## Completed
### SPC 管制線圖例 + MC σ 精度/guard 修復（commit 1d2cb57）
- **Status**: DONE
- **SPC 圖例**：移除所有管制線 `showlegend: false`（UCL/LCL/CL/MR UCL+CL/R UCL+CL/S UCL+CL 共 12 處）→ 圖例可見橘虛=UCL/LCL、綠虛=CL、紫實=MR/R/S、紅實=LSL/USL；違規點仍 `showlegend:false` 不佔圖例
- **MC σ 精度**：`.toFixed(3)` → `.toFixed(2)` 與 Pp/Ppk `precision={2}` 對齊
- **MC guard**：`assistantData.ts` context guard 補 `sigma_overall != null` 與 UI 卡對稱（UI 卡 earlier 已由 implementer 加上）
- **Files changed** — `src/features/spc/SPC.tsx`, `src/features/monte-carlo/MonteCarlo.tsx`, `src/lib/assistantData.ts`

### Task 3 — 收尾 docs + 最終驗證 + push（MC predicted capability）
- **Status**: DONE
- **引擎（commit `bb1b019`）**：`run_monte_carlo` 回傳新增 `capability`（reuse `spc.compute_capability`，`subgroup_size=1` → σ within = overall σ → pp/ppk 整體 σ 語意；spec LSL+USL 未同時設定時 pp/ppk None）；2 新測試 → engine **306 passed, 1 skipped**
- **前端（commit `27eb722`）**：MonteCarlo 頁「預測能力指數（模擬）」card（Pp/Ppk antd Statistic + σ overall，≥1.33 綠 / ≥1.0 橘 / <1.0 紅 mirror SPC）；AI context `Predicted capability (simulation)` 一行；i18n 三語 +4 keys
- **驗證**：`npx tsc --noEmit` EXIT 0、`npm run build` 成功、三語 parity `ok`、`git status` 僅含預期 docs（未含 `engine/.coverage`/icons）
- **Files changed** — `engine/src/process_intelligence_engine/monte_carlo.py`, `engine/tests/test_main_monte_carlo.py`, `src/lib/engine.ts`, `src/features/monte-carlo/MonteCarlo.tsx`, `src/lib/assistantData.ts`, `src/i18n/*.json`（×3）, `PROGRESS.md`, `README.md`, `TASK.md`（docs commit）

### Code review — MC predicted capability 前端（Task 2, commit 27eb722）
- **Status**: DONE — **APPROVE**（無 Critical/Important；3 Minor 皆 polish，不 blocking）
- **審查範圍**：`git diff bb1b019..27eb722`（6 files, +52/−4）——MonteCarlo.tsx card+capColor、engine.ts capability field、assistantData.ts context line、i18n 三語 4 keys
- **驗證重點**：`capColor`（MonteCarlo.tsx:121）+Photo與 SPC `capacityColor`（SPC.tsx:124-129）閾值與 hex 完全一致（≥1.33 綠/≥1.0 橘/<1.0 紅）；card 布局沿用 `Card size="small"`+`Row gutter={16}`+Col 6/6/12；AI context line 格式與 `buildSpcContext`/既有 MC lines 一致（num()、label:value.）；i18n 4 keys 全被引用、僅 3 語系檔案、無孤兒 key；`Statistic` import 有使用；`capability?: SPCCapability | null` 防禦型別（後端可能未填）搭配 UI/context 雙重 null-guard，安全
- **Minor（non-blocking）**：(1) UI guard 要求 `pp/ppk/sigma_overall` 三值皆非空，但 context guard 只檢查 pp/ppk——sigma_overall=null 時 UI 藏卡而 context 輸出 `sigma_overall=N/A`（num() 已防，無害，建議對齊）；(2) `sigma_overall.toFixed(3)` vs Statistic `precision={2}` 與兄弟 cell `.toFixed(2)` 精度不一致（可能刻意）；(3) 新 card 用 left-aligned `Statistic` vs 上方 centered `Typography.Title` cells（接近 SPC Process Capability card 表達，可接受）
- **Files reviewed** — commit `27eb722`（src/lib/engine.ts, src/features/monte-carlo/MonteCarlo.tsx, src/lib/assistantData.ts, src/i18n/{en,zh-TW,es-MX}.json）

### Task 2 — MC predicted capability 前端（card + AI context + i18n）
- **Status**: DONE
- **實作**：`engine.ts` `MonteCarloResult` 新增 `capability?: SPCCapability | null`；`MonteCarlo.tsx` 加入 `Statistic` import、`capColor` helper（≥1.33 綠 / ≥1.0 橘 / <1.0 紅）、percentiles 與 outputDistribution 間插入 Predicted Capability card（Pp/Ppk Statistic + σ overall，guard 多含 `sigma_overall != null`——plan snippet 遺漏致 tsc 出錯，已延伸條件）；`assistantData.ts` `buildMonteCarloContext` 於 anomaly block 後補 predicted capability 一行；三語 i18n 新增 4 keys（monteCarlo 由 30→34）
- **驗證**：三語 parity `ok count: 34`；`npx tsc --noEmit` EXIT 0（初版 1 error TS18047 sigma_overall nullable → guard 修復）；`npm run build` `✓ built in 10.78s`（chunk 警示既存）
- **Files changed（commit 27eb722）** — `src/lib/engine.ts`, `src/features/monte-carlo/MonteCarlo.tsx`, `src/lib/assistantData.ts`, `src/i18n/en.json`, `src/i18n/zh-TW.json`, `src/i18n/es-MX.json`（未 commit `engine/.coverage`/icons；TASK.md 於此紀錄）

### Code review (2nd independent pass) — MC predicted capability (Task 1 of plan 2026-09-05-monte-carlo-predicted-capability, commit bb1b019)
- **Status**: DONE — **APPROVE**（1st entry: spec compliant；2nd pass 獨立驗證確認，無 Critical/Important）
- **Verified**：diff = 2 files, +43 lines（1 import + 1 dict entry + 2 tests）；`test_main_monte_carlo.py` **11 passed**；`compute_capability` with `subgroup_size=1` → `sigma_within = overall_std`（spc.py:54-57）→ pp/ppk 用 overall σ，語意正確；無 circular import（spc.py 僅 import stdlib+numpy，monte_carlo→spc 單向）；**rel tolerance 實測 justified**——rounding 6dp 造成的 relative error 僅 ~1e-8（pp）/ ~6e-9（sigma）/ ~1e-7（ppk），遠低於 rel=1e-5（約 1000× margin）
- **Minor（non-blocking）**：(1) `capability.mean`/`sigma_overall` 被 6dp round 而 `output_mean`/`output_std` 為全精度，同畫面並排可能顯示不一致（實測 134.53323 vs 134.5332300402011）；(2) `compute_capability` 內部重算 mean/std（重複既有 output_mean/output_std，成本可忽略）；(3) one-sided spec（只有 lsl 或只有 usl）→ pp/ppk 靜默 None（spc.py:72,80 既有行為，非本 commit 引入）無測試涵蓋；(4) n_simulations=0 時 compute_capability raise ValueError——但 `_compute_boxplot` 在改動前對 empty 已會 raise，非新失敗模式（n=1 有 guard，overall_std=0 → pp/ppk None，safe）
- **備註**：`engine/.coverage`（unstaged）與 `src-tauri/icons/`（untracked）未入 commit
- **Files reviewed** — `engine/tests/test_main_monte_carlo.py`, `engine/src/process_intelligence_engine/monte_carlo.py`, `engine/src/process_intelligence_engine/spc.py`, commit `bb1b019`

### i-mr 補畫 MR 子圖（user 要求）
- **Status**: DONE
- **實作**：`SPC.tsx` i-mr 分支 violations 後新增 MR 子圖——紫 `#722ed1` lines+markers、`yaxis='y2'`、x 對齊 `i+1`；MR UCL（橘 dash）+ MR CL（綠 dash）條件式畫入（mirror R/S）；`plotLayout.yaxis2` 改為一律建立（移除非 i-mr 限制）。README 已宣稱 I-MR 故無需改
- **驗證**：`npx tsc --noEmit` clean；`npm run build` 成功
- **Files changed** — `src/features/spc/SPC.tsx`, `PROGRESS.md`, `TASK.md`

### SPC UCL/LCL 從未顯示 bug 修復（扁平 vs 巢狀 control_limits）
- **Status**: DONE
- **根因**：引擎 `compute_i_mr`/`compute_xbar_r`/`compute_xbar_s` 回傳巢狀 `control_limits`（`{'x': {ucl/lcl/cl}, 'mr'(或 r/s): {...}}`，spc.py:145/211/283），前端 `SPCCtrlLimits` 型別與 SPC.tsx/assistantData.ts 讀扁平 key（`x_ucl`/`i_ucl`/`i_center`…）→ 執行時全部 `undefined` → `cl.x_ucl != null` 恆 false → **UCL/LCL/CL 三條線自 Phase 8 起從未畫出**；AI context 同源「UCL=null」污染（assistantData.ts:149 `!== null` 對 undefined 為 true）
- **修法**：`engine.ts` `analyzeSPC` 加 `flattenControlLimits(res)`——依 chart_type 攤平巢狀 group（i-mr 時 `x→i_*`、否則 `x→x_*`；`mr`/`r`/`s`→對應 prefix），單一 choke point 同時修好 SPC.tsx + assistantData.ts。無引擎/i18n/測試變更
- **驗證**：`npx tsc --noEmit` clean；`npm run build` 成功
- **side note**：i-mr 目前只畫 Individuals 圖（`yaxis2` 僅非 i-mr 建立，SPC.tsx:254-256），MR 有計算未 render——獨立範圍缺口，待決
- **Files changed** — `src/lib/engine.ts`, `PROGRESS.md`, `TASK.md`

### SPC 規格線 — LSL/USL 參考線於位置圖（Individuals / X-bar），離散圖 MR/R/S 不加
- **Status**: DONE
- **實作**：`SPC.tsx` `buildPlotData` 新增 `addSpecLines(ref?)`（`spec.lsl`/`spec.usl` 各側獨立，僅畫已提供的側；縱跨首尾 x；黑實線 width1.5、與 UCL/LCL 橘 dash 樣式明顯區別）——i-mr 分支 `Individuals` 直畫（legend `LSL`/`USL`）、xbar-r / xbar-s 分支 `X-bar` 標記 `LSL (ref)`/`USL (ref)`（單件規格參考語意）；**MR / R / S 分支不動**。legend 名沿用既有 hardcode 慣例（無新 i18n key）
- **驗證**：`npx tsc --noEmit` clean；`npm run build` 成功（chunk 警示為既有）；無引擎變更（304 passed 維持）
- **Files changed** — `src/features/spc/SPC.tsx`, `README.md`, `PROGRESS.md`, `TASK.md`（未提交 `engine/.coverage`/icons）

### Task 10（final）— 引擎 zero-row filter 守衛 + SPC numeric guard + docs sweep + 最終驗證 + push
- **Status**: DONE
- **Part A（引擎，TDD）**：`main.py` 新增 module-level `_apply_row_filter(df, params)` helper（unknown column → KeyError、缺 filter_value → ValueError、`astype(str) == str(filter_value)` mask、**mask 後空 → `ValueError("No rows match filter")`**），取代 4 handler（`_handle_spc_analyze`/`_handle_monte_carlo_run`/`_handle_distribution`/`_handle_series`）重複 inline mask block 為單行 `df = _apply_row_filter(df, params)`；error 訊息字串與既有測試完全一致。新增 4 測試（spc/mc/distribution/series 各一，filter 值匹配 0 列 → ValueError match="No rows match filter"）——RED 4 failed → GREEN；full suite **304 passed, 1 skipped**（baseline 300 + 4）
- **Part B（前端）**：`SPC.tsx` mount effect `setColumn(pendingCtx.field)` 加 numeric guard——inline 依 `importResult?.stats.column_stats` 建 numeric set（不依賴 stale `numericColumns` state），非 numeric 保持 `column` 原樣（`spec?.outputField` default）；`npx tsc --noEmit` clean、build 成功
- **Part C（docs）**：plan 檔 append「Execution Notes (post-hoc)」段落（7 items）；PROGRESS.md append 2026-09-05 FAI entry；**新建 HANDOFF.md**（里程碑 handoff）；README 功能總覽補 FAI 一行（ProcessFlow association-keys + jump + per-node filter）
- **Part D（最終驗證）**：引擎 **304 passed, 1 skipped**；`npx tsc --noEmit` clean；`npm run build` 成功（chunk 警示為既有）；三語 `processFlow`/`spc`/`monteCarlo`/`exploration` parity `ok`；`git status` 僅含預期檔案（未含 `engine/.coverage`/icons）
- **Part E（commits + push）**：`eb134ba feat(engine): consistent row filter helper + zero-row guard` → `cf858ad fix(spc): numeric guard on jump field` → `9449b26 docs: plan execution notes, progress, handoff` → `b758980 docs: record Task 10 commit hashes + push result` → `git push` `6049214..b758980 main` ✅（未提交 `engine/.coverage`/icons）
- **Files changed** — `engine/src/process_intelligence_engine/main.py`, `engine/tests/test_main_spc.py`, `engine/tests/test_main_monte_carlo.py`, `engine/tests/test_main_handlers.py`, `src/features/spc/SPC.tsx`, `docs/superpowers/plans/2026-09-05-process-flow-analysis-integration.md`, `PROGRESS.md`, `HANDOFF.md`(new), `README.md`, `TASK.md`（未提交 `engine/.coverage`/icons）

### Code review fixes — SPC source tag interpolation + exploration filter scoping
- **Status**: DONE
- **Fix 1**：`spc.sourceFromNode` 三語單括號 `{name}` → `{{name}}`（en/zh-TW/es-MX，既已確認其他 key 僅探索/MC 用既有 `{{name}}`，spc 為唯一缺口）
- **Fix 2**：`NodeSourceFilter.tsx` 新增 optional `filterable?: boolean`（default true）；`false` 時保留 source Tag + dataSourceNotLoaded Alert、隱藏 filter 控制（column Select / value Input / clear Button）。`Exploration.tsx` 新增 `activeTab` state + 受控 `<Tabs activeKey/onChange>`，傳 `filterable={activeTab === 'distribution' || activeTab === 'trend'}` → TimeSeries/GRR 頁不再顯示會誤導的篩選控制（distribution/trend 確實套用 filter，TS/GRR 不套用）
- **驗證**：`npx tsc --noEmit` EXIT 0；三語 spc(33)/monteCarlo(30)/exploration(30) parity `ok`、無單括號 `{name}` 殘留；`npm run build` 成功
- **Files changed** — `src/components/NodeSourceFilter.tsx`、`src/features/exploration/Exploration.tsx`、`src/i18n/en.json`、`src/i18n/zh-TW.json`、`src/i18n/es-MX.json`（未提交 `engine/.coverage`/icons）

### Task 9 — Exploration 跳轉上下文消費 + 節點篩選 + 共用 NodeSourceFilter + i18n（3 commits）
- **Status**: DONE_WITH_CONCERNS（見 Concerns：節點篩選僅套用 distribution/trend；SPC 既有 `{name}` 插值缺口保留）
- **Commit 4ab2313 `feat(engine): exploration filter_column + filter_value (TDD)`**：`_handle_distribution`（`data/distribution`）與 `_handle_series`（`data/series`）加入與 spc/analyze・monte_carlo/run 相同的 mask block（optional `filter_column`/`filter_value`；unknown column → KeyError；缺 `filter_value` → ValueError；`df[df[col].astype(str) == str(value)]`）。**handler 名稱與 plan 假設不同**（實際為 `_handle_distribution`/`_handle_series`，非 `_handle_explore_*`）——deviation 註記。6 新測試（test_main_handlers.py）：distribution/series 各 happy-path（group A only，counts=30 / values<100）+ missing value + unknown column；RED 確認 6 fails → GREEN 後 full suite **300 passed, 1 skipped**
- **Commit c76aff4 `refactor(ui): shared NodeSourceFilter component`**：新 `src/components/NodeSourceFilter.tsx`（section prop + Tag/Alert/filter 三區塊，`t()` 依 `section` 命名空間），SPC.tsx/MonteCarlo.tsx 移除重複 JSX 改用之（state/handleAnalyze/handleRun filter passing 保留，`ApartmentOutlined` imports 移除）；behavior 不變，**visible layout 小 reflow**（filter controls 自主控制列移至 Tag 列，見 Concerns）
- **Commit 62ce296 `feat(exploration): consume jump context + node filter`**：engine.ts `fitDistribution`/`getColumnSeries` 加 optional `filters`；Exploration.tsx StrictMode-safe mount effect 消費 ctx（numeric guard 才 `setColumn`/`setTrendColumn`；`association_keys[0]` 存在於 dataset columns 才 `setNodeFilterColumn`）；NodeSourceFilter 置於 no-importResult 早退分支與主 Card；`loadFits`/`loadTrend` 透傳 filter（both set 才傳）；i18n 三語 exploration 新增 4 keys
- **驗證**：full engine suite 300 passed 1 skipped、`npx tsc --noEmit` clean、`npm run build` 成功（chunk 警示為既有）、三語 spc/monteCarlo/exploration key-set parity 全 `ok`
- **Files changed** — 見三個 commit（`engine/.coverage`/icons 未提交）
### SPC StrictMode consume bug fix + filter_value test gap
- **Status**: DONE
- **HIGH bug fix（commit 9e3d2b9）**：`SPC.tsx:34` 原在 render phase 呼叫 `consumeNodeContext()`（`processFlowNavStore.consume` 破壞性清空 pending），dev StrictMode double-invoke render 且採用第二次結果 → render #1（被丟棄）已清空 store，committed render #2 讀到 undefined → dev 下 ProcessFlow 跳轉到 SPC 失效（production 正常）。修法：`consumeNodeContext()` 移入 mount effect 內（`consumedRef.current = true` 之前、`pendingCtx` 判斷之前）；`consumedRef` 正確守衛 double-invoked effect（第一次 effect run 消費、第二次 early-return）；不新增 cleanup
- **test gap（commit b7f3100）**：`test_main_spc.py` 新增 `test_spc_analyze_with_filter_missing_value`（`filter_column` 設定但無 `filter_value` → ValueError）mirror 既有 filter 測試（共用 `_import_csv_for_spc_filter`）
- **驗證**：`pytest tests/test_main_spc.py -q` 12 passed；full suite **291 passed, 1 skipped**；`npx tsc --noEmit` clean
- **Files changed** — `src/features/spc/SPC.tsx`, `engine/tests/test_main_spc.py`（未提交 `engine/.coverage`/icons）

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

### 專案儲存擴展 Tier 1（存異常情境/控制界限/analysis package）
- **Status**: DONE
- `.piproj.json` 格式 v1 → **v2**：`ProjectFile` 新增 `anomalyScenarios`、`controlLimits`（ControlLimitsMap）、`analysisPackage`
- `buildProjectFile` 加 3 個可選參數（缺省空陣列/null）；關檔時保留 v1 向後相容（null fallback）
- store 新增 `restoreAnalysis` bulk action——`setSpec` 後呼叫（`setSpec` 會清 controlLimits/anomalies/package），還原 `controlLimits` + `anomalyScenarios` + `anomalyScenariosConfirmed`（derive:f all user_confirmed）+ `analysisPackage`
- `ProjectOverview.tsx`：handleSave 帶入 3 state；handleOpen 在 `setSpec` 後 `restoreAnalysis`
- 驗證：tsc --noEmit clean、npm run build 成功
- **Files changed** — `src/lib/project.ts`, `src/stores/dataPipelineStore.ts`, `src/features/project/ProjectOverview.tsx`

### es-MX 翻譯補齊（rebase 到 en 結構）
- **Status**: DONE
- 發現 es-MX 嚴重落後：**missing 168 keys**（en 有、es 缺）+ **stale 184 keys**（es 舊 schema 有、en 已無）——`dataImport`/`project`/`processDefine`/`modelCenter`/`settings`/`monteCarlo`/`nav` 等 section 是舊版結構
- 用 Node script rebase：preserve 既有 541 筆、新增 168 筆西文翻譯、移除 184 筆 stale
- 驗證：三語全 709 keys、0 missing、0 stale、JSON 有效、無 interpolation（{{var}}）失配、tsc --noEmit clean、npm run build 成功
- README 更新：es-MX「541 keys」→「709 keys 三語 key set 完全一致」
- **Files changed** — `src/i18n/es-MX.json`, `README.md`

### Process Flow 下游分析整合 — Task 4: 跳轉 store + 共用 helper（commit 570d01c）
- **Status**: DONE
- `src/stores/processFlowNavStore.ts` — 一次性「跳轉」請求 store（`pending { targetTab, context }` + `navigate()`/`consume()`）
- `src/lib/processFlowContext.ts` — 共用 helper：`consumeNodeContext()`（讀取+清除 store）、`findNodeById()`（載入 flow graph 找節點）、`dataSourceLoaded()`（dataSourceIds 含目前資料集；空=loaded/ok）
- 驗證：`npx tsc --noEmit` clean（目前未使用，供 Task 5-9 接線）
- **Files changed** — `src/stores/processFlowNavStore.ts`, `src/lib/processFlowContext.ts`

### Process Flow 下游分析整合 — Task 5: 關聯鍵 UI + 跳轉按鈕（commit b535cd0)
- **Status**: DONE
- `ProcessFlow.tsx`：(1) 空選面板由 Alert 改為關聯鍵編輯區（`Select mode="tags"` → `setAssociationKeys()` → 回寫 `graph.association_keys`）；(2) `machine_mapping` Select 後新增跳轉區——`out_quality_outputs` 非空顯示 SPC + Monte-Carlo 按鈕、`in_control_parameters` 非空顯示 Exploration 按鈕，`gotoAnalysisTab()` handler 彙整 dataSourceIds（output+input data sources）與 field 後呼叫 `useProcessFlowNavStore.navigate()`；(3) import 補 `setAssociationKeys`、`useProcessFlowNavStore`、`LineChartOutlined/RobotOutlined/BarChartOutlined`。`Alert` 仍用於 diagram-empty 故保留 import
- 命名更正：plan 中的 key 筆誤 `jumpToSqc` → 一律用 `jumpToSpc`
- i18n 三語 `processFlow` 各新增 8 keys（`associationKeys*` 4 支 + `jumpToAnalysis/jumpToSpc/jumpToMonteCarlo/jumpToExploration`）
- 驗證：`npx tsc --noEmit` clean、`npm run build` clean（chunk 警示為既有）、三語 key set 一致（`ok`）
- **Code review (b535cd0)**：APPROVE。無 Critical/Important；Minor——(1) `selectNode`/`selectNodeDesc` i18n key 成孤兒（原 Alert 唯一使用點被取代）；(2) 關聯鍵 `Select mode="tags"` 未設 `tokenSeparators`，貼上逗號分隔多鍵會成單一 tag（與 placeholder 例示不符）；(3) 失敗路徑不 rollback（與既有 `saveMapping` 一致之既有模式）；(4) `.length` guard 未沿襲檔內 `|| []` 防禦慣例（後端 to_dict 恆有欄位，實際安全）；(5) output+input dataSourceIds 可行重複
- **Files changed** — `src/features/process-flow/ProcessFlow.tsx`, `src/i18n/en.json`, `src/i18n/zh-TW.json`, `src/i18n/es-MX.json`

### Process Flow 下游分析整合 — Task 8: MonteCarlo 消費跳轉上下文 + 依節點篩選 + i18n（commit 878f821 + 8160797）
- **Status**: DONE
- **Part A（引擎，TDD）**：`_handle_monte_carlo_run`（main.py 原本 ~1098，現加帶位移）於 `df = REGISTRY.get(did)` 後加選用 `filter_column`/`filter_value`（mirror spc/analyze main.py:1041-1048：未知欄 → KeyError、設 filter_column 缺 filter_value → ValueError、`df = df[df[filter_column].astype(str) == str(filter_value)]`），mask 後的 df 直接續跑 `run_monte_carlo`（`df[col]` 抽樣取自 mask 子集 → 語意正確）。新增 3 tests 於 `test_main_monte_carlo.py`：filter 後 histogram counts sum == n_simulations 且 `output_mean` 顯著低於未過濾（A 群 x1~90-110 vs 未過濾加 B 群 ~190-210，mean 分離）、filter_column 無 filter_value → ValueError、未知 filter column → KeyError。紅→綠；full suite **294 passed, 1 skipped**（baseline 291 + 3）。commit `878f821`
- **Part B（engine.ts）**：`MonteCarloParams` 加 `filter_column?`/`filter_value?`（`analyzeMonteCarlo` 透傳）
- **Part C（MonteCarlo.tsx）**：consumedRef guard 的 mount effect 內消費 `consumeNodeContext()`（StrictMode-safe，mirror SPC.tsx）——`findNodeById` 成功後 `setSourcedFromNode`；source 已載入時 `getFlowGraph()` 讀 `association_keys[0]` 設預設 filter column（MC 無 output-field 控制，不做 field 消費；`importResult.columns` 提供欄位 Select options）；Card 頂部來源 Tag（`monteCarlo.sourceFromNode`）+ 未載入時 `Alert warning`（`dataSourceNotLoaded`）；已載入時顯示篩選控制列（欄位 Select + 值 Input + 清除 Button，placeholder `filterByNode`/`nodeFilterCleared`）；`handleRun` 僅當 `nodeFilterColumn && nodeFilterValue` 兩者皆設時帶 `filter_column`/`filter_value`
- **Part D（i18n）**：三語 `monteCarlo` 各 +4 keys（sourceFromNode/dataSourceNotLoaded/filterByNode/nodeFilterCleared）；parity check `ok`
- **驗證**：引擎 294 passed 1 skipped；`npx tsc --noEmit` clean；`npm run build` 成功（chunk 警示為既有）；i18n parity `ok`
- **Files changed** — `engine/src/process_intelligence_engine/main.py`, `engine/tests/test_main_monte_carlo.py`, `src/lib/engine.ts`, `src/features/monte-carlo/MonteCarlo.tsx`, `src/i18n/en.json`, `src/i18n/zh-TW.json`, `src/i18n/es-MX.json`（未提交 `engine/.coverage`/icons）

<!-- NEXT_ITEM_ANCHOR -->

### Code review — SPC node-filter/context-integration line（Tasks 7+7b+StrictMode fix，commits 74e44f4..b7f3100）
- **Status**: DONE — **APPROVE**（無 Critical；2 Important 皆 edge-case UX，建議 follow-up）
- **獨立驗證**：full engine **291 passed, 1 skipped**；`test_main_spc.py` 12 passed；`npx tsc --noEmit` clean；每 commit 單一邏輯變更；i18n 5 新 key 全被 SPC.tsx 引用（250/258/267/279/287/297）、三語 parity
- **Mount effect/StrictMode 正確性確認**：`consumedRef` 在 await 前同步 set → double-effect 第二次 early-return；`consume()` 為一次性破壞性（store 置 null pending），async closures（findNodeById/getFlowGraph/setState）確定只跑一次；`setColumn` 僅在 `dataSourceLoaded` 為 true 時執行（56-69）；`dataSourceLoaded` 空/undefined dataSourceIds → true（OK）語義正確；React 18 已移除 unmounted setState warning，無需 cancelled flag
- **Important #1**：SPC.tsx:57-59 `pendingCtx.field` 未過濾 numeric（plan Step 2 的 `numericColumns.includes` fallback 被捨棄）——非數值 quality output tag → Analyze 時 engine `np.asarray(..., dtype=float)` ValueError 以生硬訊息呈現
- **Important #2**：main.py:1048 `astype(str) == str(value)` 對數值欄猥瑣（50.0 vs "50" → 0 列 → spc.py:110-111 "values must not be empty"）；filter 預設為 association key（通常類別）故中標率低，但數值欄自由文字無防護
- **Minor**：effect deps `[]` 讀 `importResult` → jump-before-import 時資料載入後不會自動補選；無資料時 dataSourceNotLoaded + noDataHint 雙 Alert 重複；happy path 兩次 `getFlowGraph()` IPC；engine `filter_value` 僅檢查 None 不檢查 ""；`NodeContextResult`（processFlowContext.ts:4，Task 4 既有）export 未用；測試未涵蓋 empty-match 與 "" filter_value
- **Files reviewed** — `src/features/spc/SPC.tsx`, `engine/src/process_intelligence_engine/main.py`, `engine/tests/test_main_spc.py`, `src/lib/engine.ts`, `src/lib/processFlowContext.ts`, i18n×3

### Process Flow 下游分析整合 — Task 6: App.tsx 訂閱跳轉 store 切換 tab（commit 26f3b89）
- **Status**: DONE
- `App.tsx`：react import 合併為 `import { useEffect, useState } from 'react'`；新增 `useProcessFlowNavStore` import；`activeTab` 之後加 `pendingTarget = useProcessFlowNavStore((s) => s.pending?.targetTab)` + `useEffect`（pendingTarget 非空且不同於 activeTab 時 `setActiveTab(pendingTarget)`，同 tab guard 防迴圈；pending 由消費者 `consume()` 清除，App 不清）
- 驗證：`npx tsc --noEmit` clean、`npm run build` 成功（chunk 警示為既有）
- **Files changed** — `src/App.tsx`
- **Code review (26f3b89)**：APPROVE。無 Critical。Guard/loop 驗證正確；deps 完整；無 scope creep。Important（跨 task，非本 commit 缺陷）：dev StrictMode 會 double-invoke mount effect → Tasks 7-9 的 `consume()` 第二次回 undefined 而清掉 sourceTag（production 不受影響），需在 Tasks 7-9 以 ref/「僅 set 不清」守衛。資訊：跳轉 force-switch 屬 plan 一次性語意、窗口為 sub-frame 級，非人為可觸發；Task 7-9 落地前 pending 未消費會短暫劫持 tab 切換（plan 順序 artifacts）

### Process Flow 下游分析整合 — Task 7b: SPC 節點篩選（引擎 filter TDD + 前端 wire + UI，commit c22c283 + a15e04c）
- **Status**: DONE
- **Part A（引擎，TDD）**：`_handle_spc_analyze` 於 `df = REGISTRY.get(...)` 後加選用 `filter_column`/`filter_value`（`filter_column` 不在 df.columns → `KeyError`；有 `filter_column` 無 `filter_value` → `ValueError`；`astype(str) == str(filter_value)` df-level mask 後既有邏輯續跑）。新增 2 tests（`test_spc_analyze_with_filter` — work_order A/B 兩群，filter 後 `x_values` 全 <100、`x_mean`≈50、len==30；`test_spc_analyze_with_filter_unknown_column` — KeyError）。紅→綠→(無需 refactor)；測試放 `test_main_spc.py`（spc/analyze 既有測試所在，非 plan 預期的 test_main_handlers.py）。commit `c22c283`
- **Part B（engine.ts）**：`analyzeSPC` params 型別加 `filter_column?`/`filter_value?`（透傳，由呼叫端決定是否帶入）
- **Part C（SPC.tsx）**：新 state `nodeFilterColumn`/`nodeFilterValue`；mount effect 內 `findNodeById` 後另 `getFlowGraph()` 讀 `association_keys[0]`，若存在於 `importResult.stats.column_stats` 設為預設 filter column；控制列（`sourcedFromNode` 且 source 已載入時顯示）——欄位 Select（options=全部 dataset columns，placeholder `spc.filterByNode`）+ 值 Input（placeholder `spc.sameSourceHint`，無 filter column 時 disabled）+ 清除 Button（`spc.nodeFilterCleared`）；`handleAnalyze` 在 `nodeFilterColumn && nodeFilterValue` 兩者皆設時才帶 `filter_column`+`filter_value`（**column_stats 無 distinct values 欄位**，故依 plan 允許用 Input）。無新 i18n key（`filterByNode`/`nodeFilterCleared`/`sameSourceHint` 三語 Task 7 已預置）。commit `a15e04c`
- **驗證**：2 新測試 pass → 全引擎 **290 passed, 1 skipped**（baseline 288+2，無回歸）；`npx tsc --noEmit` clean；`npm run build` 成功（chunk 警示為既有）；三語 spc key set parity `ok`
- **Files changed** — `engine/src/process_intelligence_engine/main.py`, `engine/tests/test_main_spc.py`, `src/lib/engine.ts`, `src/features/spc/SPC.tsx`

### Process Flow 下游分析整合 — Task 7: SPC 消費跳轉上下文 + 節點篩選 + i18n（commit 74e44f4）
- **Status**: DONE_WITH_CONCERNS（節點篩選 UI 未落地，見下）
- `SPC.tsx`：consumedRef guard 的 mount effect 消費 `consumeNodeContext()`（StrictMode-safe，**有意的 plan 偏離**——省略 `cancelled` cleanup，因其在 dev StrictMode 的 synthetic unmount 會把非同步 `findNodeById` 結果取消導致 sourceTag 遺失）；`findNodeById` 成功後一律 `setSourcedFromNode`（含 dataSourceIds，供 JSX render-time 重算 `dataSourceLoaded`），source 已載入且有 node 輸出欄位時 `setColumn(field)` 自動選欄（真正的「consumeField」＝SPC 既有的 `setColumn`，plan 誤以為存在 wrapper 函式）；Card 頂部加來源 Tag（`ApartmentOutlined` + `spc.sourceFromNode`, {name}插值）+ 未載入時 `Alert warning`（`spc.dataSourceNotLoaded`）
- **節點篩選（Step 4）未落地，NOTE**：SPC.tsx 現檔無「Data source Select/setImportResult/setSpec/{x,y} 組裝」、`spc/analyze` 後端無 row-filter 參數（`_handle_spc_analyze` 對整個 dataset 分析）、`ImportResult` 僅有 stats+raw_preview（無全量 rows）、`ProcessNodeContext` 無 key column/value（`ProcessFlow.gotoAnalysisTab` 只帶 nodeId/displayName/field/dataSourceIds）→ 任何前端 row filter 都是無效空控，故不 shipping no-op Select。建議（待 user 允）後端 `spc/analyze` 加選用 `filter_column`/`filter_value`（df-level mask ~4 行）+ `analyzeSPC` 參數透傳後再接 UI；i18n 的 `filterByNode`/`nodeFilterCleared`/`sameSourceHint` 三鍵已預置（三語齊全）留待該功能
- 驗證：三語 spc key set parity `ok`（各 32 keys）、`npx tsc --noEmit` clean、`npm run build` clean（chunk 警示為既有）
- **Files changed** — `src/features/spc/SPC.tsx`, `src/i18n/en.json`, `src/i18n/zh-TW.json`, `src/i18n/es-MX.json`
- **Code review (74e44f4 + c22c283 + a15e04c)**：❌ Task 7 NOT APPROVED（HIGH）+ Task 7b APPROVE（MINOR）。獨立驗證：引擎 290 passed 1 skipped、test_main_spc.py 11 passed（9 既有 + 2 新）、test_main_handlers.py 無任何 spc 測試（測試選檔正確）、tsc clean、三語 spc 各 33 keys parity ok、5 新 key 齊全且 {name} 插值一致、三 commit 僅含聲明檔案、`_handle_spc_analyze` filter 邏輯（main.py:1041-1048）與 spec 逐行相符。**HIGH**：SPC.tsx:34 在 **render phase** 呼叫 `consumeNodeContext()`（processFlowNavStore.consume 具破壞性清空 pending），而 dev StrictMode（main.tsx:20）double-invoke function body 並採用第二次結果（react-dom.development.js:19617-19629 `updateFunctionComponent` second `renderWithHooks` 覆蓋 `nextChildren`）→ render #1（被丟棄）已清空 store，committed render #2 讀到 undefined → mount effect（SPC.tsx:47）no-op → dev 下 source Tag/setColumn/篩選預設/dataSourceNotLoaded 全部失效；production 正常。`consumedRef` 只防 double-effect，防不了 double-render。修法：把 `consumeNodeContext()` 移入 effect 內（consumedRef 之前）。**MINOR**：`filter_column` 無 `filter_value` 的 ValueError 分支（main.py:1046-1047）無測試（只測 happy path + KeyError）；red→green 過程無法由單一 commit 事後驗證
- **Status**: DONE
- `engine.ts` `FlowGraph` 新增 `association_keys: string[]`；`getFlowGraph()` 後新增 `setAssociationKeys(keys)` → `engineCall({ set_association_keys: keys })` 走 `project/flow-graph` IPC
- `ProcessFlow.tsx` line 115 `useState<FlowGraph>({ nodes: [], edges: [], association_keys: [] })`（Task 5 UI 前唯一允許的 touch）
- 驗證：`npx tsc --noEmit` clean
- **Files changed** — `src/lib/engine.ts`, `src/features/process-flow/ProcessFlow.tsx`

### Process Flow 下游分析整合 — Task 1: ProjectManifest.association_keys + set_association_keys（commit cd7788e）
- **Status**: DONE
- `manifest.py` `ProjectManifest` 新增 `association_keys: list[str]` 欄位（`settings` 後，`to_dict`/`from_dict` 經 `asdict`/`__dataclass_fields__` 自動序列化）
- `ProjectEngine` 新增 `set_association_keys(keys)` —— 過濾空字串/strip 後儲存並回傳
- `get_flow_graph()` return 加 `association_keys: list(manifest.association_keys)`
- **Tests**：`test_manifest_nodes.py` 新增 3 個（default empty / persists / survives reload）；test_manifest_nodes **8 passed**；full suite **287 passed, 1 skipped**（baseline 284 + 3 new）
- **Files changed** — `engine/src/process_intelligence_engine/project/manifest.py`, `engine/tests/test_manifest_nodes.py`

### Process Flow 下游分析整合 — Task 2: project/flow-graph IPC 支援 association_keys
- **Status**: DONE
- `_handle_project_flow_graph(params)` 改為：`params` 有 `set_association_keys` 時呼叫 `PROJECT_ENGINE.set_association_keys(keys)` 回傳 `{"association_keys": [...]}`；否則維持 `get_flow_graph()`（其 return 已含 `association_keys`）
- **Tests**：`test_main_handlers.py` 新增 `test_handle_flow_graph_set_association_keys`（set 後回傳 + 再次查詢持久化）；full suite **288 passed, 1 skipped**
- **Files changed** — `engine/src/process_intelligence_engine/main.py`, `engine/tests/test_main_handlers.py`

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

### ProcessFlow 強化 — 設計討論（brainstorming）
- **Status**: IN_PROGRESS（設計階段，尚未寫 code）
- **User 方向**：導覽列製程流程「作用太薄弱」→ 兩者都要：(1) 補規格 §11A/§18.6 深度 (2) 讓流程圖驅動/參數化下游分析
- **User 確認**：三階段深度整合（Step1 跨節點關聯鍵 barcode/序號/批次；Step2 節點資料面板→可點擊跳到對應分析 tab 帶入欄位/規格；Step3 下游 tab 依節點篩選入口）。規格深度（製程群組/目錄映射/資料流指標）留後續。
- **探索發現**：ProcessFlow.tsx 已是完整 SVG 編輯器（817 行：拖曳/縮放/minimap/自動佈局/連線/資料來源與機台對映）。薄弱處 = 與分析 tab 斷連（SPC/MonteCarlo 只用 store 的 importResult+spec，不動用節點映射）。App.tsx 用 `useState activeTab` 管理切換（需 navigation store 才能帶 payload）。引擎 ProcessNode 無 association_keys 欄位。
- **待辦**：提方案→設計文件→commit→user 審核→writing-plans

### Task 1 引擎 — ProjectManifest.association_keys + set_association_keys (REVIEWED)
- **審核結果**：✅ Spec 完全符合（commit cd7788e）
  - `association_keys: list[str] = field(default_factory=list)` 位於 `settings` 後（manifest.py:149）
  - `set_association_keys(keys) -> dict[str, Any]`：`_ensure_project()` + `_load()` → `[str(k).strip() for k in keys if str(k).strip()]` → `_save()` → 回傳 dict（manifest.py:449-454）
  - `get_flow_graph()` 回傳含 `association_keys`（manifest.py:530）
  - 3 個測試齊備（test_manifest_nodes.py:53-74），全部通過
  - 全 suite 287 passed / 1 skipped 確認無迴歸
  - commit 僅含 2 個檔案（manifest.py +10/-1、test_manifest_nodes.py +23）無異動其他程式
  - 小備註：reload 測試含一行中文註解 `# 重載 manifest 物件`（test:70），非功能性偏差

### Task 5 ProcessFlow — 關聯鍵 UI + 跳轉按鈕 + i18n (REVIEWED)
- **Status**: DONE（commit b535cd0）
- **審核結果**：✅ Spec 完全符合
  - imports：`setAssociationKeys`（engine）、`useProcessFlowNavStore`（nav store）、`LineChartOutlined`/`RobotOutlined`/`BarChartOutlined` 齊備
  - `useState<FlowGraph>` 初始 `association_keys: []`（ProcessFlow.tsx:120）
  - null-branch 空選單面板 → `<Select mode="tags">` 綁定 `graph.association_keys`，onChange `setAssociationKeys(keys)` → 更新 graph + `associationKeysSaved` success，catch `saveError`（:840-855；此分支原 `<Alert>` 已移除）
  - 跳轉區於 machine_mapping 後、connectTo 前：標題 `jumpToAnalysis`；`out_quality_outputs.length>0` 時顯示 SPC(`jumpToSpc`)/MonteCarlo(`jumpToMonteCarlo`)，`in_control_parameters.length>0` 時顯示 Exploration(`jumpToExploration`)（:766-796）
  - 共用 handler `gotoAnalysisTab(tab,node)`：dataSourceIds = output+input 兩來源串接；field = exploration→第一個 in_control_parameters、否則第一個 out_quality_outputs；呼叫 nav store `navigate(tab,{nodeId,displayName,field,dataSourceIds})`（:406-424）
  - 全檔使用 `jumpToSpc`，無 `jumpToSqc`
  - i18n：8 支新 key（associationKeys/Desc/Placeholder/Saved + jumpToAnalysis/Spc/MonteCarlo/Exploration）三語 en/zh-TW/es-MX 齊備、翻譯各語言適切、key set 一致（parity check `ok`）
  - 驗證：`npx tsc --noEmit` EXIT 0 clean；i18n parity `ok`
  - commit b535cd0 恰好 4 檔（ProcessFlow.tsx + 3 JSON）+102/-6、訊息 `feat(process-flow): association keys UI + jump buttons`
  - 小備註：`Alert` import 保留仍使用（:517 noNodes）；`selectNode`/`selectNodeDesc` JSON key 現無人引用但屬既有，task 未要求移除→保留

### Task 9 Exploration — 消費跳轉情境 + 節點篩選 + i18n + 共用元件 (REVIEWED)
- **Status**: DONE（3 commits: 4ab2313 / c76aff4 / 62ce296）
- **審核結果**：✅ Spec 完全符合
  - Engine: `_handle_distribution`/`_handle_series` 加 filter_column/filter_value（mask `df[df[col].astype(str)==str(val)]`、未知欄 KeyError、缺值 ValueError）；6 測試（happy-path group A / missing value / unknown column）全過
  - engine.ts: fitDistribution/getColumnSeries 加 filters，僅兩者皆設時帶入
  - NodeSourceFilter.tsx 共用元件（section/sourcedFromNode/dataLoaded/columns/filterColumn/setFilterColumn/filterValue/setFilterValue/clearFilter/valuePlaceholder），內部 useTranslation `${section}.*`；SPC/MC 重構行為保留、ApartmentOutlined 死 import 移除、自家 filter state 保留並傳入 analyze
  - Exploration.tsx: 在 effect 內 consume（consumedRef 在 await 前同步設 true，StrictMode-safe）；`field && numericColumns.includes(field)` 才自動選欄；預設篩選欄 = association_keys[0]（需存在於資料集欄位）；loadFits/loadTrend 僅兩者皆設才傳 filter；時間序列/GRR 未篩選（spec 明載後續）
  - i18n: 4 支新 key ×3 語（exploration 段，`{{name}}` 正確插值）；spc/monteCarlo 沿用既有 key；cross-locale + 三段共用 key parity OK
  - 驗證：pytest 300 passed / 1 skipped；tsc clean；vite build 成功；commit 範圍三檔皆精確
  - 備註（皆已核實非本次引入）：
    1. **spc.sourceFromNode 用單括號 `{name}`**（en/es-MX/zh-TW 三語皆然，74e44f4 Task 7 引入）→ i18next 只吃 `{{name}}`，SPC Tag 會字面顯示 `{name}`；本次未修（依 spec 邊界），建議後續 follow-up 一語改寫
    2. SPC/MC 篩選控制自主要 controls Space 移出至 NodeSourceFilter 自有 Space → 僅視覺分組變動，行為一致
    3. Exploration mount effect 閉包捕捉首次 render 的 numericColumns（[] deps）→ 若跳轉時資料集尚未載入則不會自動選欄，與 SPC 同為既有模式，非阻塞

### 待辦 / 下一步
- [ ] follow-up：修正 spc.sourceFromNode 三語單括號 `{name}` → `{{name}}`
- [ ] follow-up：GRR / 時間序列套用節點篩選
- [ ] 全任務九完成，可進行總體驗收 / 文件更新
