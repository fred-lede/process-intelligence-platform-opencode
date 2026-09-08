import { Alert, Button, Card, Space, Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import type { AssistantActionDraft } from '../../lib/engine'

interface ActionDraftCardProps {
  draft: AssistantActionDraft
  busy: boolean
  disabled: boolean
  error?: string
  onConfirm: () => void
  onCancel: () => void
}

export default function ActionDraftCard({ draft, busy, disabled, error, onConfirm, onCancel }: ActionDraftCardProps) {
  const { t } = useTranslation()
  return (
    <Card size="small" title={t('assistant.actionDraft', { defaultValue: 'Action draft' })}>
      <Space direction="vertical" style={{ width: '100%', overflowWrap: 'anywhere' }}>
        <Typography.Text code>{draft.draft_id}</Typography.Text>
        <div>{draft.method}</div>
        <div>{t('assistant.impact', { defaultValue: 'Impact' })}: {draft.impact}</div>
        <div>{t('assistant.expectedResult', { defaultValue: 'Expected result' })}: {draft.expected_result}</div>
        <Typography.Text type="secondary">{t('assistant.draftPending', { defaultValue: 'The project changes only after you confirm.' })}</Typography.Text>
        {error && <Alert type="error" message={error} />}
        <Space wrap>
          <Button size="small" type="primary" loading={busy} disabled={disabled} onClick={onConfirm}>{t('common.confirm')}</Button>
          <Button size="small" disabled={busy || disabled} onClick={onCancel}>{t('common.cancel')}</Button>
        </Space>
      </Space>
    </Card>
  )
}
