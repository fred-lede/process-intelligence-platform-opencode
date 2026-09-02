import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, Table, Form, Input, Select, Button, Space, Alert, Tag, Descriptions, Modal, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { UserOutlined, HistoryOutlined, CloudOutlined, CheckCircleOutlined, ReloadOutlined } from '@ant-design/icons'
import { login, logout, registerUser, getCurrentUser, getAuditLog, listUsers, getSettings, updateSettings, testConnection, listAIModels, enginePing } from '../../lib/engine'
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
  })
  const [savingAI, setSavingAI] = useState(false)
  const [availableModels, setAvailableModels] = useState<string[]>([])
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ success: boolean; error?: string } | null>(null)

  const [aiForm] = Form.useForm()
  const [loginForm] = Form.useForm()
  const [registerForm] = Form.useForm()
  const [showLoginModal, setShowLoginModal] = useState(false)
  const [showRegisterModal, setShowRegisterModal] = useState(false)

  useEffect(() => {
    loadData()
    loadSettings()
  }, [])

  const loadSettings = async (retryCount = 0) => {
    try {
      await enginePing()
      const result = await getSettings()
      if (result.config) {
        setAiConfig(result.config)
        aiForm.setFieldsValue(result.config)
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
      setAiConfig(prev => ({ ...prev, provider: 'ollama', base_url: 'http://localhost:11434', model: 'gemma4:e2b-mlx', api_key: '' }))
    } else if (aiConfig.provider === 'openai') {
      aiForm.setFieldValue('model', 'gpt-4o')
      setAiConfig(prev => ({ ...prev, provider: 'openai', base_url: 'https://api.openai.com', model: 'gpt-4o', api_key: prev.api_key }))
    }
  }, [aiConfig.provider])

  const loadData = async () => {
    try {
      const [user, usersList, log] = await Promise.all([
        getCurrentUser(),
        listUsers(),
        getAuditLog(50),
      ])
      setCurrentUser(user)
      setUsers(usersList.users)
      setAuditLog(log.log)
    } catch {
      messageApi.error('Failed to load data')
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
      const result = await updateSettings(aiConfig)
      if (result.success) {
        setAiConfig(result.config)
        messageApi.success(t('settings.aiConfigSaved'))
      }
    } catch (e) {
      messageApi.error(t('settings.aiConfigSaveFailed'))
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
    const colors: Record<UserRole, string> = { admin: 'red', engineer: 'blue', viewer: 'gray' }
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
            onValuesChange={(_, all) => setAiConfig(all as AIProviderConfig)}
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
              { value: 'admin', label: 'Admin' },
            ]} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} block>{t('settings.register')}</Button>
        </Form>
      </Modal>
    </>
  )
}
