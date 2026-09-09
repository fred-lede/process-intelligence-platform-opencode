import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, Button, Space, Alert, message, Tag, List, Popconfirm, Typography } from 'antd'
import { FileTextOutlined, DownloadOutlined, DeleteOutlined } from '@ant-design/icons'
import { save } from '@tauri-apps/plugin-dialog'
import { writeTextFile, writeFile } from '@tauri-apps/plugin-fs'
import { useDataPipelineStore } from '../../stores/dataPipelineStore'
import { useModelStore } from '../../stores/modelStore'
import { useAssistantContextStore } from '../../stores/assistantContextStore'
import { generateReport, listReports, exportReport, deleteReport, runReadiness, type ReportRecord } from '../../lib/engine'
import { buildReportsContext } from '../../lib/assistantData'

export default function Report() {
  const { t } = useTranslation()
  const [messageApi, contextHolder] = message.useMessage()
  const { importResult, spec, fields } = useDataPipelineStore()
  const { models } = useModelStore()
  const { setContext } = useAssistantContextStore()

  const [generating, setGenerating] = useState(false)
  const [savedReports, setSavedReports] = useState<ReportRecord[]>([])
  useEffect(() => { listReports().then(r => setSavedReports(r.reports)).catch(e => messageApi.error(String(e))) }, [])
  const openSaved = async (id: string) => {
    try {
      const result = await exportReport(id)
      setReportHtml(result.content)
      setLastFormat('html')
    } catch (e) { messageApi.error(String(e)) }
  }
  const removeSaved = async (id: string) => {
    try {
      await deleteReport(id)
      setSavedReports(reports => reports.filter(report => report.report_id !== id))
      if (reportHtml && savedReports.find(report => report.report_id === id)) setReportHtml(null)
      messageApi.success(t('report.deleteSuccess'))
    } catch (e) { messageApi.error(t('report.deleteError')) }
  }
  const [reportHtml, setReportHtml] = useState<string | null>(null)
  const [lastFormat, setLastFormat] = useState<'html' | 'pdf' | 'excel' | null>(null)

  const saveReportOutput = async (format: 'html' | 'pdf' | 'excel', result: { content?: string; content_base64?: string }) => {
    const ext = format === 'html' ? 'html' : format === 'pdf' ? 'pdf' : 'xlsx'
    const target = await save({
      title: t('report.saveOutput'),
      defaultPath: `process-analysis-report.${ext}`,
      filters: [{ name: ext.toUpperCase(), extensions: [ext] }],
    })
    if (!target) return false
    if (format === 'html') {
      await writeTextFile(target, result.content ?? '')
    } else {
      const raw = atob(result.content_base64 ?? '')
      const bytes = Uint8Array.from(raw, char => char.charCodeAt(0))
      await writeFile(target, bytes)
    }
    messageApi.success(t('report.savedTo', { path: target }))
    return true
  }

  useEffect(() => {
    setContext('reports', buildReportsContext(!!lastFormat, lastFormat ?? ''))
  }, [lastFormat, setContext])

  const datasetId = importResult?.dataset_id
  const modelIds = models.map(m => m.model_id)

  const handleGenerate = async (format: 'html' | 'pdf' | 'excel') => {
    if (!datasetId) {
      messageApi.error(t('report.noData'))
      return
    }

    setGenerating(true)
    try {
      const readiness = fields.length ? await runReadiness(datasetId, fields.filter(f => f.role === 'input' || f.role === 'output').map(f => ({ name: f.originalName, role: f.role }))) : undefined
      const result = await generateReport({
        project_name: 'Process Analysis Report',
        operator: 'Fred Wang',
        dataset_id: datasetId,
        model_ids: modelIds.length > 0 ? modelIds : undefined,
        format,
        spec: (spec as unknown as Record<string, unknown>) ?? undefined,
        lsl: spec?.lsl,
        usl: spec?.usl,
        runs_length: 5,
        n_simulations: 10000,
        seed: 42,
        enable_anomalies: true,
        readiness_snapshot: readiness,
      })

      if (format === 'html' && result.content) {
        setReportHtml(result.content)
      }
      await saveReportOutput(format, result)

      messageApi.success(t('report.generateSuccess'))
      setSavedReports((await listReports()).reports)
      setLastFormat(format)
    } catch (err) {
      messageApi.error(t('report.generateError'))
    } finally {
      setGenerating(false)
    }
  }

  if (!datasetId && !savedReports.length) {
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
          {savedReports.length > 0 && <Card type="inner" title={t('report.savedReports')} style={{ marginBottom: 16 }}>
            <List
              size="small"
              dataSource={savedReports}
              renderItem={r => <List.Item actions={[
                <Button key="open" type="link" onClick={() => void openSaved(r.report_id)}>{t('report.open')}</Button>,
                <Popconfirm key="delete" title={t('report.deleteConfirm')} onConfirm={() => void removeSaved(r.report_id)} okText={t('common.delete')} cancelText={t('common.cancel')}>
                  <Button type="link" danger icon={<DeleteOutlined />}>{t('common.delete')}</Button>
                </Popconfirm>,
              ]}><List.Item.Meta title={r.project_name} description={<Typography.Text type="secondary">{r.report_id.slice(0, 12)} · {r.format.toUpperCase()} · {new Date(r.timestamp).toLocaleString()}{r.grain?.filter_column ? ` · ${r.grain.filter_column}=${r.grain.filter_value}` : ''}{r.readiness_status ? ` · ${t('report.readinessStatus')}: ${r.readiness_status}` : ''}</Typography.Text>} /></List.Item>}
            />
          </Card>}
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
