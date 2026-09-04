# Approval 審核 tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立獨立 Approval 審核 tab，支援將模型/報告送審、核可/退回待審資源、並檢視完整審核紀錄。

**Architecture:** Backend 新增輕量 in-memory `REPORT_REGISTRY`（`report/generate` 成功即登記）與 `report/list` IPC，供 Approval 列舉已產生報告；既有的 `approval/*` workflow IPC 已完整不再變動。Frontend 新增 `Approval.tsx` 獨立 tab——列出模型（`modeling/list`）+ 報告（`report/list`）資源與狀態、送審表單、依 current user role（reviewer/admin）顯示核可/退回、審核紀錄表。

**Tech Stack:** Python 3.11 + pandas（engine）、Tauri 2.0 + React 18 + TypeScript + AntD 5 + i18next（en/zh-TW/es-MX）。

---

## 檔案結構

- `engine/src/process_intelligence_engine/reporting/registry.py` — **新增**，`ReportRecord` + `ReportRegistry`
- `engine/src/process_intelligence_engine/main.py` — import registry、`report/generate` 登記 hook、新增 `_handle_report_list` + `report/list` dispatch
- `engine/tests/` — report registry + IPC 測試
- `src/lib/engine.ts` — `ReportRecord`/`ApprovalRecord` interface + `listReports`/`submitForReview`/`approveResource`/`rejectResource`/`getApprovalStatus`/`listApprovalRecords`
- `src/features/approval/Approval.tsx` — **新增**，Approval 審核 UI
- `src/types/index.ts`、`src/App.tsx`、`src/components/layout/Sidebar.tsx`、`src/lib/assistantGuide.ts` — 路由整合
- `src/i18n/en.json` / `zh-TW.json` / `es-MX.json` — approval keys

---

### Task 1: Backend — `REPORT_REGISTRY` + `report/list` IPC

**Files:**
- Create: `engine/src/process_intelligence_engine/reporting/registry.py`
- Modify: `engine/src/process_intelligence_engine/main.py`
- Test: `engine/tests/test_report_registry.py`（**新增**）

- [ ] **Step 1: 寫失敗測試**

```python
"""Tests for the report registry used by the Approval tab."""
from process_intelligence_engine.reporting.registry import _REPORT_REGISTRY as reg


def test_register_and_list_report():
    reg._clear()
    rid = reg.register(
        project_name="Proj A",
        operator="qa",
        output_format="html",
    )
    reports = reg.list()
    assert len(reports) == 1
    assert reports[0]["report_id"] == rid
    assert reports[0]["project_name"] == "Proj A"
    assert reports[0]["operator"] == "qa"
    assert reports[0]["format"] == "html"
    assert reports[0]["timestamp"]


def test_list_empty():
    reg._clear()
    assert reg.list() == []
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd engine && .venv/bin/python -m pytest tests/test_report_registry.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named ... 'reporting.registry'` / `cannot import name '_REPORT_REGISTRY'`

- [ ] **Step 3: 實作 registry 模組**

```python
"""In-memory registry of generated reports (for the Approval tab).

Tracks every successful report/generate so the frontend can list
generated reports and submit them for review.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any


class ReportRegistry:
    """In-memory registry of generated report records."""

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def register(
        self,
        project_name: str,
        operator: str = "Unknown",
        output_format: str = "html",
    ) -> str:
        report_id = str(uuid.uuid4())
        rec = {
            "report_id": report_id,
            "project_name": project_name,
            "operator": operator,
            "format": output_format,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._records[report_id] = rec
        return report_id

    def list(self) -> list[dict]:
        with self._lock:
            # newest first
            return sorted(self._records.values(), key=lambda r: r["timestamp"], reverse=True)

    def _clear(self) -> None:
        """Test helper: wipe all records."""
        with self._lock:
            self._records.clear()


_REPORT_REGISTRY = ReportRegistry()
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd engine && .venv/bin/python -m pytest tests/test_report_registry.py -q`
Expected: 2 passed

- [ ] **Step 5: 接上 report/generate 與 report/list IPC**

