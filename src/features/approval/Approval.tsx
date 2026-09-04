import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Card, Table, Select, Button, Space, Tag, Modal, Alert, Typography, Form, Input, message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  CheckOutlined, CloseOutlined, SendOutlined, ReloadOutlined,
} from '@ant-design/icons'
import {
  getCurrentUser, listUsers, listModels, listReports, listApprovalRecords,
  getApprovalStatus, submitForReview, approveResource, rejectResource,
} from '../../lib/engine'
import type {
  ApprovalRecord, ApprovalResourceType, UserRole,
} from '../../lib/engine'

const { Text } = Typography
const { TextArea } = Input

interface ResourceRow {
  key: string
  resourceType: ApprovalResourceType
  resourceId: string
  label: string
  status: string
}

interface ReviewerOption {
  label: string
  value: string
  role: UserRole
}

const STATUS_TAG: Record<string, string> = {
  draft: 'default',
  pending_review: 'processing',
  approved: 'success',
  rejected: 'error',
  retired: 'warning',
}

export default function Approval() {
  const { t } = useTranslation()
  const [messageApi, contextHolder] = message.useMessage()

  const [currentRole, setCurrentRole] = useState<UserRole | null>(null)
  const [reviewers, setReviewers] = useState<ReviewerOption[]>([])
  const [models, setModels] = useState<Awaited<ReturnType<typeof listModels>>['models']>([])
  const [reports, setReports] = useState<Awaited<ReturnType<typeof listReports>>['reports']>([])
  const [approvalRecords, setApprovalRecords] = useState<ApprovalRecord[]>([])
  const [statuses, setStatuses] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)

  const [submitOpen, setSubmitOpen] = useState(false)
  const [submitType, setSubmitType] = useState<ApprovalResourceType>('model')
  const [submitResourceId, setSubmitResourceId] = useState<string | undefined>()
  const [submitReviewer, setSubmitReviewer] = useState<string | undefined>()
  const [submitComments, setSubmitComments] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const [actionModalOpen, setActionModalOpen] = useState(false)
  const [actionKind, setActionKind] = useState<'approve' | 'reject'>('approve')
  const [actionTarget, setActionTarget] = useState<ResourceRow | null>(null)
  const [actionComments, setActionComments] = useState('')
  const [actionLoading, setActionLoading] = useState(false)

  const canReview = currentRole === 'admin' || currentRole === 'engineer'

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [modelsRes, reportsRes, recordsRes] = await Promise.all([
        listModels(), listReports(), listApprovalRecords(),
      ])
      setModels(modelsRes.models)
      setReports(reportsRes.reports)
      setApprovalRecords(recordsRes.records)

      const s: Record<string, string> = {}
      for (const m of modelsRes.models) {
        try {
          const st = await getApprovalStatus({ resource_type: 'model', resource_id: m.model_id })
          s[`model:${m.model_id}`] = st.status
        } catch {
          s[`model:${m.model_id}`] = m.status
        }
      }
      for (const r of reportsRes.reports) {
        try {
          const st = await getApprovalStatus({ resource_type: 'report', resource_id: r.report_id })
          s[`report:${r.report_id}`] = st.status
        } catch {
          s[`report:${r.report_id}`] = 'draft'
        }
      }
      for (const rec of recordsRes.records) {
        if (rec.action === 'submit_for_review') {
          s[`${rec.resource_type}:${rec.resource_id}`] = 'pending_review'
        } else if (rec.action === 'approve') {
          s[`${rec.resource_type}:${rec.resource_id}`] = 'approved'
        } else if (rec.action === 'reject') {
          s[`${rec.resource_type}:${rec.resource_id}`] = 'rejected'
        }
      }
      setStatuses(s)
    } catch {
      messageApi.error(t('approval.loadError'))
    } finally {
      setLoading(false)
    }
  }, [messageApi, t])

  useEffect(() => {
    getCurrentUser().then((u) => setCurrentRole(u.role))
    listUsers().then((u) => {
      setReviewers(
        u.users
          .filter((r) => r.role === 'admin' || r.role === 'engineer')
          .map((r) => ({ label: `${r.username} (${r.role})`, value: r.username, role: r.role }))
      )
    })
    load()
  }, [load])

  const resources: ResourceRow[] = [
    ...models.map((m) => ({
      key: `model:${m.model_id}`,
      resourceType: 'model' as ApprovalResourceType,
      resourceId: m.model_id,
      label: `${m.model_type} (${m.model_id})`,
      status: statuses[`model:${m.model_id}`] ?? m.status,
    })),
    ...reports.map((r) => ({
      key: `report:${r.report_id}`,
      resourceType: 'report' as ApprovalResourceType,
      resourceId: r.report_id,
      label: `${r.project_name} (${r.format})`,
      status: statuses[`report:${r.report_id}`] ?? 'draft',
    })),
  ]

  const resourceColumns: ColumnsType<ResourceRow> = [
    {
      title: t('approval.type'),
      dataIndex: 'resourceType',
      width: 120,
      render: (v: ApprovalResourceType) => v === 'model' ? t('approval.model') : t('approval.report'),
    },
    {
      title: t('approval.resource'),
      dataIndex: 'label',
    },
    {
      title: t('approval.status'),
      dataIndex: 'status',
      width: 140,
      render: (s: string) => <Tag color={STATUS_TAG[s] ?? 'default'}>{t(`approval.status${s.charAt(0).toUpperCase() + s.slice(1)}`)}</Tag>,
    },
    {
      title: t('approval.action'),
      width: 180,
      render: (_: unknown, row: ResourceRow) => {
        if (row.status === 'pending_review' && canReview) {
          return (
            <Space>
              <Button size="small" type="primary" icon={<CheckOutlined />} onClick={() => openActionModal('approve', row)}>
                {t('approval.approve')}
              </Button>
              <Button size="small" danger icon={<CloseOutlined />} onClick={() => openActionModal('reject', row)}>
                {t('approval.reject')}
              </Button>
            </Space>
          )
        }
        if (row.status === 'pending_review' && !canReview) {
          return <Text type="secondary">{t('approval.onlyReviewer')}</Text>
        }
        return '—'
      },
    },
  ]

  const recordColumns: ColumnsType<ApprovalRecord> = [
    {
      title: t('approval.time'),
      dataIndex: 'timestamp',
      width: 200,
      render: (v: string) => new Date(v).toLocaleString(),
    },
    {
      title: t('approval.type'),
      dataIndex: 'resource_type',
      width: 120,
      render: (v: ApprovalResourceType) => v === 'model' ? t('approval.model') : t('approval.report'),
    },
    {
      title: t('approval.resource'),
      dataIndex: 'resource_id',
    },
    {
      title: t('approval.action'),
      dataIndex: 'action',
      width: 160,
      render: (v: string) => {
        if (v === 'submit_for_review') return t('approval.submit')
        if (v === 'approve') return t('approval.approve')
        return t('approval.reject')
      },
    },
    { title: t('approval.reviewer'), dataIndex: 'reviewer', width: 140 },
    { title: t('approval.comments'), dataIndex: 'comments' },
  ]

  const openActionModal = (kind: 'approve' | 'reject', row: ResourceRow) => {
    setActionKind(kind)
    setActionTarget(row)
    setActionComments('')
    setActionModalOpen(true)
  }

  const handleAction = async () => {
    if (!actionTarget) return
    setActionLoading(true)
    try {
      const user = await getCurrentUser()
      if (!user.username || !user.role) {
        messageApi.error(t('approval.loadError'))
        return
      }
      const params = {
        resource_type: actionTarget.resourceType,
        resource_id: actionTarget.resourceId,
        reviewer: user.username,
        reviewer_role: user.role,
        comments: actionComments || undefined,
      }
      if (actionKind === 'approve') {
        await approveResource(params)
        messageApi.success(t('approval.approveSuccess'))
      } else {
        await rejectResource(params)
        messageApi.success(t('approval.rejectSuccess'))
      }
      setActionModalOpen(false)
      await load()
    } catch {
      messageApi.error(t('approval.actionError'))
    } finally {
      setActionLoading(false)
    }
  }

  const handleSubmit = async () => {
    if (!submitResourceId || !submitReviewer) return
    setSubmitting(true)
    try {
      const reviewerOption = reviewers.find((r) => r.value === submitReviewer)
      await submitForReview({
        resource_type: submitType,
        resource_id: submitResourceId,
        reviewer: submitReviewer,
        reviewer_role: reviewerOption?.role ?? 'engineer',
        comments: submitComments || undefined,
      })
      messageApi.success(t('approval.submitSuccess'))
      setSubmitOpen(false)
      await load()
    } catch {
      messageApi.error(t('approval.submitError'))
    } finally {
      setSubmitting(false)
    }
  }

  const resourceOptions = submitType === 'model'
    ? models.map((m) => ({ label: `${m.model_type} (${m.model_id})`, value: m.model_id }))
    : reports.map((r) => ({ label: `${r.project_name} (${r.format})`, value: r.report_id }))

  return (
    <>
      {contextHolder}
      <Card
        title={t('approval.title')}
        extra={
          <Space>
            <Text type="secondary">{t('approval.desc')}</Text>
            <Button icon={<SendOutlined />} onClick={() => { setSubmitType('model'); setSubmitResourceId(undefined); setSubmitReviewer(undefined); setSubmitComments(''); setSubmitOpen(true) }}>
              {t('approval.submit')}
            </Button>
            <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
              {t('approval.refresh')}
            </Button>
          </Space>
        }
      >
        <Table<ResourceRow>
          dataSource={resources}
          columns={resourceColumns}
          rowKey="key"
          loading={loading}
          pagination={false}
          size="middle"
        />
      </Card>

      <Card title={t('approval.records')} style={{ marginTop: 16 }}>
        <Table<ApprovalRecord>
          dataSource={approvalRecords}
          columns={recordColumns}
          rowKey="record_id"
          loading={loading}
          pagination={{ pageSize: 10 }}
          size="small"
        />
      </Card>

      <Modal
        title={t('approval.submit')}
        open={submitOpen}
        onCancel={() => setSubmitOpen(false)}
        onOk={handleSubmit}
        confirmLoading={submitting}
        okText={t('approval.submit')}
      >
        <Form layout="vertical">
          <Form.Item label={t('approval.type')}>
            <Select
              value={submitType}
              onChange={(v: ApprovalResourceType) => { setSubmitType(v); setSubmitResourceId(undefined) }}
              options={[
                { label: t('approval.model'), value: 'model' },
                { label: t('approval.report'), value: 'report' },
              ]}
            />
          </Form.Item>
          <Form.Item label={t('approval.resource')}>
            <Select
              value={submitResourceId}
              onChange={setSubmitResourceId}
              options={resourceOptions}
              placeholder={t('approval.resource')}
            />
          </Form.Item>
          <Form.Item label={t('approval.reviewer')}>
            <Select
              value={submitReviewer}
              onChange={setSubmitReviewer}
              options={reviewers}
              placeholder={t('approval.reviewer')}
            />
          </Form.Item>
          <Form.Item label={t('approval.comments')}>
            <TextArea
              rows={3}
              value={submitComments}
              onChange={(e) => setSubmitComments(e.target.value)}
              placeholder={t('approval.commentsPlaceholder')}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={actionKind === 'approve' ? t('approval.approve') : t('approval.reject')}
        open={actionModalOpen}
        onCancel={() => setActionModalOpen(false)}
        onOk={handleAction}
        confirmLoading={actionLoading}
        okButtonProps={{ danger: actionKind === 'reject' }}
        okText={actionKind === 'approve' ? t('approval.approve') : t('approval.reject')}
      >
        {actionTarget && (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Alert type={actionKind === 'approve' ? 'success' : 'warning'} message={`${actionTarget.label}`} />
            <TextArea
              rows={3}
              value={actionComments}
              onChange={(e) => setActionComments(e.target.value)}
              placeholder={t('approval.commentsPlaceholder')}
            />
          </Space>
        )}
      </Modal>
    </>
  )
}
