import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, Table, Form, Input, Select, Button, Space, Alert, Tag, Descriptions, Modal, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { UserOutlined, HistoryOutlined } from '@ant-design/icons'
import { login, logout, registerUser, getCurrentUser, getAuditLog, listUsers } from '../../lib/engine'
import type { UserRole, AuditEntry, UserRecord } from '../../lib/engine'

export default function Settings() {
  const { t } = useTranslation()
  const [messageApi, contextHolder] = message.useMessage()

  const [currentUser, setCurrentUser] = useState<{ username: string | null; role: UserRole | null }>({ username: null, role: null })
  const [users, setUsers] = useState<UserRecord[]>([])
  const [auditLog, setAuditLog] = useState<AuditEntry[]>([])
  const [loading, setLoading] = useState(false)

  const [loginForm] = Form.useForm()
  const [registerForm] = Form.useForm()
  const [showLoginModal, setShowLoginModal] = useState(false)
  const [showRegisterModal, setShowRegisterModal] = useState(false)

  useEffect(() => {
    loadData()
  }, [])

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
