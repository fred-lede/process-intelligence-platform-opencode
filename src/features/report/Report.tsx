import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, Button, Space, Alert, message, Tag } from 'antd'
import { FileTextOutlined, DownloadOutlined } from '@ant-design/icons'
import { useDataPipelineStore } from '../../stores/dataPipelineStore'
import { useModelStore } from '../../stores/modelStore'
import { generateReport } from '../../lib/engine'

export default function Report() {
  const { t } = useTranslation()
  const [messageApi, contextHolder] = message.useMessage()
  const { importResult } = useDataPipelineStore()
  const { models } = useModelStore()

  const [generating, setGenerating] = useState(false)
  const [reportHtml, setReportHtml] = useState<string | null>(null)

  const datasetId = importResult?.dataset_id
  const modelIds = models.map(m => m.model_id)

  const handleGenerate = async (format: 'html' | 'pdf' | 'excel') => {
    if (!datasetId) {
      messageApi.error(t('report.noData'))
      return
    }

    setGenerating(true)
    try {
      const result = await generateReport({
        project_name: 'Process Analysis Report',
        operator: 'Fred Wang',
        dataset_id: datasetId,
        model_ids: modelIds.length > 0 ? modelIds : undefined,
        format,
      })

      if (format === 'html' && result.content) {
        setReportHtml(result.content)
      } else if ((format === 'pdf' || format === 'excel') && result.content_base64) {
        const byteCharacters = atob(result.content_base64)
        const byteNumbers = new Array(byteCharacters.length)
        for (let i = 0; i < byteCharacters.length; i++) {
          byteNumbers[i] = byteCharacters.charCodeAt(i)
        }
        const byteArray = new Uint8Array(byteNumbers)
        const ext = format === 'pdf' ? 'pdf' : 'xlsx'
        const mimeType = format === 'pdf' ? 'application/pdf' : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        const blob = new Blob([byteArray], { type: mimeType })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `report.${ext}`
        a.click()
        URL.revokeObjectURL(url)
      }

      messageApi.success(t('report.generateSuccess'))
    } catch (err) {
      messageApi.error(t('report.generateError'))
    } finally {
      setGenerating(false)
    }
  }

  if (!datasetId) {
    return (
      <Card title={t('report.title')}>
        <Alert type="info" showIcon message={t('report.noData')} />
      </Card>
    )
  }

  return (
    <>
      {contextHolder}
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Card title={t('report.title')} extra={<FileTextOutlined />}>
          <Space direction="vertical" style={{ width: '100%' }}>
            <Alert
              type="info"
              message={t('report.info')}
              description={t('report.infoDetail')}
              showIcon
            />

            <Space>
              <Button
                type="primary"
                icon={<FileTextOutlined />}
                loading={generating}
                onClick={() => handleGenerate('html')}
              >
                {t('report.htmlButton')}
              </Button>
              <Button
                icon={<DownloadOutlined />}
                loading={generating}
                onClick={() => handleGenerate('pdf')}
              >
                {t('report.pdfButton')}
              </Button>
              <Button
                icon={<DownloadOutlined />}
                loading={generating}
                onClick={() => handleGenerate('excel')}
              >
                {t('report.excelButton')}
              </Button>
            </Space>

            {reportHtml && (
              <div style={{ marginTop: 20 }}>
                <Tag color="blue">{t('report.preview')}</Tag>
                <div
                  style={{
                    border: '1px solid #d9d9d9',
                    borderRadius: 4,
                    padding: 16,
                    marginTop: 8,
                    maxHeight: 600,
                    overflow: 'auto'
                  }}
                  dangerouslySetInnerHTML={{ __html: reportHtml }}
                />
              </div>
            )}
          </Space>
        </Card>
      </Space>
    </>
  )
}
