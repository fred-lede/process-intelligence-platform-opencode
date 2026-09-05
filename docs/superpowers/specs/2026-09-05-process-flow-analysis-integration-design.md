# 製程流程圖 × 下游分析整合 — 設計文件

日期：2026-09-05
狀態：審閱中
對應規格：main spec §11A（資料資產管理）、§18.6（資料目錄與製程群組）

## 1. 背景與問題

`ProcessFlow.tsx` 已是完整的 SVG 圖形化編輯器（817 行），具備節點
CRUD、連線拖曳、節點拖曳＋位置持久化、自動佈局、縮放／平移、minimap、
以及節點級資料對映面板（`input_data_sources` / `output_data_sources` /
`in_control_parameters` / `out_quality_outputs` / `machine_mapping`）。

但**這個 tab 在整個產品中是孤立的**——它畫出的流程與映射，對下游所有
分析 tab 完全不可見。SPC、Monte-Carlo、Exploration 三者都只從
`dataPipelineStore` 讀取 `importResult` 與 `spec`，從不查詢流程節點的
資料源／品質輸出／控制參數。使用者畫完流程圖後，除了「看」與「排佈」，
節點上填的資料映射對分析流程沒有任何作用。

對照 main spec §11A 的定義，流程圖理應是**專案分析的主幹**：
「跨節點分析則透過共同的 barcode、序號、批次、工單或使用者指定的關聯鍵
串接」——目前這項能力完全缺失，流程圖與分析數據沒有橋接。

產品現況另有一個**結構性限制**：`App.tsx` 以 `useState<AppTab>`
管理目前 tab，沒有機制在切換 tab 時傳遞額外 payload（例如「跳到 SPC 並
預選某節點的品質輸出欄位」）。

## 2. 目標

在不重寫流程圖編輯器的前提下，讓流程圖**成為下游分析的參數化入口**，
並補上跨節點分析所需的關聯鍵。本次只做**三階段的下游整合**；spec §11A
更深層的製程群組設定、目錄掃描／映射、資料流指標（哪份資料流過哪節點）
**不列入本次範圍**，留待後續。

## 3. 範圍（三階段）

| 階段 | 內容 | 任務代號 |
|------|------|---------|
| Step 1 | 跨節點關聯鍵（flow 層級） | FAI-1 |
| Step 2 | 節點資料面板可點擊跳轉 → 帶入欄位／資料源 | FAI-2 |
| Step 3 | 下游 tab 依節點篩選入口 | FAI-3 |

**明確排除**（後續階段）：製程群組設定與目錄映射、自動目錄掃描、
「節點→資料集→實際資料流」的推導與指標視覺化、自動載入資料源。

## 4. 共用基礎設施

三階段共用兩件新的前端最小載具，兩者都不觸及引擎。

### 4.1 Tab 跳轉載具 — `useProcessFlowNav`

新增 `src/stores/processFlowNavStore.ts`（仿照 `dataPipelineStore` 的
zustand 模式）：

```ts
interface ProcessNodeContext {
  nodeId: string
  displayName: string
  field?: string          // 目標欄位（品質輸出 / 控制參數）
  dataSourceIds?: string[] // 節點 input/output 資料源 dataset_id
}

interface ProcessFlowNavState {
  pending?: {
    targetTab: 'spc' | 'monteCarlo' | 'exploration'
    context: ProcessNodeContext
  }
  navigate: (targetTab, context) => void
  consume: () => ProcessNodeContext | undefined   // 讀取並清除（一次性）
}
```

`App.tsx` 的 `setActiveTab(newTab)` 改為訂閱 store：`renderTab()` 回傳
目標元件時若有 `pending` 則消費它。目標 tab（SPC/MC/Exploration）在
mount 時讀 `consume()` 取得上下文。

> 簡化：因 `App.tsx` 的 `activeTab` 是本機 state，本設計以 `consume()`
> 一次性讀取為原則——跳轉目標在 `useEffect` 中 `consume()`，欄位初始化
> 後即清除，避免跨 tab 殘留。

### 4.2 節點上下文載具（Tab 內初始化）

各目標 tab 在 mount 的 `useEffect` 中讀取已消費的上下文，用身設定
對應的下拉／篩選的初始值，並以 Tag 標示「來源：製程節點 X」。

## 5. Step 1 — 跨節點關聯鍵（FAI-1）

### 5.1 資料模型（引擎）

關聯鍵是**跨節點共享**（spec §11A：「共同的 barcode、序號、批次…」），
因此放在 **flow / manifest 層級**，而非節點層級。現況：
`ProjectManifest`（`manifest.py`）持有 `process_nodes`，`get_flow_graph()`
在呼叫時由 `process_nodes` 現場組出 `{nodes, edges}`——**沒有獨立的
`FlowGraph` dataclass，也沒有 `set_association_keys`**。故正確的存放位置是
`ProjectManifest` 本身：

- `engine/.../project/manifest.py`：
  - `ProjectManifest` 增 `association_keys: list[str]`
    （dataclass 欄位，`to_dict`/`from_dict` 自動帶入）。
  - 新增 `set_association_keys(keys)` 方法寫回並 `_save()`。