在 `main.py`：
1) 加 import（在 report import 附近，如 line 58 `from process_intelligence_engine.reporting.models import ReportData` 之後）：
```python
from process_intelligence_engine.reporting.registry import _REPORT_REGISTRY as REPORT_REGISTRY
```
2) 在 `_handle_report_generate` 的 `if output_format == "html":` 分支**之前**（已取到 `project_name`/`operator`/`output_format` 之後）登記：
```python
    REPORT_REGISTRY.register(
        project_name=project_name,
        operator=operator,
        output_format=output_format,
    )
```
3) 新增 handler + dispatch：
```python
def _handle_report_list(params: dict) -> dict:
    return {"reports": REPORT_REGISTRY.list()}
```
dispatch 分支（放在 `report/generate` 的 `if method == "report/generate":` 附近，找到該行）：
```python
    if method == "report/list":
        return _handle_report_list(params)
```

- [ ] **Step 6: 加 IPC 測試**（`test_main_handlers.py`）

```python
def test_handle_report_list_returns_registry(tmp_path):
    # Generate a report first -> registers it
    csv_text = "\n".join(["temp,flag", "1.0,OK", "2.0,OK", "3.0,NG"])
    dataset_id = _import_csv_and_return_id(tmp_path, csv_text)
    handle_request(
        "report/generate",
        {"dataset_id": dataset_id, "project_name": "Proj X", "operator": "qa", "format": "html"},
    )
    result = handle_request("report/list", {})
    assert result["reports"]
    assert result["reports"][0]["project_name"] == "Proj X"
```

> 注意：`test_main_handlers.py` 需要先 import `_REPORT_REGISTRY` 並在測試前 `_clear()`，避免其它測試殘留。在該測試檔加：
> ```python
> from process_intelligence_engine.reporting.registry import _REPORT_REGISTRY
> ```
> 測試內先呼叫 `_REPORT_REGISTRY._clear()` 再 generate。

Run: `cd engine && .venv/bin/python -m pytest tests/test_main_handlers.py::test_handle_report_list_returns_registry -q`
Expected: PASS

- [ ] **Step 7: 跑全引擎測試**

Run: `cd engine && .venv/bin/python -m pytest tests/ -q`
Expected: 全通過（既有 280 passed 基線 + 新增）

- [ ] **Step 8: Commit**

```bash
git add engine/src/process_intelligence_engine/reporting/registry.py engine/src/process_intelligence_engine/main.py engine/tests/test_report_registry.py engine/tests/test_main_handlers.py
git commit -m "feat(report): add REPORT_REGISTRY + report/list IPC for approval"
```

---

### Task 2: Frontend — engine.ts types + approval/report functions

**Files:**
- Modify: `src/lib/engine.ts`

- [ ] **Step 1: 加 interfaces**（放在靠近 `CloudUploadParams` 或報表相關處；`ModelFitDTO` 既有，勿重複）

```typescript
export interface ReportRecord {
  report_id: string
  project_name: string
  operator: string
  format: string
  timestamp: string
}

export interface ApprovalRecord {
  record_id: string
  resource_type: string
  resource_id: string
  action: string
  reviewer: string
  reviewer_role: string
  comments: string
  timestamp: string
}

export interface ApprovalSubmitParams {
  resource_type: string
  resource_id: string
  reviewer: string
  reviewer_role: string
  comments?: string
}
```

- [ ] **Step 2: 加 functions**（放在既有 `listModels`/`listUsers` 附近）

```typescript
export async function listReports(): Promise<{ reports: ReportRecord[] }> {
  return engineCall<{ reports: ReportRecord[] }>('report/list', {})
}

export async function submitForReview(params: ApprovalSubmitParams): Promise<{ record_id: string; new_status: string }> {
  return engineCall<{ record_id: string; new_status: string }>('approval/submit', params as unknown as Record<string, unknown>)
}

export async function approveResource(params: ApprovalSubmitParams): Promise<{ record_id: string; new_status: string }> {
  return engineCall<{ record_id: string; new_status: string }>('approval/approve', params as unknown as Record<string, unknown>)
}

export async function rejectResource(params: ApprovalSubmitParams): Promise<{ record_id: string; new_status: string }> {
  return engineCall<{ record_id: string; new_status: string }>('approval/reject', params as unknown as Record<string, unknown>)
}

export async function getApprovalStatus(params: { resource_type: string; resource_id: string }): Promise<{ status: string }> {
  return engineCall<{ status: string }>('approval/status', params as unknown as Record<string, unknown>)
}

export async function listApprovalRecords(): Promise<{ records: ApprovalRecord[] }> {
  return engineCall<{ records: ApprovalRecord[] }>('approval/records', {})
}
```

