import { useTranslation } from 'react-i18next'
import { Card, Result, Typography } from 'antd'

interface PlaceholderProps {
  tabKey: string
}

export default function FeaturePlaceholder({ tabKey }: PlaceholderProps) {
  const { t } = useTranslation()

  return (
    <Card>
      <Result
        status="info"
        title={t(`nav.${tabKey}`)}
        subTitle={`${t('common.notStarted')} — ${t('common.pendingConfirm')}`}
      />
      <Typography.Text type="secondary" style={{ display: 'block', textAlign: 'center' }}>
        {t('common.loading')}
      </Typography.Text>
    </Card>
  )
}
