# Approval 審核 tab 設計（spec §20）

日期：2026-09-04
狀態：設計（待實作）
範圍：建立獨立的 Approval 審核 tab——可將模型/報告送審、核可/退回、查詢審核紀錄。

## 背景與現況

- **Backend approval workflow 已完整**（`engine/src/process_intelligence_engine/approval/workflow.py`）：
  - 資源型態 `model` | `report`；狀態 `draft → pending_review → approved/rejected`（rejected → draft）。
  - `submit_for_review` / `approve` / `reject` / `get_status` / `list_records`。
  - `approve`/`reject` 要求 `reviewer_role` 為 `reviewer` 或 `admin`。
  - IPC 已 wiring：`approval/submit` / `approval/approve` / `approval/reject` / `approval/status` / `approval/records`。
- **模型有 registry**：`modeling/list` 回傳已訓練/匯入模型（`MODEL_REGISTRY`）。
- **報告無 registry**：`report/generate` 只產出檔案/HTML 預覽，沒有被追蹤成可列舉的清單。

## 目標

建立 `src/features/approval/Approval.tsx` 獨立 tab，讓使用者：
1. 將**模型**或**報告**資源送出審核（選資源 + 選 reviewer + comments → `pending_review`）。
2. 具 `reviewer`/`admin` 身分者對待審資源**核可（approve）或退回（reject）**。
3. 檢視各資源**目前狀態**與**完整審核紀錄**（action/reviewer/comments/timestamp）。

## Architecture / 資料流

```
Approval tab
  ├─ 資源清單（模型：modeling/list；報告：report/list）
  ├─ 送審表單 ── submit_for_review(reviewer, resource) → approval/submit
  ├─ 待審核（status=pending_review）→ approve / reject → approval/approve|reject
  └─ 審核紀錄表（approval/records）

後端新增：
  ReportRegistry（in-memory）: report/generate 成功即 register
    └─ report/list IPC 回傳已產生報告
```

## Backend 變更

### 1. 新增 `REPORT_REGISTRY`（報告追蹤）

在 `engine/src/process_intelligence_engine/reporting/` 新增輕量 in-memory registry（平行 `MODEL_REGISTRY`）：
- `ReportRecord`: `report_id`（uuid）、`project_name`、`format`（html/pdf/excel）、`operator`、`timestamp`。
- `register(...)`：在 `report/generate` handler 成功產出後呼叫登記。
- `list()`：回傳全部紀錄（新→舊）。
- `_handle_report_list(params)` + IPC `report/list`：回傳 `{"reports": [...]}`。

### 2. 透傳 reviewer role（RBAC 判定）

`approval` 4 個既有 handler 不改邏輯；前端以 current user 的 role 決定是否顯示 Approve/Reject 按鈕。`approval/records` 已回傳完整紀錄，無需變更。

## Frontend 變更

### engine.ts
新增 interface 與 functions：
- `ReportRecord { report_id; project_name; format; operator; timestamp }`
- `ApprovalRecord { record_id; resource_type; resource_id; action; reviewer; reviewer_role; comments; timestamp }`
- `listReports(): Promise<{ reports: ReportRecord[] }>` → `report/list`
- `submitForReview(params)` → `approval/submit`；`approveResource(params)` → `approval/approve`；`rejectResource(params)` → `approval/reject`
- `getApprovalStatus(resource_type, resource_id)` → `approval/status`
- `listApprovalRecords()` → `approval/records`

### Approval.tsx（新增）
- **資源來源**：`modeling/list`（模型）+ `report/list`（報告），合併成一張資源表，顯示 `resource_type`、`resource_id`/`project_name`、`status`。
- **送審表單**：選資源（模型/報告）、選 reviewer（`listUsers()` 中 role=reviewer/admin）、comments → submit。
- **核可/退回**：對 `status=pending_review` 且 current user 為 reviewer/admin 的列，顯示 Approve（綠）/Reject（紅）按鈕，各開啟 comments modal 後呼叫對應 IPC。完成後刷新狀態清單。
- **審核紀錄表**：`approval/records` 全量列出（time/resource/action/reviewer/comments）。
- 身分取得：`getCurrentUser()` 的 `role`。
- 路由：`types/index.ts` 的 `AppTab` 加 `'approval'`；`Sidebar.tsx` 加 nav item；`App.tsx` 加 `if (activeTab === 'approval') return <Approval />`；`assistantGuide.ts` 加 approval guide。

### i18n（en / zh-TW / es-MX）
- `nav.approval`
- `approval.*`：title、resourceType（model/report）、resourceId、status、draft/pendingReview/approved/rejected、submit/reviewer/comments/approve/reject/records、noResources、onlyReviewer 等。

## 測試

- **Backend**（`engine/tests/`）：
  - `report/generate` 成功後 registry 登記、`report/list` 回傳該報告。
  - `report/list` 空時回傳空清單。
- **前端**：`npx tsc --noEmit`、`npm run build` clean；三語 JSON 有效。

## 非目標（YAGNI）
- 不把 approval 整合進各資源頁（不嵌入其他 tab）。
- 不做多步驟/串行審核流程（維持單一 reviewer 審核，與現有 backend 一致）。
- 不做 RBAC 後端強制改動——沿用現有 `approval/approve`/`reject` 的 role 檢查，前端僅做 UI 顯示控管。