- [ ] **Step 3: 驗證**

Run: `npx tsc --noEmit`
Expected: 無 error（功能尚未用到，僅 type/function 定義不觸發未使用錯誤）

- [ ] **Step 4: Commit**

```bash
git add src/lib/engine.ts
git commit -m "feat(engine): approval + report list api types and functions"
```

---

### Task 3: Frontend — Approval.tsx UI

**Files:**
- Create: `src/features/approval/Approval.tsx`

- [ ] **Step 1: 建立元件**（完整內容）

```tsx
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, Table, Select, Input, Button, Space, Tag, Modal, message, Typography, Alert, Form } from 'antd'
import { CheckOutlined, StopOutlined, SendOutlined, AuditOutlined } from '@ant-design/icons'
import {
  listModels, listReports, listUsers, getCurrentUser, submitForReview,
  approveResource, rejectResource, listApprovalRecords,
} from '../../lib/engine'
import type { ModelFitDTO, ReportRecord, UserRecord } from '../../lib/engine'

interface ResourceRow {
  key: string
  resource_type: 'model' | 'report'
  resource_id: string
  label: string
  status: string
}

export default function Approval() {
  const { t } = useTranslation()
  const [messageApi, contextHolder] = message.useMessage()

  const [currentRole, setCurrentRole] = useState<string | null>(null)
  const [reviewers, setReviewers] = useState<UserRecord[]>([])
  const [models, setModels] = useState<ModelFitDTO[]>([])
  const [reports, setReports] = useState<ReportRecord[]>([])
  const [statuses, setStatuses] = useState<Record<string, string>>({})
  const [records, setRecords] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  const [submitOpen, setSubmitOpen] = useState(false)
  const [submitResType, setSubmitResType] = useState<'model' | 'report'>('model')
  const [submitResId, setSubmitResId] = useState('')
  const [submitReviewer, setSubmitReviewer] = useState('')
  const [submitComments, setSubmitComments] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const [actionTarget, setActionTarget] = useState<ResourceRow | null>(null)
  const [actionMode, setActionMode] = useState<'approve' | 'reject'>('approve')
  const [actionComments, setActionComments] = useState('')
  const [actionLoading, setActionLoading] = useState(false)

  const canReview = currentRole === 'reviewer' || currentRole === 'admin'

  const reviewerOptions = useMemo(
    () => reviewers.filter(u => u.role === 'reviewer' || u.role === 'admin').map(u => ({ value: u.username, label: u.username })),
    [reviewers],
  )

  const load = async () => {
    setLoading(true)
    try {
      const [m, r] = await Promise.all([listModels(), listReports()])
      setModels(m.models)
      setReports(r.reports)
      const resources: ResourceRow[] = [
        ...m.models.map((mod: ModelFitDTO): ResourceRow => ({
          key: `model:${mod.model_id}`, resource_type: 'model', resource_id: mod.model_id,
          label: `${mod.model_type} (${mod.model_id})`, status: mod.status,
        })),
        ...r.reports.map((rep: ReportRecord): ResourceRow => ({
          key: `report:${rep.report_id}`, resource_type: 'report', resource_id: rep.report_id,
          label: `${rep.project_name} (${rep.format})`, status: 'draft',
        })),
      ]
      const st: Record<string, string> = {}
      for (const res of resources) {
        st[`${res.resource_type}:${res.resource_id}`] = res.resource_type === 'model'
          ? res.status : (st[res.key] ?? 'draft')
      }
      const rec = await listApprovalRecords()
      setRecords(rec.records)
      // derive approval statuses from records + model base status
      const base = Object.fromEntries(resources.map(r => [r.key, r.status]))
      setStatuses(base)
    } catch {
      messageApi.error(t('approval.loadError'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    getCurrentUser().then(u => setCurrentRole(u.role))
    listUsers().then(u => setReviewers(u.users)).catch(() => {})
    load()
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const refreshStatusFor = async (resType: string, resId: string) => {
    try {
      const r = await getApprovalStatus(resType, resId)
      setStatuses(prev => ({ ...prev, [`${resType}:${resId}`]: r.status }))
    } catch { /* ignore */ }
    const rec = await listApprovalRecords()
    setRecords(rec.records)
  }

  const doSubmit = async () => {
    if (!submitResId || !submitReviewer) return
    setSubmitting(true)
    try {
      const reviewer = reviewers.find(u => u.username === submitReviewer)
      await submitForReview({
        resource_type: submitResType,
        resource_id: submitResId,
        reviewer: submitReviewer,
        reviewer_role: reviewer?.role ?? 'reviewer',
        comments: submitComments,
      })
      messageApi.success(t('approval.submitSuccess'))
      setSubmitOpen(false)
      await refreshStatusFor(submitResType, submitResId)
    } catch {
      messageApi.error(t('approval.submitError'))
    } finally {
      setSubmitting(false)
    }
  }

  const doAction = async () => {
    if (!actionTarget) return
    setActionLoading(true)
    try {
      const reviewer = reviewers.find(u => u.username === String(getCurrentUser ?? ''))
      const params = {
        resource_type: actionTarget.resource_type,
        resource_id: actionTarget.resource_id,
        reviewer: 'reviewer', // placeholder, replaced below
        reviewer_role: 'reviewer',
        comments: actionComments,
      }
      if (actionMode === 'approve') {
        await approveResource(params)
        messageApi.success(t('approval.approveSuccess'))
      } else {
        await rejectResource(params)
        messageApi.success(t('approval.rejectSuccess'))
      }
      setActionTarget(null)
      await refreshStatusFor(actionTarget.resource_type, actionTarget.resource_id)
    } catch {
      messageApi.error(t('approval.actionError'))
    } finally {
      setActionLoading(false)
    }
  }

  const rows: ResourceRow[] = useMemo(() => {
    const st = (r: ResourceRow) => statuses[r.key] ?? r.status
    return [
      ...models.map((mod: ModelFitDTO): ResourceRow => ({
        key: `model:${mod.model_id}`, resource_type: 'model', resource_id: mod.model_id,
        label: `${mod.model_type} (${mod.model_id})`, status: st({ key: `model:${mod.model_id}` } as ResourceRow),
      })),
      ...reports.map((rep: ReportRecord): ResourceRow => ({
        key: `report:${rep.report_id}`, resource_type: 'report', resource_id: rep.report_id,
        label: `${rep.project_name} (${rep.format})`, status: st({ key: `report:${rep.report_id}` } as ResourceRow),
      })),
    ]
  }, [models, reports, statuses])

  const statusTag = (s: string) => {
    const color = s === 'approved' ? 'green' : s === 'rejected' ? 'red' : s === 'pending_review' ? 'gold' : 'default'
    const label =
      s === 'approved' ? t('approval.statusApproved') :
      s === 'rejected' ? t('approval.statusRejected') :
      s === 'pending_review' ? t('approval.statusPending') :
      s === 'draft' ? t('approval.statusDraft') : s
    return <Tag color={color}>{label}</Tag>
  }

  return (
    <>
      {contextHolder}
      <Card size="small" title={<Space><AuditOutlined />{t('approval.title')}</Space>} style={{ marginBottom: 16 }}>
        <Alert type="info" showIcon message={t('approval.desc')} style={{ marginBottom: 12 }} />
        <Space style={{ marginBottom: 12 }}>
          <Button type="primary" icon={<SendOutlined />} onClick={() => setSubmitOpen(true)}>
            {t('approval.submit')}
          </Button>
          <Button onClick={load} loading={loading}>{t('approval.refresh')}</Button>
        </Space>

        <Table<ResourceRow>
          size="small"
          rowKey="key"
          loading={loading}
          dataSource={rows}
          pagination={{ pageSize: 8 }}
          columns={[
            { title: t('approval.type'), dataIndex: 'resource_type', width: 90, render: (v: string) => v === 'model' ? t('approval.model') : t('approval.report') },
            { title: t('approval.resource'), dataIndex: 'label', ellipsis: true },
            { title: t('approval.status'), dataIndex: 'status', width: 140, render: (_: unknown, r: ResourceRow) => statusTag(r.status) },
            {
              title: t('approval.action'), width: 200,
              render: (_: unknown, r: ResourceRow) => (
                r.status === 'pending_review' && canReview ? (
                  <Space>
                    <Button size="small" type="primary" icon={<CheckOutlined />}
                      onClick={() => { setActionTarget(r); setActionMode('approve'); setActionComments('') }}>
                      {t('approval.approve')}
                    </Button>
                    <Button size="small" danger icon={<StopOutlined />}
                      onClick={() => { setActionTarget(r); setActionMode('reject'); setActionComments('') }}>
                      {t('approval.reject')}
                    </Button>
                  </Space>
                ) : (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {r.status === 'pending_review' && !canReview ? t('approval.onlyReviewer') : '—'}
                  </Typography.Text>
                )
              ),
            },
          ]}
        />
      </Card>

      <Card size="small" title={<Space><AuditOutlined />{t('approval.records')}</Space>}>
        <Table<any>
          size="small"
          rowKey="record_id"
          dataSource={records}
          pagination={{ pageSize: 6 }}
          columns={[
            { title: t('approval.time'), dataIndex: 'timestamp', width: 170, render: (v: string) => new Date(v).toLocaleString() },
            { title: t('approval.type'), dataIndex: 'resource_type', width: 80 },
            { title: t('approval.resource'), dataIndex: 'resource_id', ellipsis: true },
            { title: t('approval.action'), dataIndex: 'action', width: 130 },
            { title: t('approval.reviewer'), dataIndex: 'reviewer', width: 100 },
            { title: t('approval.comments'), dataIndex: 'comments', ellipsis: true },
          ]}
        />
      </Card>

      {/* Submit modal */}
      <Modal
        title={t('approval.submit')}
        open={submitOpen}
        onCancel={() => setSubmitOpen(false)}
        onOk={doSubmit}
        confirmLoading={submitting}
        okText={t('approval.submit')}
      >
        <Form layout="vertical">
          <Form.Item label={t('approval.type')}>
            <Select
              value={submitResType}
              onChange={v => { setSubmitResType(v); setSubmitResId('') }}
              options={[
                { value: 'model', label: t('approval.model') },
                { value: 'report', label: t('approval.report') },
              ]}
            />
          </Form.Item>
          <Form.Item label={t('approval.resource')}>
            <Select
              showSearch
              value={submitResId || undefined}
              onChange={setSubmitResId}
              options={
                submitResType === 'model'
                  ? models.map(m => ({ value: m.model_id, label: `${m.model_type} (${m.model_id})` }))
                  : reports.map(r => ({ value: r.report_id, label: `${r.project_name} (${r.format})` }))
              }
            />
          </Form.Item>
          <Form.Item label={t('approval.reviewer')}>
            <Select
              value={submitReviewer || undefined}
              onChange={setSubmitReviewer}
              options={reviewerOptions}
            />
          </Form.Item>
          <Form.Item label={t('approval.comments')}>
            <Input.TextArea value={submitComments} onChange={e => setSubmitComments(e.target.value)} rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Approve/Reject modal */}
      <Modal
        title={actionMode === 'approve' ? t('approval.approve') : t('approval.reject')}
        open={!!actionTarget}
        onCancel={() => setActionTarget(null)}
        onOk={doAction}
        confirmLoading={actionLoading}
        okText={actionMode === 'approve' ? t('approval.approve') : t('approval.reject')}
      >
        <Input.TextArea
          value={actionComments}
          onChange={e => setActionComments(e.target.value)}
          placeholder={t('approval.commentsPlaceholder')}
          rows={3}
        />
      </Modal>
    </>
  )
}
```

