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
import { openProject, getGateSummary, createProject, saveProjectUiState, saveProjectSession } from '../../lib/engine'
import { buildProjectFile, loadProjectFile, saveProjectFile, type ProjectFile } from '../../lib/project'
import { useDataPipelineStore } from '../../stores/dataPipelineStore'
import { useModelStore } from '../../stores/modelStore'
import AnalysisReview from '../../components/AnalysisReview'

export default function ProjectOverview({ onProjectChanged }: { onProjectChanged: (project: { name: string; root: string }) => void }) {
  const confirmableModules = ['data_import', 'modeling', 'monte_carlo', 'validation']
  const { t } = useTranslation()
  const { status, refresh } = useEngineStatus(5000)
  const [busy, setBusy] = useState(false)
  const [messageApi, contextHolder] = message.useMessage()
  const [gateSummary, setGateSummary] = useState<Record<string, string>>({})
  const [newProjectParent, setNewProjectParent] = useState<string | null>(null)
  const [newProjectName, setNewProjectName] = useState('')
  const [pendingImport, setPendingImport] = useState<{ filePath: string; projectFile: ProjectFile } | null>(null)
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
      let projectRoot = root
      let projectName = name
      if (pendingImport) {
        await openProject(pendingImport.filePath)
        const saved = await saveProjectSession(root, pendingImport.projectFile, name)
        projectRoot = saved.project_root
        const opened = await openProject(projectRoot)
        projectName = opened.project_name
        const data = opened.project_file
        const result = opened.import_result
        useModelStore.setState({ models: [], selectedModelId: null, error: null })
        resetAll()
        if (result) setImportResult(result)
        if (data?.fields) setFields(data.fields)
        if (data?.quality) setQuality(data.quality)
        if (data?.spec) setSpec(data.spec)
        if (data) restoreAnalysis({
          anomalyScenarios: data.anomalyScenarios ?? [],
          controlLimits: data.controlLimits ?? {},
          analysisPackage: data.analysisPackage ?? null,
        })
      } else {
        const created = await createProject({ root, name })
        projectRoot = created.project_root
        useModelStore.setState({ models: [], selectedModelId: null, error: null })
        resetAll()
      }
      const gateRes = await getGateSummary()
      setGateSummary(gateRes.summary || {})
      setNewProjectParent(null)
      setPendingImport(null)
      onProjectChanged({ name: projectName, root: projectRoot })
      messageApi.success(t('project.createdTo', { path: projectRoot }))
    } catch (err) {
      messageApi.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const buildCurrentProjectFile = () => {
    if (!importResult) return null
    return buildProjectFile(
      importResult.file_path,
      fields,
      quality,
      spec,
      anomalyScenarios,
      controlLimits,
      analysisPackage,
    )
  }

  const handleSave = async () => {
    const data = buildCurrentProjectFile()
    if (!data) {
      messageApi.warning(t('project.saveNoData'))
      return
    }
    setBusy(true)
    try {
      const saved = await saveProjectUiState(data)
      messageApi.success(t('project.savedTo', { path: saved.project_root }))
    } catch (err) {
      messageApi.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleExportSettings = async () => {
    if (!importResult) {
      messageApi.warning(t('project.saveNoData'))
      return
    }
    setBusy(true)
    try {
      const data = buildCurrentProjectFile()
      if (!data) return
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
      const selected = await open({
        title: t('project.openExisting'),
        multiple: false,
        directory: true,
      })
      if (!selected) return

      const opened = await openProject(selected)
      const data = opened.project_file
      const result = opened.import_result
      useModelStore.setState({ models: [], selectedModelId: null, error: null })
      resetAll()
      if (result) setImportResult(result)
      if (data?.fields) setFields(data.fields)
      if (data?.quality) setQuality(data.quality)
      if (data?.spec) setSpec(data.spec)
      if (data) restoreAnalysis({
        anomalyScenarios: data.anomalyScenarios ?? [],
        controlLimits: data.controlLimits ?? {},
        analysisPackage: data.analysisPackage ?? null,
      })
      const gateRes = await getGateSummary()
      setGateSummary(gateRes.summary || {})
      onProjectChanged({ name: opened.project_name, root: opened.project_root })
      messageApi.success(t('project.opened', { path: selected }))
    } catch (err) {
      messageApi.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleImportSettings = async () => {
    try {
      const selected = await loadProjectFile()
      if (!selected) return
      const parent = await open({
        title: t('project.selectParentDirectory'),
        multiple: false,
        directory: true,
      })
      if (typeof parent !== 'string') return
      setPendingImport({ filePath: selected.file_path, projectFile: selected })
      setNewProjectParent(parent)
      setNewProjectName('')
    } catch (err) {
      messageApi.error(err instanceof Error ? err.message : String(err))
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
            {t('project.saveCurrentProject')}
          </Button>
          <Button
            loading={busy}
            onClick={() => void handleExportSettings()}
            disabled={!importResult}
          >
            {t('project.exportSettings')}
          </Button>
          <Button
            loading={busy}
            onClick={() => void handleImportSettings()}
          >
            {t('project.importSettings')}
          </Button>
        </Space>
      </Card>

      <Modal
        title={pendingImport ? t('project.saveImportedProjectTitle') : t('project.newProjectTitle')}
        open={newProjectParent !== null}
        confirmLoading={busy}
        okText={pendingImport ? t('project.saveCurrentProject') : t('project.createNew')}
        onOk={() => void createNewProject()}
        onCancel={() => { setNewProjectParent(null); setPendingImport(null) }}
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
          {Object.entries(gateSummary).filter(([module]) => confirmableModules.includes(module)).map(([module, status]) => (
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
          {confirmableModules.filter(module => gateSummary[module] === 'confirmed').length}/{confirmableModules.length} {t('project.reviewableModulesConfirmed')}
        </Typography.Text>
      </Card>

      <AnalysisReview onConfirmed={() => { getGateSummary().then((res) => setGateSummary(res.summary || {})).catch(console.error) }} />
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
