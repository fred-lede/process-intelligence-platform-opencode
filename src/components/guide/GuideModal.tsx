import { Modal, Table, Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import type { AppTab } from '../../types'
import { getGuideSection } from './guideContent'

interface Props { open: boolean; tab: AppTab; subtab?: string; onClose: () => void }

export default function GuideModal({ open, tab, subtab, onClose }: Props) {
  const { t, i18n } = useTranslation()
  const section = getGuideSection(tab, subtab, i18n.language)
  const subtabLabel = tab === 'exploration' && subtab ? (subtab === 'grr' ? t('grr.title') : t(`exploration.${subtab === 'timeseries' ? 'timeSeriesTab' : `${subtab}Tab`}`, { defaultValue: subtab })) : ''
  const title = `${t(`nav.${tab}`, { defaultValue: t('guide.generic.title') })}${subtabLabel ? ` - ${subtabLabel}` : ''}`
  const isZh = i18n.language.toLowerCase().startsWith('zh')
  const isEs = i18n.language.toLowerCase().startsWith('es')
  const contractTitle = isZh ? '建議的資料契約' : isEs ? 'Contrato de datos sugerido' : 'Suggested data contract'
  const contractHeaders = isZh ? ['類型', '範本基礎', '額外要求'] : isEs ? ['Tipo', 'Plantilla base', 'Requisitos adicionales'] : ['Type', 'Template basis', 'Additional requirements']
  const contractData = (section.contract ?? []).map(([type, template, requirement], index) => ({ key: index, type, template, requirement }))
  return <Modal open={open} title={title} onCancel={onClose} onOk={onClose} width={720}>
    <Typography.Paragraph><Typography.Text strong>{t('guide.labels.purpose')}</Typography.Text><br />{section.purpose}</Typography.Paragraph>
    <Typography.Paragraph><Typography.Text strong>{i18n.language.toLowerCase().startsWith('zh') ? '操作步驟' : i18n.language.toLowerCase().startsWith('es') ? 'Pasos' : 'Steps'}</Typography.Text><br />{section.steps}</Typography.Paragraph>
    {contractData.length > 0 && <Typography.Paragraph><Typography.Text strong>{contractTitle}</Typography.Text><Table size="small" pagination={false} dataSource={contractData} columns={[{ title: contractHeaders[0], dataIndex: 'type', key: 'type' }, { title: contractHeaders[1], dataIndex: 'template', key: 'template' }, { title: contractHeaders[2], dataIndex: 'requirement', key: 'requirement' }]} /></Typography.Paragraph>}
    <Typography.Paragraph><Typography.Text strong>{t('guide.labels.principle')}</Typography.Text><br />{section.principle}</Typography.Paragraph>
    <Typography.Paragraph><Typography.Text strong>{t('guide.labels.formula')}</Typography.Text><br />{section.formula}</Typography.Paragraph>
    <Typography.Paragraph><Typography.Text strong>{t('guide.labels.interpretation')}</Typography.Text><br />{section.interpretation}</Typography.Paragraph>
    <Typography.Paragraph><Typography.Text strong>{t('guide.labels.limits')}</Typography.Text><br />{section.limits}</Typography.Paragraph>
    <Typography.Paragraph><Typography.Text strong>{t('guide.labels.recommendation')}</Typography.Text><br />{section.recommendation}</Typography.Paragraph>
  </Modal>
}