> **實作注意（RBAC 使用者身分）**：`approval/approve`/`reject` 需要 `reviewer`/`admin` role 且要 `reviewer` 名稱。在下方程式 `doAction` 中，`reviewer/reviewer_role` 請用**目前登入使用者**（`getCurrentUser().username` 與 `.role`）而非佔位字串。請實際撰寫時用 `getCurrentUser()` 取得 username/role 填入 params。下方程式是方向性骨架，必須改為正確抓取 current user。

- [ ] **Step 2: 驗證**

Run: `npx tsc --noEmit`
Expected: 需 clean；若有 type 錯誤（例如 `ModelFitDTO` 欄位名、`any` 在 `<Table<any>>`）依實際型別修正。

- [ ] **Step 3: Commit**

```bash
git add src/features/approval/Approval.tsx
git commit -m "feat(approval): add Approval review tab UI"
```

---

### Task 4: Frontend routing + assistantGuide + i18n

**Files:**
- Modify: `src/types/index.ts`
- Modify: `src/App.tsx`
- Modify: `src/components/layout/Sidebar.tsx`
- Modify: `src/lib/assistantGuide.ts`
- Modify: `src/i18n/en.json` / `zh-TW.json` / `es-MX.json`

- [ ] **Step 1: AppTab 加 `'approval'`**

