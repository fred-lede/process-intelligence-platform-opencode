import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Layout, Input, Button, Space, Avatar, Typography, Tag, Spin, Popconfirm } from 'antd'
import { RobotOutlined, SendOutlined, CheckCircleOutlined, CloseCircleOutlined, ClearOutlined } from '@ant-design/icons'
import { aiChat, checkAIHealth, type AIChatMessage } from '../../lib/engine'
import { useAIStore } from '../../stores/aiStore'
import { useAssistantContextStore } from '../../stores/assistantContextStore'
import { buildAssistantSystemPrompt } from '../../lib/assistantGuide'
import type { AppTab } from '../../types'

const { Sider } = Layout

interface AssistantPanelProps {
  activeTab: AppTab
}

export default function AssistantPanel({ activeTab }: AssistantPanelProps) {
  const { t, i18n } = useTranslation()
  const { context } = useAssistantContextStore()
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
    // Let React flush the loading state and the browser paint before awaiting.
    await new Promise(r => setTimeout(r, 0))

    // Keep the "thinking" banner visible for a guaranteed minimum time so the
    // green bar is clearly seen BEFORE the reply reveals itself (a perceptible
    // think -> answer sequence even though the local AI answers instantly).
    const MIN_THINK_MS = 800
    const started = Date.now()

    let reply: string
    try {
      const payload: AIChatMessage[] = [
        { role: 'system', content: buildAssistantSystemPrompt(activeTab, i18n.language, context[activeTab]) },
        ...messages,
        userMessage,
      ]
      const result = await aiChat(payload)
      reply = result.response ?? `Error: ${result.error ?? 'Unknown error'}`
    } catch {
      reply = 'Failed to connect to AI assistant.'
    } finally {
      const remaining = Math.max(0, MIN_THINK_MS - (Date.now() - started))
      await new Promise(r => setTimeout(r, remaining))
    }

    setMessages(prev => [...prev, { role: 'assistant', content: reply }])
    setLoading(false)
  }

  const handleClear = () => {
    setInput('')
    setMessages([{ role: 'assistant', content: t('assistant.welcome') }])
  }

  return (
    <Sider
      width={320}
      theme="light"
      style={{ borderLeft: '1px solid #e5e7eb', display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}
    >
      <div style={{ padding: '12px 16px', borderBottom: '1px solid #e5e7eb' }}>
        <div style={{ display: 'flex', width: '100%', justifyContent: 'space-between', alignItems: 'center' }}>
          <Typography.Title level={5} style={{ margin: 0 }}>{t('assistant.title')}</Typography.Title>
          <Space size={8}>
            {health === true ? (
              <Tag color="success" icon={<CheckCircleOutlined />} style={{ fontSize: 12, margin: 0 }}>Online</Tag>
            ) : health === false ? (
              <Tag color="error" icon={<CloseCircleOutlined />} style={{ fontSize: 12, margin: 0 }}>Offline</Tag>
            ) : null}
            <Popconfirm
              title={t('assistant.clearConfirm')}
              onConfirm={handleClear}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
            >
              <Button size="small" type="text" icon={<ClearOutlined />} disabled={loading}>
                {t('assistant.clear')}
              </Button>
            </Popconfirm>
          </Space>
        </div>

      </div>

      {loading && (
        <div style={{ padding: '10px 16px', borderBottom: '1px solid #d1fae5', background: '#ecfdf5', display: 'flex', alignItems: 'center', gap: 8 }}>
          <Spin size="small" />
          <Typography.Text style={{ fontSize: 13, color: '#10b981', fontWeight: 600 }}>{t('assistant.thinking')}</Typography.Text>
        </div>
      )}
      <div
        className="assistant-messages"
        style={{ flex: '1 1 0', minHeight: 0, maxHeight: 'calc(100vh - 118px)', overflowY: 'auto', overflowX: 'hidden', padding: 16 }}
      >
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
        <div ref={messagesEndRef} />
      </div>

      <div style={{ padding: 12, borderTop: '1px solid #e5e7eb' }}>
        <Space.Compact style={{ width: '100%' }}>
          <Input
            placeholder={t('assistant.placeholder')}
            value={input}
            onChange={(e) => setInput(e.target.value)}
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
