import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Layout, Input, Button, Space, Avatar, Typography, Tag, Spin } from 'antd'
import { RobotOutlined, SendOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons'
import { aiChat, checkAIHealth, type AIChatMessage } from '../../lib/engine'
import { useAIStore } from '../../stores/aiStore'

const { Sider } = Layout

export default function AssistantPanel() {
  const { t } = useTranslation()
  const [messages, setMessages] = useState<AIChatMessage[]>([
    { role: 'assistant', content: t('assistant.welcome') }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [health, setHealth] = useState<boolean | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const refreshKey = useAIStore((s) => s.refreshKey)

  useEffect(() => {
    checkHealth()
  }, [])

  useEffect(() => {
    if (refreshKey > 0) checkHealth()
  }, [refreshKey])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const checkHealth = async () => {
    try {
      const result = await checkAIHealth()
      setHealth(result.healthy)
    } catch {
      setHealth(false)
    }
  }

  const handleSend = async () => {
    if (!input.trim() || loading) return

    const userMessage: AIChatMessage = { role: 'user', content: input }
    setMessages(prev => [...prev, userMessage])
    setInput('')
    setLoading(true)
    // Let React flush the loading state and the browser paint before awaiting
    // (otherwise React 18 auto-batching can skip the loading frame on fast calls).
    await new Promise(r => setTimeout(r, 0))

    const started = Date.now()
    try {
      const result = await aiChat([...messages, userMessage])
      setMessages(prev => [...prev, { role: 'assistant', content: result.response ?? `Error: ${result.error ?? 'Unknown error'}` }])
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Failed to connect to AI assistant.' }])
    } finally {
      // Keep the spinner visible for a minimum time so fast replies don't hide it instantly.
      const remaining = Math.max(0, 400 - (Date.now() - started))
      await new Promise(r => setTimeout(r, remaining))
      setLoading(false)
    }
  }

  return (
    <Sider
      width={320}
      theme="light"
      style={{ borderLeft: '1px solid #e5e7eb', display: 'flex', flexDirection: 'column' }}
    >
      <div style={{ padding: 16, borderBottom: '1px solid #e5e7eb' }}>
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Typography.Title level={5} style={{ margin: 0 }}>{t('assistant.title')}</Typography.Title>
          {health === true ? (
            <Tag color="success" icon={<CheckCircleOutlined />} style={{ fontSize: 12 }}>Online</Tag>
          ) : health === false ? (
            <Tag color="error" icon={<CloseCircleOutlined />} style={{ fontSize: 12 }}>Offline</Tag>
          ) : null}
        </Space>

      </div>

      <div style={{ flex: 1, padding: 16, overflow: 'auto' }}>
        {messages.map((msg, idx) => (
          <div key={idx} style={{ marginBottom: 12, display: 'flex', gap: 8 }}>
            <Avatar
              size="small"
              icon={<RobotOutlined />}
              style={{ backgroundColor: msg.role === 'user' ? '#2563EB' : '#10b981', marginTop: 4 }}
            />
            <div style={{ flex: 1, background: '#f5f5f5', padding: '8px 12px', borderRadius: 8 }}>
              <Typography.Text style={{ fontSize: 13 }}>{msg.content}</Typography.Text>
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ marginBottom: 12, display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <Avatar size="small" icon={<RobotOutlined />} style={{ backgroundColor: '#10b981', marginTop: 4 }} />
            <div style={{ flex: 1, background: '#f0f9ff', padding: '10px 14px', borderRadius: 8, minWidth: 120 }}>
              <Space direction="horizontal" size={8}>
                <Spin size="small" />
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>{t('assistant.thinking')}</Typography.Text>
              </Space>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div style={{ padding: 12, borderTop: '1px solid #e5e7eb' }}>
        <Space.Compact style={{ width: '100%' }}>
          <Input
            placeholder={t('assistant.placeholder')}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onPressEnter={handleSend}
            disabled={loading || health === false}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            loading={loading}
            disabled={!input.trim() || health === false}
          />
        </Space.Compact>
      </div>
    </Sider>
  )
}
