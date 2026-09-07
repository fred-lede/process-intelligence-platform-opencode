import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Typography, Card, Button, Space, Alert, Badge, Row, Col, message, Divider, Tag, Modal, Input } from 'antd'
import { open } from '@tauri-apps/plugin-dialog'
import {
  PlusOutlined,
  FolderOpenOutlined,
  SaveOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { useEngineStatus } from '../../hooks/useEngineStatus'
import { openProject, getGateSummary, createProject } from '../../lib/engine'
import { buildProjectFile, loadProjectFile, saveProjectFile } from '../../lib/project'
import { useDataPipelineStore } from '../../stores/dataPipelineStore'
import { useModelStore } from '../../stores/modelStore'
import AnalysisReview from '../../components/AnalysisReview'

export default function ProjectOverview() {
  const { t } = useTranslation()
  const { status, refresh } = useEngineStatus(5000)
  const [busy, setBusy] = useState(false)
  const [messageApi, contextHolder] = message.useMessage()
  const [gateSummary, setGateSummary] = useState<Record<string, string>>({})
  const [newProjectParent, setNewProjectParent] = useState<string | null>(null)
  const [newProjectName, setNewProjectName] = useState('')
  const {
    importResult,
    fields,
    quality,
    spec,
    controlLimits,
    anomalyScenarios,
    analysisPackage,
    setImportResult,
    setFields,
    setQuality,
    setSpec,
    restoreAnalysis,
    resetAll,
  } = useDataPipelineStore()

  useEffect(() => {
    getGateSummary().then((res) => {
      setGateSummary(res.summary || {})
    }).catch(console.error)
  }, [])

  const handleNew = async () => {
    const selected = await open({
      title: t('project.selectParentDirectory'),
      multiple: false,
      directory: true,
    })
    if (typeof selected === 'string') {
      setNewProjectParent(selected)
      setNewProjectName('')
    }
  }

  const createNewProject = async () => {
    const name = newProjectName.trim()
    if (!name || name === '.' || name === '..' || /[\\/]/.test(name)) {
      messageApi.warning(t('project.invalidProjectName'))
      return
    }
    if (!newProjectParent) return

    setBusy(true)
    try {
      const root = `${newProjectParent.replace(/[\\/]+$/, '')}/${name}`
      const created = await createProject({ root, name })
      useModelStore.setState({ models: [], selectedModelId: null, error: null })
      resetAll()
      const gateRes = await getGateSummary()
      setGateSummary(gateRes.summary || {})
      setNewProjectParent(null)
      messageApi.success(t('project.createdTo', { path: created.project_root }))
    } catch (err) {
      messageApi.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
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
        anomalyScenarios,
        controlLimits,
        analysisPackage,
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
      const selected = await loadProjectFile()
      if (!selected) return

      const opened = await openProject(selected.file_path)
      const data = opened.project_file
      const result = opened.import_result
      if (!data || !result) throw new Error('Invalid portable project response')
      useModelStore.setState({ models: [], selectedModelId: null, error: null })
      setImportResult(result)
      if (data.fields) setFields(data.fields)
      if (data.quality) setQuality(data.quality)
      if (data.spec) setSpec(data.spec)
      restoreAnalysis({
        anomalyScenarios: data.anomalyScenarios ?? [],
        controlLimits: data.controlLimits ?? {},
        analysisPackage: data.analysisPackage ?? null,
      })
      // Refresh gate summary (portable .piproj.json has no gate state)
      const gateRes = await getGateSummary()
      setGateSummary(gateRes.summary || {})
      messageApi.success(t('project.opened', { path: selected.file_path }))
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
          <Button type="primary" icon={<PlusOutlined />} onClick={() => void handleNew()}>
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

      <Modal
        title={t('project.newProjectTitle')}
        open={newProjectParent !== null}
        confirmLoading={busy}
        okText={t('project.createNew')}
        onOk={() => void createNewProject()}
        onCancel={() => setNewProjectParent(null)}
      >
        <Typography.Paragraph type="secondary">
          {newProjectParent}
        </Typography.Paragraph>
        <Input
          autoFocus
          value={newProjectName}
          onChange={(event) => setNewProjectName(event.target.value)}
          placeholder={t('project.projectNamePlaceholder')}
          onPressEnter={() => void createNewProject()}
        />
      </Modal>

      <Card title={t('project.analysisPhaseTitle')} size="small">
        <Row gutter={[16, 16]}>
          {Object.entries(gateSummary).map(([module, status]) => (
            <Col key={module} span={8}>
              <Space>
                <span>{t(`gates.${module}`)}</span>
                <Tag color={status === 'confirmed' ? 'green' : status === 'pending_confirmation' ? 'orange' : 'default'}>
                  {status === 'confirmed' ? t('gates.confirmed') : status === 'pending_confirmation' ? t('gates.pending') : t('gates.notStarted')}
                </Tag>
              </Space>
            </Col>
          ))}
        </Row>
        <Divider />
        <Typography.Text type="secondary">
          {Object.values(gateSummary).filter(s => s === 'confirmed').length}/{Object.keys(gateSummary).length} {t('project.modulesConfirmed')}
        </Typography.Text>
      </Card>

      <AnalysisReview />
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