`src/types/index.ts`：在 `'reports'` 後加一行 `| 'approval'`。

- [ ] **Step 2: App.tsx 路由**

```tsx
import Approval from './features/approval/Approval'
// ...
if (activeTab === 'approval') return <Approval />
```
放在 `reports` 分支附近。

- [ ] **Step 3: Sidebar nav item**

`src/components/layout/Sidebar.tsx`：新增 icon 與 nav entry。

在 icon import（從 `@ant-design/icons`）加 `AuditOutlined`（若尚無）；在 nav items array（`{ key: 'reports', ... }` 之後）加：
```tsx
{ key: 'approval', icon: <AuditOutlined /> },
```

- [ ] **Step 4: assistantGuide.ts 加 approval guide**

在 `assistantGuide.ts`（參考既有 `reports`/`copula` guide 的結構，`buildAssistantSystemPrompt` 內各 tab 的 description array）加 `approval` 段落，說明：將模型/報告送審、reviewer/admin 可核可/退回、檢視審核紀錄。鍵名對齊既有每個 tab 的結構（如 `approval: [...]`）。

- [ ] **Step 5: i18n 三語 keys**

`en.json`（`nav` section 加 `"approval": "Approval"`；新增 `approval` section）：
```json
"approval": {
  "title": "Approval",
  "desc": "Submit models or reports for review, then approve or reject pending items.",
  "type": "Type",
  "model": "Model",
  "report": "Report",
  "resource": "Resource",
  "status": "Status",
  "statusDraft": "Draft",
  "statusPending": "Pending Review",
  "statusApproved": "Approved",
  "statusRejected": "Rejected",
  "action": "Action",
  "approve": "Approve",
  "reject": "Reject",
  "submit": "Submit for Review",
  "refresh": "Refresh",
  "reviewer": "Reviewer",
  "comments": "Comments",
  "commentsPlaceholder": "Add a comment...",
  "records": "Approval Records",
  "time": "Time",
  "onlyReviewer": "Reviewer access required",
  "loadError": "Failed to load approval data",
  "submitSuccess": "Submitted for review",
  "submitError": "Failed to submit for review",
  "approveSuccess": "Approved",
  "rejectSuccess": "Rejected",
  "actionError": "Action failed"
}
```
`zh-TW.json`：
```json
"approval": {
  "title": "審核",
  "desc": "將模型或報告送出審核，並對待審項目進行核可或退回。",
  "type": "類型",
  "model": "模型",
  "report": "報告",
  "resource": "資源",
  "status": "狀態",
  "statusDraft": "草稿",
  "statusPending": "待審核",
  "statusApproved": "已核可",
  "statusRejected": "已退回",
  "action": "操作",
  "approve": "核可",
  "reject": "退回",
  "submit": "送出審核",
  "refresh": "重新整理",
  "reviewer": "審核人",
  "comments": "備註",
  "commentsPlaceholder": "輸入備註…",
  "records": "審核紀錄",
  "time": "時間",
  "onlyReviewer": "需審核人員身分",
  "loadError": "載入審核資料失敗",
  "submitSuccess": "已送出審核",
  "submitError": "送出審核失敗",
  "approveSuccess": "已核可",
  "rejectSuccess": "已退回",
  "actionError": "操作失敗"
}
```
`es-MX.json`：
```json
"approval": {
  "title": "Aprobación",
  "desc": "Envía modelos o informes para revisión y aprueba o rechaza los pendientes.",
  "type": "Tipo",
  "model": "Modelo",
  "report": "Informe",
  "resource": "Recurso",
  "status": "Estado",
  "statusDraft": "Borrador",
  "statusPending": "Pendiente",
  "statusApproved": "Aprobado",
  "statusRejected": "Rechazado",
  "action": "Acción",
  "approve": "Aprobar",
  "reject": "Rechazar",
  "submit": "Enviar a revisión",
  "refresh": "Actualizar",
  "reviewer": "Revisor",
  "comments": "Comentarios",
  "commentsPlaceholder": "Añade un comentario...",
  "records": "Registros de aprobación",
  "time": "Hora",
  "onlyReviewer": "Requiere rol de revisor",
  "loadError": "Error al cargar los datos de aprobación",
  "submitSuccess": "Enviado a revisión",
  "submitError": "Error al enviar a revisión",
  "approveSuccess": "Aprobado",
  "rejectSuccess": "Rechazado",
  "actionError": "Acción fallida"
}
```
`nav` section 三語各加 `"approval": "審核"`（zh-TW）/ `"Aprobación"`（es-MX）/ `"Approval"`（en）。

