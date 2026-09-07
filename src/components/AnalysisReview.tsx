import { useEffect, useState } from 'react'
import { Button, Card, Input, Modal, Space, Table, message } from 'antd'
import { useTranslation } from 'react-i18next'
import { confirmGate, getChainSummary, getChainTrace, type ChainEntitySummary } from '../lib/engine'

const modules: Record<string, string> = { dataset: 'data_import', model: 'modeling', simulation: 'monte_carlo', experiment: 'validation' }

export default function AnalysisReview({ onConfirmed }: { onConfirmed?: () => void }) {
  const { t } = useTranslation()
  const [rows, setRows] = useState<ChainEntitySummary[]>([])
  const [operator, setOperator] = useState('')
  const [api, holder] = message.useMessage()
  const refresh = () => getChainSummary().then(setRows).catch(e => api.error(String(e)))
  useEffect(() => { void refresh() }, [])
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
    <Space><Input value={operator} onChange={e => setOperator(e.target.value)} placeholder={t('validationLab.column.operator')} />
      <Button onClick={() => void refresh()}>{t('common.refresh')}</Button></Space>
    <Table rowKey="entity_id" dataSource={rows.filter(r => modules[r.entity_type])} columns={[
      { title: 'ID', dataIndex: 'entity_id' },
      { title: t('project.analysisPhaseTitle'), render: (_, r) => t(`gates.${modules[r.entity_type]}`) },
      { title: 'Version', dataIndex: 'version' },
      { title: t('common.confirm'), render: (_, r) => <Button disabled={!operator.trim()} onClick={() => void review(r)}>{t('common.confirm')}</Button> },
    ]} />
  </Card>
}
