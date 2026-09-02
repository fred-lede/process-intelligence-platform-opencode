import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Layout, Input, Button, Space, Avatar, Typography, Select, Tag } from 'antd'
import { RobotOutlined, SendOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons'
import { aiChat, listAIModels, checkAIHealth, type AIChatMessage } from '../../lib/engine'

const { Sider } = Layout

export default function AssistantPanel() {
  const { t } = useTranslation()
  const [messages, setMessages] = useState<AIChatMessage[]>([
    { role: 'assistant', content: t('assistant.welcome') }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [models, setModels] = useState<string[]>([])
  const [selectedModel, setSelectedModel] = useState<string>('gemma4:e2b-mlx')
  const [health, setHealth] = useState<boolean | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    loadModels()
    checkHealth()
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const loadModels = async () => {
    try {
      const result = await listAIModels()
      if (result.success && result.models) {
        setModels(result.models)
        if (result.models.length > 0) {
          setSelectedModel(result.models[0])
        }
      }
    } catch { /* ignore */ }
  }

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

    try {
      const result = await aiChat([...messages, userMessage], selectedModel)
      if (result.success && result.response) {
        setMessages(prev => [...prev, { role: 'assistant', content: result.response! }])
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${result.error ?? 'Unknown error'}` }])
      }
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Failed to connect to AI assistant.' }])
    } finally {
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
        <Select
          size="small"
          style={{ width: '100%', marginTop: 8 }}
          value={selectedModel}
          onChange={setSelectedModel}
          options={models.map(m => ({ value: m, label: m }))}
          placeholder="Select model..."
        />
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
