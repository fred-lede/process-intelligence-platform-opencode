import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Typography, Card, Button, Space, Alert, Badge, Row, Col, message } from 'antd'
import {
  PlusOutlined,
  FolderOpenOutlined,
  SaveOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { useEngineStatus } from '../../hooks/useEngineStatus'
import { importDataFile } from '../../lib/engine'
import { buildProjectFile, loadProjectFile, saveProjectFile } from '../../lib/project'
import { useDataPipelineStore } from '../../stores/dataPipelineStore'

export default function ProjectOverview() {
  const { t } = useTranslation()
  const { status, refresh } = useEngineStatus(5000)
  const [busy, setBusy] = useState(false)
  const [messageApi, contextHolder] = message.useMessage()
  const {
    importResult,
    fields,
    quality,
    spec,
    setImportResult,
    setFields,
    setQuality,
    setSpec,
    resetAll,
  } = useDataPipelineStore()

  const handleNew = () => {
    resetAll()
    messageApi.success(t('project.newDone'))
  }

  const handleSave = async () => {
    if (!importResult) {
      messageApi.warning(t('project.saveNoData'))
      return
    }
    setBusy(true)
    try {
      const data = buildProjectFile(
        importResult.file_path,
        fields,
        quality,
        spec,
      )
      const target = await saveProjectFile(data)
      if (target) messageApi.success(t('project.savedTo', { path: target }))
    } catch (err) {
      messageApi.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleOpen = async () => {
    setBusy(true)
    try {
      const data = await loadProjectFile()
      if (!data) return

      // Re-import the source file so the engine dataset is registered again.
      const result = await importDataFile(data.import.file_path)
      setImportResult(result)
      if (data.fields) setFields(data.fields)
      if (data.quality) setQuality(data.quality)
      if (data.spec) setSpec(data.spec)
      messageApi.success(t('project.opened', { path: data.import.file_path }))
    } catch (err) {
      messageApi.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const renderEngineStatus = () => {
    if (status.state === 'checking') {
      return <Badge status="processing" text={t('common.loading')} />
    }
    if (status.state === 'online') {
      return (
        <Badge
          status="success"
          text={`${t('engine.online')} · v${status.health.version}`}
        />
      )
    }
    return <Badge status="error" text={t('engine.offline')} />
  }

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      {contextHolder}
      <Card>
        <Row gutter={16}>
          <Col flex="auto">
            <Typography.Title level={3} style={{ margin: 0 }}>
              {t('project.welcome')}
            </Typography.Title>
          </Col>
          <Col>
            <Space>
              {renderEngineStatus()}
              <Button
                size="small"
                icon={<ReloadOutlined />}
                onClick={() => void refresh()}
              >
                {t('common.refresh')}
              </Button>
            </Space>
          </Col>
        </Row>
        <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>
          {t('project.welcomeSubtitle')}
        </Typography.Paragraph>
        <Space style={{ marginTop: 16 }}>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleNew}>
            {t('project.createNew')}
          </Button>
          <Button
            icon={<FolderOpenOutlined />}
            loading={busy}
            onClick={() => void handleOpen()}
          >
            {t('project.openExisting')}
          </Button>
          <Button
            icon={<SaveOutlined />}
            loading={busy}
            onClick={() => void handleSave()}
            disabled={!importResult}
          >
            {t('project.saveProject')}
          </Button>
        </Space>
      </Card>

      <Card title={t('project.engineTitle')} size="small">
        {status.state === 'offline' ? (
          <Alert
            type="error"
            showIcon
            message={t('engine.offlineMessage')}
            description={status.error}
          />
        ) : (
          <Typography.Text type="secondary">
            {t('project.engineDescription')}
          </Typography.Text>
        )}
      </Card>
    </Space>
  )
}