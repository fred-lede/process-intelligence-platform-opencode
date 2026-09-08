import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Layout, Input, Button, Space, Avatar, Typography, Tag, Spin, Popconfirm, Alert } from 'antd'
import { RobotOutlined, SendOutlined, ClearOutlined } from '@ant-design/icons'
import {
  assistantRespond, previewAssistantCloudTransfer, grantAssistantCloudConsent, executeAssistantDraft, getSettings,
  type AIChatMessage, type AIProviderType, type AssistantRequest, type AssistantResponse, type AssistantCloudTransferPreview,
} from '../../lib/engine'
import { useAIStore } from '../../stores/aiStore'
import { useAssistantContextStore } from '../../stores/assistantContextStore'
import { useEngineActivityStore } from '../../stores/engineStatusStore'
import EvidenceCard from '../assistant/EvidenceCard'
import TransferPreviewCard from '../assistant/TransferPreviewCard'
import ActionDraftCard from '../assistant/ActionDraftCard'
import type { AppTab } from '../../types'

const { Sider } = Layout

interface AssistantPanelProps {
  activeTab: AppTab
  activeProject: { id: string; name: string; root: string } | null
}

interface TranscriptMessage extends AIChatMessage {
  result?: AssistantResponse
  draftDismissed?: boolean
  draftExecuted?: boolean
  actionError?: string
}

