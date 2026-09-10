import { Modal, Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import type { AppTab } from '../../types'

interface Props { open: boolean; tab: AppTab; subtab?: string; onClose: () => void }

export default function GuideModal({ open, tab, subtab, onClose }: Props) {
  const { t } = useTranslation()
  const key = `guide.${tab}${subtab ? `.${subtab}` : ''}`
  return <Modal open={open} title={t(`${key}.title`, { defaultValue: t('guide.generic.title') })} onCancel={onClose} onOk={onClose} width={720}>
    <Typography.Paragraph><Typography.Text strong>{t('guide.labels.purpose')}</Typography.Text><br />{t(`${key}.purpose`, { defaultValue: t('guide.generic.purpose') })}</Typography.Paragraph>
    <Typography.Paragraph><Typography.Text strong>{t('guide.labels.principle')}</Typography.Text><br />{t(`${key}.principle`, { defaultValue: t('guide.generic.principle') })}</Typography.Paragraph>
    <Typography.Paragraph><Typography.Text strong>{t('guide.labels.formula')}</Typography.Text><br />{t(`${key}.formula`, { defaultValue: t('guide.generic.formula') })}</Typography.Paragraph>
    <Typography.Paragraph><Typography.Text strong>{t('guide.labels.interpretation')}</Typography.Text><br />{t(`${key}.interpretation`, { defaultValue: t('guide.generic.interpretation') })}</Typography.Paragraph>
    <Typography.Paragraph><Typography.Text strong>{t('guide.labels.limits')}</Typography.Text><br />{t(`${key}.limits`, { defaultValue: t('guide.generic.limits') })}</Typography.Paragraph>
    <Typography.Paragraph><Typography.Text strong>{t('guide.labels.recommendation')}</Typography.Text><br />{t(`${key}.recommendation`, { defaultValue: t('guide.generic.recommendation') })}</Typography.Paragraph>
  </Modal>
}
