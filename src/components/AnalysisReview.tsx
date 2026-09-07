import { useEffect, useState } from 'react'
import { Button, Card, Input, Modal, Space, Table, message } from 'antd'
import { useTranslation } from 'react-i18next'
import { confirmGate, getChainSummary, getChainTrace, type ChainEntitySummary } from '../lib/engine'

const modules: Record<string, string> = { dataset: 'data_import', model: 'modeling', simulation: 'monte_carlo', experiment: 'validation' }

function latestReviewRows(rows: ChainEntitySummary[]) {
  const latest = new Map<string, ChainEntitySummary>()
  rows.filter((row) => modules[row.entity_type]).forEach((row) => {
    const current = latest.get(row.entity_type)
    if (!current || row.version > current.version) latest.set(row.entity_type, row)
  })
  return Object.keys(modules).map((entityType) => latest.get(entityType)).filter((row): row is ChainEntitySummary => Boolean(row))
}

export default function AnalysisReview({ projectOpen, onConfirmed }: { projectOpen: boolean; onConfirmed?: () => void }) {
  const { t } = useTranslation()
  const [rows, setRows] = useState<ChainEntitySummary[]>([])
  const [operator, setOperator] = useState('')
  const [api, holder] = message.useMessage()
  const refresh = () => {
    if (!projectOpen) {
      setRows([])
      return Promise.resolve()
    }
    return getChainSummary().then(setRows).catch(e => api.error(String(e)))
  }
  useEffect(() => { void refresh() }, [projectOpen])
  const review = async (row: ChainEntitySummary) => {
    try {
      const trace = await getChainTrace(row.entity_id)
      Modal.confirm({ title: `${t('common.confirm')} · ${row.entity_id} · v${row.version}`,
        width: 720, content: <pre style={{ maxHeight: 400, overflow: 'auto' }}>{JSON.stringify(trace.metadata, null, 2)}</pre>,
        onOk: async () => { await confirmGate(modules[row.entity_type], row.entity_id, row.version, operator); api.success(t('gates.confirmed')); await refresh(); onConfirmed?.() },
      })
    } catch (e) { api.error(String(e)) }
  }
  return <Card title={t('project.analysisPhaseTitle')}>
    {holder}
    <Space><Input disabled={!projectOpen} value={operator} onChange={e => setOperator(e.target.value)} placeholder={t('validationLab.column.operator')} />
      <Button disabled={!projectOpen} onClick={() => void refresh()}>{t('common.refresh')}</Button></Space>
    <Table rowKey="entity_id" dataSource={latestReviewRows(rows)} locale={{ emptyText: projectOpen ? undefined : t('project.noActiveProject') }} columns={[
      { title: 'ID', dataIndex: 'entity_id' },
      { title: t('project.analysisPhaseTitle'), render: (_, r) => t(`gates.${modules[r.entity_type]}`) },
      { title: 'Version', dataIndex: 'version' },
      { title: t('common.confirm'), render: (_, r) => <Button disabled={!projectOpen || !operator.trim()} onClick={() => void review(r)}>{t('common.confirm')}</Button> },
    ]} />
  </Card>
}
