import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, Table, Form, Input, Select, Button, Space, Alert, Tag, Descriptions, Modal, message, InputNumber, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { UserOutlined, HistoryOutlined, CloudOutlined, CheckCircleOutlined, ReloadOutlined, ExperimentOutlined } from '@ant-design/icons'
import { login, logout, registerUser, getCurrentUser, getAuditLog, listUsers, getSettings, updateSettings, testConnection, listAIModels, enginePing, previewCloudUpload, confirmCloudUpload, listCloudUploadRecords, getDataAssets, detectFields, type UploadPreview, type UploadRecord, type DataAsset, type DetectedField } from '../../lib/engine'
import { useAIStore } from '../../stores/aiStore'
import type { UserRole, AuditEntry, UserRecord, AIProviderConfig } from '../../lib/engine'

export default function Settings() {
  const { t } = useTranslation()
  const [messageApi, contextHolder] = message.useMessage()

  const [currentUser, setCurrentUser] = useState<{ username: string | null; role: UserRole | null }>({ username: null, role: null })
  const [users, setUsers] = useState<UserRecord[]>([])
  const [auditLog, setAuditLog] = useState<AuditEntry[]>([])
  const [loading, setLoading] = useState(false)
  
  const [aiConfig, setAiConfig] = useState<AIProviderConfig>({
    provider: 'ollama',
    base_url: 'http://localhost:11434',
    api_key: '',
    model: 'gemma4:e2b-mlx',
    enabled: true,
    lightgbm_device: 'auto',
  })
  const [savingAI, setSavingAI] = useState(false)
  const [availableModels, setAvailableModels] = useState<string[]>([])
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ success: boolean; error?: string } | null>(null)

  const [aiForm] = Form.useForm()
  const [modelForm] = Form.useForm()
  const [loginForm] = Form.useForm()
  const [registerForm] = Form.useForm()
  const [showLoginModal, setShowLoginModal] = useState(false)
  const [showRegisterModal, setShowRegisterModal] = useState(false)

  // Cloud upload state
  const [cloudPreview, setCloudPreview] = useState<UploadPreview | null>(null)
  const [cloudLoading, setCloudLoading] = useState(false)
  const [cloudConfirmOpen, setCloudConfirmOpen] = useState(false)
  const [cloudConfirming, setCloudConfirming] = useState(false)
  const [cloudHistory, setCloudHistory] = useState<UploadRecord[]>([])
  const [cloudNoiseStd, setCloudNoiseStd] = useState(0)
  const [cloudPurpose, setCloudPurpose] = useState('')
  const [cloudProvider, setCloudProvider] = useState('custom')
  const [cloudModelVersion, setCloudModelVersion] = useState('unknown')
  const [cloudDatasets, setCloudDatasets] = useState<DataAsset[]>([])
  const [cloudDatasetId, setCloudDatasetId] = useState<string>('')
  const [cloudFields, setCloudFields] = useState<DetectedField[]>([])
  const [cloudLoadingFields, setCloudLoadingFields] = useState(false)
  const [cloudColClass, setCloudColClass] = useState<Record<string, 'transmit' | 'mask' | 'exclude'>>({})
  const [cloudColStrategy, setCloudColStrategy] = useState<Record<string, 'hash' | 'masked' | 'noise'>>({})

  useEffect(() => {
    loadData()
    loadSettings()
  }, [])

  useEffect(() => {
    getDataAssets()
      .then(res => setCloudDatasets(res.datasets))
      .catch(() => {})
  }, [])

  const loadCloudFields = async (datasetId: string) => {
    if (!datasetId) return
    setCloudLoadingFields(true)
    try {
      const res = await detectFields([], datasetId)
      const fields = res.fields
      setCloudFields(fields)
      const cls: Record<string, 'transmit' | 'mask' | 'exclude'> = {}
      const strat: Record<string, 'hash' | 'masked' | 'noise'> = {}
      for (const f of fields) {
        const isSensitive = f.role === 'sensitive' || f.role === 'identifier'
        cls[f.name] = isSensitive ? 'mask' : 'transmit'
        strat[f.name] = 'hash'
      }
      setCloudColClass(cls)
      setCloudColStrategy(strat)
    } catch {
      // engine may be unavailable in test
    } finally {
      setCloudLoadingFields(false)
    }
  }

  const deriveColumns = () => {
    const sensitive = Object.entries(cloudColClass).filter(([, c]) => c === 'mask').map(([n]) => n)
    const excluded = Object.entries(cloudColClass).filter(([, c]) => c === 'exclude').map(([n]) => n)
    const overrides: Record<string, string> = {}
    for (const n of sensitive) overrides[n] = cloudColStrategy[n] ?? 'hash'
    return { sensitive, excluded, overrides }
  }

  const loadSettings = async (retryCount = 0) => {
    try {
      await enginePing()
      const result = await getSettings()
      if (result.config) {
        setAiConfig(result.config)
        aiForm.setFieldsValue(result.config)
        modelForm.setFieldsValue(result.config)
      }
    } catch {
      if (retryCount < 5) {
        setTimeout(() => loadSettings(retryCount + 1), 500)
      }
    }
  }

  const [loadingModels, setLoadingModels] = useState(false)
  const loadModels = async (retryCount = 0) => {
    try {
      setLoadingModels(true)
      // Wait for engine to be ready
      try {
        await enginePing()
      } catch {
        if (retryCount < 5) {
          setTimeout(() => loadModels(retryCount + 1), 500)
          return
        }
      }
      const result = await listAIModels()
      if (result.success && result.models) {
        setAvailableModels(result.models)
      }
    } catch { /* ignore */ }
    finally {
      setLoadingModels(false)
    }
  }

  useEffect(() => {
    loadModels()
    if (aiConfig.provider === 'ollama') {
      aiForm.setFieldValue('model', 'gemma4:e2b-mlx')
      setAiConfig(prev => { const next = { ...prev, provider: 'ollama' as const, model: 'gemma4:e2b-mlx', api_key: '' }; console.log('[Settings] ollama:', next); return next })
    } else if (aiConfig.provider === 'openai') {
      aiForm.setFieldValue('model', 'gpt-4o')
      setAiConfig(prev => { const next = { ...prev, provider: 'openai' as const, model: 'gpt-4o' }; console.log('[Settings] openai:', next); return next })
    } else if (aiConfig.provider === 'custom') {
      aiForm.setFieldValue('model', '')
      setAiConfig(prev => { const next = { ...prev, provider: 'custom' as const, model: '' }; console.log('[Settings] custom:', next); return next })
    }
  }, [aiConfig.provider])

  const loadData = async (retryCount = 0) => {
    try {
      await enginePing()
      const [user, usersList, log] = await Promise.all([
        getCurrentUser(),
        listUsers(),
        getAuditLog(50),
      ])
      setCurrentUser(user)
      setUsers(usersList.users)
      setAuditLog(log.log)
    } catch (e) {
      if (retryCount < 5) {
        setTimeout(() => loadData(retryCount + 1), 500)
        return
      }
      console.error('[Settings] loadData error:', e)
      messageApi.error(e instanceof Error ? e.message : 'Failed to load data')
    }
  }

  const handleLogin = async (values: { username: string; password: string }) => {
    setLoading(true)
    try {
      const result = await login(values.username, values.password)
      if (result.success) {
        messageApi.success(`Logged in as ${result.username}`)
        setShowLoginModal(false)
        loginForm.resetFields()
        await loadData()
      } else {
        messageApi.error(result.error || 'Login failed')
      }
    } catch {
      messageApi.error('Login failed')
    } finally {
      setLoading(false)
    }
  }

  const handleRegister = async (values: { username: string; role: UserRole }) => {
    setLoading(true)
    try {
      const result = await registerUser(values.username, values.role)
      if (result.success) {
        messageApi.success(`User ${values.username} registered`)
        setShowRegisterModal(false)
        registerForm.resetFields()
        await loadData()
      }
    } catch {
      messageApi.error('Registration failed')
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = async () => {
    await logout()
    setCurrentUser({ username: null, role: null })
    messageApi.success('Logged out')
  }

  const handleSaveAIConfig = async () => {
    console.log('[Settings] Saving aiConfig:', aiConfig)
    setSavingAI(true)
    try {
      // Filter out masked keys before saving — never persist a masked value back
      const savePayload = { ...aiConfig }
      if (/^\w{3}\.\.\./.test(savePayload.api_key)) {
        delete savePayload.api_key
      }
      const result = await updateSettings(savePayload)
      console.log('[Settings] Save result:', result)
      if (result.success) {
        setAiConfig(result.config)
        aiForm.setFieldsValue(result.config)
        modelForm.setFieldsValue(result.config)
        useAIStore.getState().refreshHealth()
        messageApi.success(t('settings.saveSuccess'))
      }
    } catch (e) {
      console.error('[Settings] Save error:', e)
      messageApi.error(t('settings.saveFailed'))
    } finally {
      setSavingAI(false)
    }
  }

  const handleTestConnection = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const result = await testConnection()
      setTestResult(result)
      if (result.success) {
        messageApi.success(t('settings.connectionSuccess'))
      } else {
        messageApi.error(result.error || t('settings.connectionFailed'))
      }
    } catch (err) {
      setTestResult({ success: false, error: String(err) })
      messageApi.error(t('settings.connectionFailed'))
    } finally {
      setTesting(false)
    }
  }

  const roleColor = (role: UserRole) => {
    const colors: Record<UserRole, string> = { admin: 'red', engineer: 'blue', reviewer: 'purple', viewer: 'gray' }
    return colors[role] || 'default'
  }

  const userColumns: ColumnsType<UserRecord> = [
    { title: 'Username', dataIndex: 'username', key: 'username' },
    { title: 'Role', dataIndex: 'role', key: 'role', render: (role: UserRole) => <Tag color={roleColor(role)}>{role}</Tag> },
    { title: 'Created', dataIndex: 'created_at', key: 'created_at' },
  ]

  const auditColumns: ColumnsType<AuditEntry> = [
    { title: 'Time', dataIndex: 'timestamp', key: 'timestamp', width: 180 },
    { title: 'User', dataIndex: 'username', key: 'username', width: 100 },
    { title: 'Action', dataIndex: 'action', key: 'action', width: 120 },
    { title: 'Target', dataIndex: 'target', key: 'target' },
    { title: 'Details', dataIndex: 'details', key: 'details', render: (d: any) => JSON.stringify(d)?.substring(0, 50) },
  ]

  return (
    <>
      {contextHolder}
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Card title={t('settings.currentUser')} extra={
          currentUser.username ? (
            <Space>
              <Tag color={roleColor(currentUser.role!)}>{currentUser.role}</Tag>
              <Button size="small" onClick={handleLogout}>{t('settings.logout')}</Button>
            </Space>
          ) : (
            <Space>
              <Button type="primary" size="small" onClick={() => setShowLoginModal(true)}>
                {t('settings.login')}
              </Button>
              <Button size="small" onClick={() => setShowRegisterModal(true)}>
                {t('settings.register')}
              </Button>
            </Space>
          )
        }>
          {currentUser.username ? (
            <Descriptions column={1}>
              <Descriptions.Item label="Username">{currentUser.username}</Descriptions.Item>
              <Descriptions.Item label="Role">
                <Tag color={roleColor(currentUser.role!)}>{currentUser.role}</Tag>
              </Descriptions.Item>
            </Descriptions>
          ) : (
            <Alert type="info" message={t('settings.notLoggedIn')} showIcon />
          )}
        </Card>

        <Card title={<><UserOutlined /> {t('settings.users')}</>}>
          <Table size="small" rowKey="username" columns={userColumns} dataSource={users} pagination={false} />
        </Card>

        <Card title={<><HistoryOutlined /> {t('settings.auditLog')}</>}>
          <Table size="small" rowKey="id" columns={auditColumns} dataSource={auditLog} pagination={{ pageSize: 20 }} />
        </Card>

        <Card
          title={<><CloudOutlined /> {t('settings.aiProvider')}</>}
          extra={
            aiConfig.enabled ? (
              <Tag color="success" icon={<CheckCircleOutlined />}>{t('settings.enabled')}</Tag>
            ) : (
              <Tag color="default">{t('settings.disabled')}</Tag>
            )
          }
        >
          <Form
            form={aiForm}
            layout="vertical"
            onValuesChange={(_, changes) => { console.log('[Settings] onValuesChange:', changes); setAiConfig(prev => { const next = { ...prev, ...changes }; console.log('[Settings] merged:', next); return next as AIProviderConfig }) }}
          >
            <Form.Item name="provider" label={t('settings.providerType')}>
              <Select
                options={[
                  { value: 'ollama', label: 'Ollama (Local)' },
                  { value: 'openai', label: 'OpenAI' },
                  { value: 'azure', label: 'Azure OpenAI' },
                  { value: 'custom', label: 'Custom (OpenAI-compatible)' },
                ]}
              />
            </Form.Item>

            <Form.Item name="base_url" label={t('settings.baseUrl')}>
              <Input
                placeholder={
                  aiConfig.provider === 'ollama'
                    ? 'http://localhost:11434'
                    : 'https://api.openai.com'
                }
              />
            </Form.Item>

            <Form.Item name="api_key" label={t('settings.apiKey')}>
              <Input.Password placeholder={aiConfig.provider === 'ollama' ? t('settings.apiKeyOptional') : 'sk-...'} />
            </Form.Item>

            <Form.Item name="model" label={t('settings.model')}>
              <Select
                showSearch
                allowClear
                placeholder="Select or type model..."
                filterOption={false}
                options={availableModels.map(m => ({ value: m, label: m }))}
                onSearch={(val) => {
                  if (val && !availableModels.includes(val)) {
                    setAvailableModels(prev => [...prev, val])
                  }
                }}
              />
            </Form.Item>

            <Form.Item>
              <Space>
                <Button onClick={() => loadModels()} loading={loadingModels} icon={<ReloadOutlined />}>
                  {t('settings.refreshModels')}
                </Button>
                <Button type="primary" onClick={handleSaveAIConfig} loading={savingAI}>
                  {t('settings.save')}
                </Button>
                <Button onClick={handleTestConnection} loading={testing}>
                  {t('settings.testConnection')}
                </Button>
              </Space>
            </Form.Item>

            {testResult !== null && (
              <Alert
                type={testResult.success ? 'success' : 'error'}
                message={testResult.success ? t('settings.connectionSuccess') : t('settings.connectionFailed')}
                description={testResult.error}
                showIcon
                style={{ marginTop: 16 }}
              />
            )}
          </Form>
        </Card>

        <Card title={<><ExperimentOutlined /> {t('settings.modelSettings')}</>}>
          <Form
            form={modelForm}
            layout="vertical"
            style={{ maxWidth: 400 }}
            onValuesChange={(_, values) => setAiConfig(prev => ({ ...prev, ...values }))}
          >
            <Form.Item name="lightgbm_device" label={t('settings.lightgbmDevice')}>
              <Select
                options={[
                  { value: 'auto', label: t('settings.lightgbmDeviceAuto') },
                  { value: 'cpu', label: t('settings.lightgbmDeviceCpu') },
                  { value: 'gpu', label: t('settings.lightgbmDeviceGpu') },
                ]}
              />
            </Form.Item>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t('settings.lightgbmDeviceNote')}
            </Typography.Text>
            <Form.Item style={{ marginBottom: 0, marginTop: 8 }}>
              <Button
                type="primary"
                size="small"
                onClick={handleSaveAIConfig}
                loading={savingAI}
              >
                {t('settings.save')}
              </Button>
            </Form.Item>
          </Form>
        </Card>
      </Space>

      <Modal open={showLoginModal} title={t('settings.login')} footer={null} onCancel={() => setShowLoginModal(false)}>
        <Form form={loginForm} onFinish={handleLogin} layout="vertical">
          <Form.Item name="username" label={t('settings.username')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="password" label={t('settings.password')} rules={[{ required: true }]}>
            <Input.Password />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} block>{t('settings.login')}</Button>
        </Form>
      </Modal>

      <Modal open={showRegisterModal} title={t('settings.register')} footer={null} onCancel={() => setShowRegisterModal(false)}>
        <Form form={registerForm} onFinish={handleRegister} layout="vertical">
          <Form.Item name="username" label={t('settings.username')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="role" label={t('settings.role')} rules={[{ required: true }]}>
            <Select options={[
              { value: 'viewer', label: 'Viewer' },
              { value: 'engineer', label: 'Engineer' },
              { value: 'reviewer', label: 'Reviewer' },
              { value: 'admin', label: 'Admin' },
            ]} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} block>{t('settings.register')}</Button>
        </Form>
      </Modal>

      {/* Cloud Upload Section */}
      <Card
        size="small"
        title={
          <Space>
            <CloudOutlined />
            {t('cloud.title')}
          </Space>
        }
      >
        <Alert
          type="info"
          showIcon
          message={t('cloud.warn')}
          description={t('cloud.desc')}
          style={{ marginBottom: 12 }}
        />
        <Space direction="vertical" style={{ width: '100%' }} size="small">
          <Select
            placeholder={t('cloud.selectDataset')}
            value={cloudDatasetId || undefined}
            onChange={id => { setCloudDatasetId(id); setCloudPreview(null); loadCloudFields(id) }}
            style={{ width: 300 }}
            loading={cloudLoadingFields}
            options={cloudDatasets.map(d => ({ value: d.dataset_id, label: `${d.file_path} (${d.dataset_id})` }))}
          />

          {cloudDatasetId ? (
            <Table
              size="small"
              rowKey="name"
              loading={cloudLoadingFields}
              dataSource={cloudFields}
              pagination={false}
              scroll={{ x: 520 }}
              columns={[
                { title: t('cloud.field'), dataIndex: 'name', width: 150 },
                { title: t('cloud.dataType'), dataIndex: 'data_type', width: 80 },
                {
                  title: t('cloud.classification'),
                  render: (_, r: DetectedField) => (
                    <Select
                      value={cloudColClass[r.name] ?? 'transmit'}
                      onChange={v => setCloudColClass(prev => ({ ...prev, [r.name]: v }))}
                      options={[
                        { value: 'transmit', label: t('cloud.transmit') },
                        { value: 'mask', label: t('cloud.mask') },
                        { value: 'exclude', label: t('cloud.exclude') },
                      ]}
                      style={{ width: 120 }}
                    />
                  ),
                },
                {
                  title: t('cloud.strategy'),
                  render: (_, r: DetectedField) => {
                    const isMasked = (cloudColClass[r.name] ?? 'transmit') === 'mask'
                    const s = cloudColStrategy[r.name] ?? 'hash'
                    return (
                      <Select
                        value={s}
                        disabled={!isMasked}
                        onChange={v => setCloudColStrategy(prev => ({ ...prev, [r.name]: v }))}
                        options={[
                          { value: 'hash', label: t('cloud.strategyHash') },
                          { value: 'masked', label: t('cloud.strategyMasked') },
                          { value: 'noise', label: t('cloud.strategyNoise') },
                        ]}
                        style={{ width: 140 }}
                      />
                    )
                  },
                },
              ]}
            />
          ) : (
            <Alert type="info" showIcon message={t('cloud.noDataset')} />
          )}

          <Space wrap>
            <Input
              placeholder={t('cloud.purpose')}
              value={cloudPurpose}
              onChange={e => setCloudPurpose(e.target.value)}
              style={{ width: 200 }}
            />
            <Select
              value={cloudProvider}
              onChange={setCloudProvider}
              options={[
                { value: 'ollama', label: 'Ollama (local)' },
                { value: 'openai', label: 'OpenAI' },
                { value: 'azure', label: 'Azure' },
                { value: 'custom', label: 'Custom' },
              ]}
              style={{ width: 140 }}
            />
            <Input
              placeholder={t('cloud.modelVersion')}
              value={cloudModelVersion}
              onChange={e => setCloudModelVersion(e.target.value)}
              style={{ width: 140 }}
            />
            <span style={{ color: '#6b7280', fontSize: 12 }}>{t('cloud.noise')}</span>
            <InputNumber
              value={cloudNoiseStd}
              onChange={v => setCloudNoiseStd(v ?? 0)}
              min={0}
              max={1}
              step={0.1}
              style={{ width: 80 }}
            />
            <Button
              type="primary"
              icon={<CloudOutlined />}
              loading={cloudLoading}
              disabled={!cloudDatasetId}
              onClick={async () => {
                setCloudLoading(true)
                try {
                  const { sensitive, excluded, overrides } = deriveColumns()
                  const result = await previewCloudUpload({
                    dataset_id: cloudDatasetId,
                    sensitive_columns: sensitive,
                    excluded_columns: excluded,
                    strategy_overrides: overrides,
                    noise_std: cloudNoiseStd,
                  })
                  setCloudPreview(result)
                } catch {
                  // engine may not be available in test
                } finally {
                  setCloudLoading(false)
                }
              }}
            >
              {t('cloud.preview')}
            </Button>
            <Button
              danger
              disabled={!cloudPreview}
              onClick={() => setCloudConfirmOpen(true)}
            >
              {t('cloud.confirm')}
            </Button>
          </Space>

          {cloudPreview && (
            <Descriptions size="small" column={2} bordered style={{ marginTop: 8 }}>
              <Descriptions.Item label={t('cloud.rows')}>{cloudPreview.row_count}</Descriptions.Item>
              <Descriptions.Item label={t('cloud.totalCols')}>{cloudPreview.total_columns}</Descriptions.Item>
              <Descriptions.Item label={t('cloud.transmitted')}>
                <Space wrap>
                  {cloudPreview.transmitted_columns.map(c => (
                    <Tag key={c} color="green">{c}</Tag>
                  ))}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label={t('cloud.masked')}>
                <Space wrap>
                  {cloudPreview.masked_columns.map(c => (
                    <Tag key={c} color="orange">{c}</Tag>
                  ))}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label={t('cloud.excluded')} span={2}>
                {cloudPreview.excluded_columns.length > 0
                  ? cloudPreview.excluded_columns.map(c => <Tag key={c} color="default">{c}</Tag>)
                  : t('cloud.none')
                }
              </Descriptions.Item>
              <Descriptions.Item label={t('cloud.hash')} span={2}>
                <Typography.Text type="secondary" style={{ fontSize: 11, fontFamily: 'monospace' }}>
                  {cloudPreview.upload_hash}
                </Typography.Text>
              </Descriptions.Item>
            </Descriptions>
          )}

          {cloudHistory.length > 0 && (
            <Table
              size="small"
              dataSource={cloudHistory}
              rowKey="record_id"
              pagination={{ pageSize: 5 }}
              columns={[
                { title: t('cloud.time'), dataIndex: 'timestamp', width: 160, render: (v: string) => new Date(v).toLocaleString() },
                { title: t('cloud.operator'), dataIndex: 'operator', width: 100 },
                { title: t('cloud.provider'), dataIndex: 'provider', width: 100 },
                { title: t('cloud.rows'), dataIndex: 'row_count', width: 80 },
                { title: t('cloud.purpose'), dataIndex: 'purpose', ellipsis: true },
              ]}
            />
          )}
        </Space>
      </Card>

      {/* Cloud Upload Confirmation Modal */}
      <Modal
        title={t('cloud.confirmTitle')}
        open={cloudConfirmOpen}
        confirmLoading={cloudConfirming}
        onOk={async () => {
          if (!cloudPreview) return
          setCloudConfirming(true)
          try {
            const { sensitive, excluded, overrides } = deriveColumns()
            await confirmCloudUpload({
              dataset_id: cloudDatasetId,
              sensitive_columns: sensitive,
              excluded_columns: excluded,
              strategy_overrides: overrides,
              noise_std: cloudNoiseStd,
              operator: currentUser.username || 'anonymous',
              provider: cloudProvider,
              model_version: cloudModelVersion,
              purpose: cloudPurpose,
            })
            messageApi.success(t('cloud.uploadSuccess'))
            setCloudConfirmOpen(false)
            setCloudPreview(null)
            const records = await listCloudUploadRecords()
            setCloudHistory(records.records)
          } catch {
            messageApi.error(t('cloud.uploadError'))
          } finally {
            setCloudConfirming(false)
          }
        }}
        onCancel={() => setCloudConfirmOpen(false)}
      >
        <Alert
          type="warning"
          showIcon
          message={t('cloud.confirmWarn')}
          description={
            <div>
              <p>{t('cloud.confirmDesc')}</p>
              {cloudPreview && (
                <Space direction="vertical" style={{ width: '100%', marginTop: 8 }}>
                  <div><strong>{t('cloud.transmitted')}:</strong> {cloudPreview.transmitted_columns.join(', ')}</div>
                  <div><strong>{t('cloud.masked')}:</strong> {cloudPreview.masked_columns.join(', ') || t('cloud.none')}</div>
                  <div><strong>{t('cloud.rows')}:</strong> {cloudPreview.row_count}</div>
                  <div><strong>{t('cloud.hash')}:</strong> <span style={{ fontFamily: 'monospace', fontSize: 11 }}>{cloudPreview.upload_hash}</span></div>
                </Space>
              )}
            </div>
          }
        />
      </Modal>
    </>
  )
}
