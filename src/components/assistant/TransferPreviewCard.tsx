import { Alert, Button, Card, Space, Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import type { AssistantCloudTransferPreview } from '../../lib/engine'

interface TransferPreviewCardProps {
  preview: AssistantCloudTransferPreview
  busy: boolean
  error?: string
  onConfirm: () => void
  onCancel: () => void
}

export default function TransferPreviewCard({ preview, busy, error, onConfirm, onCancel }: TransferPreviewCardProps) {
  const { t } = useTranslation()
  return (
    <Card size="small" title={t('assistant.transferPreview', { defaultValue: 'Cloud transfer preview' })}>
      <Space direction="vertical" style={{ width: '100%', overflowWrap: 'anywhere' }}>
        <div>{t('assistant.provider', { defaultValue: 'Provider' })}: {preview.provider}</div>
        <div>{t('assistant.maskedPaths', { defaultValue: 'Masked paths' })}: {preview.masked_fields.join(', ') || t('assistant.none', { defaultValue: 'None' })}</div>
        <div>{t('assistant.numericPolicy', { defaultValue: 'Numeric policy' })}: {preview.numeric_policy}</div>
        <div>{t('assistant.payloadHash', { defaultValue: 'Payload hash' })}: <Typography.Text code>{preview.payload_hash}</Typography.Text></div>
        <Typography.Text type="secondary">{t('assistant.transferConsent', { defaultValue: 'Confirm to authorize this project and send this previewed request.' })}</Typography.Text>
        {error && <Alert type="error" message={error} />}
        <Space wrap>
          <Button size="small" type="primary" loading={busy} onClick={onConfirm}>{t('common.confirm')}</Button>
          <Button size="small" disabled={busy} onClick={onCancel}>{t('common.cancel')}</Button>
        </Space>
      </Space>
    </Card>
  )
}