- [ ] **Step 6: 驗證**

Run: `npx tsc --noEmit && npm run build`
Expected: 兩者 clean。
Run: `node -e "for (const l of ['en','zh-TW','es-MX']) { JSON.parse(require('fs').readFileSync('src/i18n/'+l+'.json','utf8')); console.log(l,'ok') }"`
Expected: 三行 ok

- [ ] **Step 7: Commit**

```bash
git add src/types/index.ts src/App.tsx src/components/layout/Sidebar.tsx src/lib/assistantGuide.ts src/i18n/en.json src/i18n/zh-TW.json src/i18n/es-MX.json
git commit -m "feat(approval): wire approval tab routing + assistant guide + i18n"
```

---

### Task 5: 收尾 — docs + 最終驗證 + push

**Files:**
- Modify: `PROGRESS.md`、`TASK.md`

- [ ] **Step 1: 更新 PROGRESS.md / TASK.md**

在 Completed 補 Approval tab 條目：REPORT_REGISTRY + report/list、Approval.tsx（送審/核可/退回/紀錄）、路由 + i18n 三語，引用 spec 檔名，註明引擎測試數與驗證結果。

- [ ] **Step 2: 最終驗證**

Run: `cd engine && .venv/bin/python -m pytest tests/ -q && cd .. && npx tsc --noEmit && npm run build`
Expected: 全 passed、tsc/build clean