- `engine/.../main.py`：
  - `get_flow_graph()` 回傳改為 `{nodes, edges, association_keys}`。
  - 新增 IPC `project/flow-graph/keywords`（或於現有
    `project/flow-graph` handler 增加 update 分支）接受
    `set_association_keys` 並寫入 manifest。
- `src/lib/engine.ts`：`FlowGraph` 型別加 `association_keys: string[]`；
  新增 `setAssociationKeys(keys)` 包裝函式。

### 5.2 前端 UI

`ProcessFlow.tsx`：未選節點時，原本的面板顯示「選擇節點」提示，改為
顯示**流程關聯鍵編輯區**（Select `mode="tags"`，placeholder 提示
barcode / serial_no / batch_no / work_order），onChange 呼
`updateFlowGraph({ association_keys })`。

## 6. Step 2 — 節點資料面板可點擊跳轉（FAI-2）

### 6.1 行為

節點被選取時，屬性面板中既有欄位群組改為**可點擊**：

| 現有欄位 | 跳轉目標 tab | 帶入的 field 初值 |
|----------|--------------|-------------------|
| `output_data_sources` + `out_quality_outputs` | `spc` | 第一個 `out_quality_outputs` |
| `output_data_sources` + `out_quality_outputs` | `monteCarlo` | 第一個 `out_quality_outputs` |
| `input_data_sources` + `in_control_parameters` | `exploration` | 第一個 `in_control_parameters` |

每個欄位 「跳到 SPC / 跳到 Monte-Carlo / 跳到探索」小按鈕，點擊時呼叫
`navigate(tab, context)`，其中 `context` 帶入 `nodeId`、`displayName`、
與該節點對應的 `dataSourceIds` 與 `field`。

### 6.2 資料源處理（已與使用者確認）

跳轉**不自動載入資料源**。目標 tab mount 時：

- 若節點 `dataSourceIds` 中的任一 dataset 恰為目前
  `importResult.dataset_id` → 欄位下拉直接可用，並顯示來源 Tag。
- 否則 → 欄位下拉維持空，顯示提示「此節點資料源未載入，請到 Data
  Import 載入」；仍顯示節點來源 Tag（提示使用者從何而來）。

## 7. Step 3 — 下游 tab 依節點篩選（FAI-3）

### 7.1 篩選入口

SPC / Monte-Carlo / Exploration 三個 tab 各在工具列加一個
「製程節點」篩選 `<Select>`（列出流程圖所有節點），值改變時：
- 用該節點 `out_quality_outputs`（SPC/MC）或 `in_control_parameters`（探索）
  覆寫欄位選項與選中值。
- 顯示來源 Tag「製程節點：X」。
- 資料源處理同 §6.2（不自動載入，未載入即提示）。

### 7.2 與 Step 2 的關係

Step 3 是 Step 2 的「站內版」：Step 2 提供「從流程圖跳進來」，
Step 3 提供「站在目標 tab 直接選一個節點」。兩者共用同一組
「套用節點上下文」的 helper（`src/lib/processFlowContext.ts`），避免
重複邏輯。

## 8. 檔案變更清單（預估）

| 檔案 | 變更 |
|------|------|
| `engine/.../project/manifest.py` | `FlowGraph.association_keys` |
| `engine/.../main.py` | get/set association_keys |
| `engine/tests/test_project_flow.py` | association_keys 存取測試 |
| `src/lib/engine.ts` | `FlowGraph.association_keys` |
| `src/stores/processFlowNavStore.ts` | 新增跳轉 store |
| `src/lib/processFlowContext.ts` | 新增套用節點上下文的共用 helper |
| `src/App.tsx` | 訂閱跳轉 store |
| `src/features/process-flow/ProcessFlow.tsx` | 關聯鍵 UI + 跳轉按鈕 |
| `src/features/spc/SPC.tsx` | 讀取上下文 + 節點篩選 |
| `src/features/monte-carlo/MonteCarlo.tsx` | 讀取上下文 + 節點篩選 |
| `src/features/exploration/Exploration.tsx` | 讀取上下文 + 節點篩選 |
| `src/i18n/en.json` / `zh-TW.json` / `es-MX.json` | 新增 keys（三語一致） |

## 9. 驗證

- 引擎：`cd engine && .venv/bin/python -m pytest tests/ -q`（含新 test）。
- 前端：`npx tsc --noEmit`、`npm run build`。
- 三語：JSON 有效、三語 key set 一致、無 `{{var}}` 失配。
- 手動：流程圖設定關聯鍵 → 畫節點並映射 → 點「跳到 SPC」看到欄位與來源 Tag。

## 10. 本迭代不做／留待後續

- 製程群組設定與目錄映射（spec §11A）。
- 自動目錄掃描與「資料流→節點」指標視覺化。
- 跳轉時自動載入資料源（維持「只帶上下文字段」）。
- 節點層級關聯鍵（本設計採 flow 層級）。