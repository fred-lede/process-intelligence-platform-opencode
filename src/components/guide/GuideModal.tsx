import { Modal, Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import type { AppTab } from '../../types'
import { getGuideSection } from './guideContent'

interface Props { open: boolean; tab: AppTab; subtab?: string; onClose: () => void }

export default function GuideModal({ open, tab, subtab, onClose }: Props) {
  const { t, i18n } = useTranslation()
  const section = getGuideSection(tab, subtab, i18n.language)
  return <Modal open={open} title={t(`nav.${tab}`, { defaultValue: t('guide.generic.title') })} onCancel={onClose} onOk={onClose} width={720}>
    <Typography.Paragraph><Typography.Text strong>{t('guide.labels.purpose')}</Typography.Text><br />{section.purpose}</Typography.Paragraph>
    <Typography.Paragraph><Typography.Text strong>{t('guide.labels.principle')}</Typography.Text><br />{section.principle}</Typography.Paragraph>
    <Typography.Paragraph><Typography.Text strong>{t('guide.labels.formula')}</Typography.Text><br />{section.formula}</Typography.Paragraph>
    <Typography.Paragraph><Typography.Text strong>{t('guide.labels.interpretation')}</Typography.Text><br />{section.interpretation}</Typography.Paragraph>
    <Typography.Paragraph><Typography.Text strong>{t('guide.labels.limits')}</Typography.Text><br />{section.limits}</Typography.Paragraph>
    <Typography.Paragraph><Typography.Text strong>{t('guide.labels.recommendation')}</Typography.Text><br />{section.recommendation}</Typography.Paragraph>
  </Modal>
}