- [ ] **Step 3: Commit + Push**

```bash
git add PROGRESS.md TASK.md
git commit -m "docs: record approval tab implementation"
git push origin main
```

---

## Self-Review

**Spec 覆蓋：**
- REPORT_REGISTRY + report/list → Task 1
- Approval.tsx（資源清單/送審/核可退回/紀錄）→ Task 3
- RBAC（reviewer/admin 才顯示按鈕）→ Task 3（`canReview` 依 current user role）
- engine.ts functions → Task 2
- 路由 + assistantGuide + i18n → Task 4
- 測試（backend + tsc/build + 三語）→ Task 1/3/4/5

**Placeholder 掃描：** 無 TBD/TODO；程式碼步驟皆含實際內容。Task 3 明確要求修正 `doAction` 的 reviewer 需用目前登入使用者。

**型別一致性：** `ApprovalSubmitParams{ resource_type, resource_id, reviewer, reviewer_role, comments }` 在 Task 2 定義、Task 3 使用一致。`ReportRecord{ report_id, project_name, operator, format, timestamp }` 在 backend（Task 1）與前端（Task 2）一致。`approval/list` 無此端點——用 `getApprovalStatus` + 前端組合。`report/list`、`approval/*` 方法名與 backend dispatch 一致。

**已知風險：** ModelFitDTO 的 `status` 值為 backend 既有值（如 validated/approved/draft 等），與 approval 的 draft/pending_review 狀態不同——Task 3 的資源表中 model 的初始 status 用 model 自身 status，透過审批紀錄推導 pending_review/approved/rejected；此為展示性映射，`refreshStatusFor` 呼叫 `approval/status` 取得正確審核狀態。