export default function AssistantPanel({ activeTab, activeProject }: AssistantPanelProps) {
  const { t } = useTranslation()
  const projectId = useAssistantContextStore((s) => s.activeProjectId)
  const [messages, setMessages] = useState<TranscriptMessage[]>([{ role: 'assistant', content: t('assistant.welcome') }])
  const [input, setInput] = useState('')
  const [enterArmed, setEnterArmed] = useState(false)
  const [loading, setLoading] = useState(false)
  const [executingDraft, setExecutingDraft] = useState<string | null>(null)
  const [provider, setProvider] = useState<AIProviderType>('ollama')
  const [configuredModel, setConfiguredModel] = useState('')
  const [pendingTransfer, setPendingTransfer] = useState<{ request: AssistantRequest; preview: AssistantCloudTransferPreview; error?: string } | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const mounted = useRef(true)
  const refreshKey = useAIStore((s) => s.refreshKey)
  const projectReady = !!activeProject && projectId === activeProject.id
  const busy = loading || executingDraft !== null
  const setAssistantBusy = useEngineActivityStore((s) => s.setAssistantBusy)

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  useEffect(() => {
    let cancelled = false
    getSettings().then(({ config }) => {
      if (!cancelled) {
        const configuredProvider = config.enabled ? config.provider : 'ollama'
        setProvider(configuredProvider)
        setConfiguredModel(config.model || '')
        setPendingTransfer(null)
      }
    }).catch(() => {})
    return () => { cancelled = true }
  }, [refreshKey])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, pendingTransfer])

  const stillCurrent = (id: string | null) => mounted.current && id !== null && useAssistantContextStore.getState().activeProjectId === id

  const appendResponse = async (request: AssistantRequest) => {
    const result = await assistantRespond(request)
    if (stillCurrent(request.context.project_id)) {
      setMessages(prev => [...prev, { role: 'assistant', content: result.explanation, result }])
    }
  }

  const handleSend = async () => {
    if (!input.trim() || busy || pendingTransfer || !projectReady) return
    const context = useAssistantContextStore.getState().getCurrentContext(activeTab)
    if (context.project_id !== activeProject?.id) return
    const request: AssistantRequest = { message: input.trim(), tab: activeTab, context, provider }
    setMessages(prev => [...prev, { role: 'user', content: request.message }])
    setInput('')
    setEnterArmed(false)
    setLoading(true)
    setAssistantBusy(true)
    try {
      if (provider === 'ollama') {
        await appendResponse(request)
      } else {
        const preview = await previewAssistantCloudTransfer(request)
        if (stillCurrent(context.project_id)) setPendingTransfer({ request, preview })
      }
    } catch (error) {
      const raw = String(error)
      const message = raw.includes('TimeoutError')
        ? '雲端模型回覆逾時，模型可能仍在推理中，請稍後重試。'
        : raw
      if (stillCurrent(context.project_id)) setMessages(prev => [...prev, { role: 'assistant', content: message }])
    } finally {
      setLoading(false)
      setAssistantBusy(false)
    }
  }

  const handleTransferConfirm = async () => {
    if (!pendingTransfer || busy || !projectReady || !stillCurrent(pendingTransfer.request.context.project_id)) return
    const { request, preview } = pendingTransfer
    setLoading(true)
    setAssistantBusy(true)
    try {
      const consent = await grantAssistantCloudConsent(preview.payload_hash)
      if (!consent.cloud_consent) throw new Error(consent.error_code ?? 'Cloud consent failed.')
      if (!stillCurrent(request.context.project_id)) return
      await appendResponse({ ...request, preview_hash: preview.payload_hash })
      setPendingTransfer(null)
    } catch (error) {
      if (stillCurrent(request.context.project_id)) setPendingTransfer({ request, preview, error: String(error) })
    } finally {
      setLoading(false)
      setAssistantBusy(false)
    }
  }

  const handleDraftConfirm = async (index: number, draftId: string) => {
    if (busy || pendingTransfer || !projectReady || !stillCurrent(projectId)) return
    setExecutingDraft(draftId)
    try {
      const result = await executeAssistantDraft(draftId, true)
      if (result.success === false || result.error_code || result.error) throw new Error(result.error_code ?? result.error ?? 'Action failed.')
      if (stillCurrent(projectId)) setMessages(prev => prev.map((msg, i) => i === index ? { ...msg, draftExecuted: true, actionError: undefined } : msg))
    } catch (error) {
      const raw = String(error)
      const actionError = raw.includes('Unknown dataset_id')
        ? '此操作引用的資料集尚未載入目前工作階段。請先回到資料匯入或 SPC 頁面重新載入資料，再重試。'
        : raw
      if (stillCurrent(projectId)) setMessages(prev => prev.map((msg, i) => i === index ? { ...msg, actionError } : msg))
    } finally {
      setExecutingDraft(null)
    }
  }

  const handleClear = () => {
    setInput('')
    setPendingTransfer(null)
    setMessages([{ role: 'assistant', content: t('assistant.welcome') }])
  }

  return (
    <Sider width={320} theme="light" style={{ borderLeft: '1px solid #e5e7eb', height: '100vh', overflow: 'hidden' }}>
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid #e5e7eb' }}>
          <Space style={{ width: '100%', justifyContent: 'space-between' }}>
            <Typography.Title level={5} style={{ margin: 0 }}>{t('assistant.title')}</Typography.Title>
            <Popconfirm title={t('assistant.clearConfirm')} onConfirm={handleClear} okText={t('common.confirm')} cancelText={t('common.cancel')}>
              <Button size="small" type="text" icon={<ClearOutlined />} disabled={busy}>{t('assistant.clear')}</Button>
            </Popconfirm>
          </Space>
          <Typography.Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
            {provider === 'ollama' ? t('assistant.localProvider', { defaultValue: 'Local · Ollama' }) : provider} · {configuredModel || '—'}
          </Typography.Text>
        </div>
        {loading && <div style={{ padding: '10px 16px', background: '#ecfdf5' }}><Space><Spin size="small" /><Typography.Text>{t('assistant.thinking')}</Typography.Text></Space></div>}
        <div className="assistant-messages" style={{ flex: '1 1 0', minHeight: 0, overflowY: 'auto', overflowX: 'hidden', padding: 16 }}>
          {messages.map((msg, idx) => (
            <div key={idx} style={{ marginBottom: 12, display: 'flex', gap: 8 }}>
              <Avatar size="small" icon={<RobotOutlined />} style={{ flexShrink: 0, backgroundColor: msg.role === 'user' ? '#2563EB' : '#10b981', marginTop: 4 }} />
              <div style={{ flex: 1, minWidth: 0, background: '#f5f5f5', padding: '8px 12px', borderRadius: 8, overflowWrap: 'anywhere' }}>
                <Space direction="vertical" style={{ width: '100%' }}>
                  {msg.result?.error_code === 'local_model_unavailable' ? (
                    <Alert type="warning" showIcon message={t('assistant.localUnavailable', { defaultValue: 'Local model is not ready' })} description={t('assistant.localSetup', { defaultValue: 'Start Ollama, install a local model, then choose and test it in Settings → AI Provider. Retry here when ready.' })} />
                  ) : <Typography.Text style={{ fontSize: 13, whiteSpace: 'pre-wrap' }}>{msg.content}</Typography.Text>}
                  {msg.result && <>
                    <EvidenceCard evidence={msg.result.evidence} status={msg.result.evidence_status} />
                    {msg.result.recommendations.length > 0 && <div><Typography.Text strong>{t('assistant.recommendations', { defaultValue: 'Recommendations' })}</Typography.Text><ul style={{ paddingLeft: 18, marginBottom: 0 }}>{msg.result.recommendations.map((value, i) => <li key={i}>{value}</li>)}</ul></div>}
                    {msg.result.limitations.length > 0 && <Alert type="warning" message={t('assistant.limitations', { defaultValue: 'Limitations' })} description={msg.result.limitations.join('\n')} />}
                    {msg.draftExecuted && <Tag color="success">{t('assistant.draftExecuted', { defaultValue: 'Action completed' })}</Tag>}
                    {msg.result.success && msg.result.action_draft && !msg.draftDismissed && !msg.draftExecuted && <ActionDraftCard
                      draft={msg.result.action_draft}
                      busy={executingDraft === msg.result.action_draft.draft_id}
                      disabled={busy || !!pendingTransfer || !projectReady}
                      error={msg.actionError}
                      onConfirm={() => void handleDraftConfirm(idx, msg.result!.action_draft!.draft_id)}
                      onCancel={() => setMessages(prev => prev.map((item, i) => i === idx ? { ...item, draftDismissed: true } : item))}
                    />}
                  </>}
                </Space>
              </div>
            </div>
          ))}
          {pendingTransfer && <TransferPreviewCard preview={pendingTransfer.preview} busy={busy || !projectReady} error={pendingTransfer.error} onConfirm={() => void handleTransferConfirm()} onCancel={() => setPendingTransfer(null)} />}
          <div ref={messagesEndRef} />
        </div>
        <div style={{ padding: 12, borderTop: '1px solid #e5e7eb' }}>
          <Space.Compact style={{ width: '100%' }}>
            <Input.TextArea
              placeholder={t('assistant.placeholder')}
              value={input}
              autoSize={{ minRows: 1, maxRows: 5 }}
              style={enterArmed ? { borderBottom: '2px solid #2563eb' } : undefined}
              onChange={(e) => { setInput(e.target.value); setEnterArmed(false) }}
              onPressEnter={(event) => {
                event.preventDefault()
                if (enterArmed) void handleSend()
                else setEnterArmed(true)
              }}
              onBlur={() => setEnterArmed(false)}
              disabled={busy || !!pendingTransfer || !projectReady}
            />
            <Button aria-label={t('assistant.send', { defaultValue: 'Send' })} type="primary" icon={<SendOutlined />} onClick={() => void handleSend()} loading={loading} disabled={!input.trim() || busy || !!pendingTransfer || !projectReady} />
          </Space.Compact>
        </div>
      </div>
    </Sider>
  )
}
