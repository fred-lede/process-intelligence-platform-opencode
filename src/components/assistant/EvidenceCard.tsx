import { Card, Space, Tag, Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import type { AssistantEvidence } from '../../lib/engine'

export default function EvidenceCard({ evidence, status }: { evidence: AssistantEvidence[]; status: string }) {
  const { t } = useTranslation()
  return (
    <Card size="small" title={t('assistant.evidence', { defaultValue: 'Evidence' })}>
      <Space direction="vertical" style={{ width: '100%', overflowWrap: 'anywhere' }}>
        <Tag color={status === 'confirmed' ? 'success' : 'warning'} style={{ whiteSpace: 'normal' }}>{status}</Tag>
        {evidence.length === 0 && <Typography.Text type="secondary">{t('assistant.noEvidence', { defaultValue: 'No traceable evidence cited.' })}</Typography.Text>}
        {evidence.map((item) => (
          <div key={item.evidence_id}>
            <Typography.Text code>{item.evidence_id}</Typography.Text>
            <div>{item.summary}</div>
            <Tag style={{ whiteSpace: 'normal' }}>{item.status}</Tag>
          </div>
        ))}
      </Space>
    </Card>
  )
}
