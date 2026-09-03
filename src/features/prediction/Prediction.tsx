import { useEffect, useRef, useState, useCallback } from 'react'
import type { CSSProperties, PointerEvent as ReactPointerEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, Select, Space, Button, Alert, Typography, Tag, InputNumber, Statistic, Modal, Input, message, Row, Col } from 'antd'
import { PlusOutlined, MinusOutlined, SaveOutlined, HistoryOutlined } from '@ant-design/icons'
import { useDataPipelineStore } from '../../stores/dataPipelineStore'
import { predictOutput, getModelInfo, listModels, saveScenario, listScenarios, type ModelInfo, type PredictionScenario } from '../../lib/engine'

function DraggableSlider({ min, max, value, onChange, style }: {
  min: number
  max: number
  value: number
  onChange: (v: number) => void
  style?: CSSProperties
}) {
  const trackRef = useRef<HTMLDivElement>(null)

  const updateFrom = useCallback((clientX: number) => {
    const el = trackRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    if (!(rect.width > 0)) return
    let ratio = (clientX - rect.left) / rect.width
    ratio = Math.min(1, Math.max(0, ratio))
    const raw = min + ratio * (max - min)
    const clamped = Math.min(max, Math.max(min, raw))
    onChange(Number(clamped.toFixed(4)))
  }, [min, max, onChange])

  const handlePointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.currentTarget.setPointerCapture(e.pointerId)
    updateFrom(e.clientX)
  }

  const handlePointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.buttons === 0 && e.pressure === 0) return
    updateFrom(e.clientX)
  }

  const pct = max === min ? 0 : Math.min(100, Math.max(0, ((value - min) / (max - min)) * 100))

  return (
    <div
      ref={trackRef}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerCancel={() => {}}
      onPointerUp={() => {}}
      style={{
        position: 'relative',
        height: 24,
        touchAction: 'none',
        cursor: 'pointer',
        userSelect: 'none',
        ...style,
      }}
    >
      <div style={{ position: 'absolute', top: '50%', left: 0, right: 0, height: 10, transform: 'translateY(-50%)', borderRadius: 5, overflow: 'hidden', background: '#e5e9f0' }}>
        <div style={{ position: 'absolute', top: 0, left: 0, bottom: 0, width: `${pct}%`, background: '#2563eb' }} />
      </div>
      <div
        style={{
          position: 'absolute',
          top: '50%',
          left: `${pct}%`,
          transform: 'translate(-50%, -50%)',
          width: 18,
          height: 18,
          borderRadius: '50%',
          background: '#2563eb',
          border: '2px solid #fff',
          boxShadow: '0 1px 3px rgba(0,0,0,0.25)',
        }}
      >
        <span style={{ position: 'absolute', left: '50%', top: 22, transform: 'translateX(-50%)', fontSize: 10, color: '#fff', background: 'rgba(0,0,0,0.6)', borderRadius: 3, padding: '0 4px', whiteSpace: 'nowrap' }}>
          {value.toFixed(2)}
        </span>
      </div>
    </div>
  )
}

export default function Prediction() {
  const { t } = useTranslation()
  const { importResult, spec } = useDataPipelineStore()

  const [models, setModels] = useState<Array<{ model_id: string; model_type: string; equation: string }>>([])
  const [selectedModel, setSelectedModel] = useState<string | undefined>()
  const [modelInfo, setModelInfo] = useState<ModelInfo | null>(null)
  const [inputValues, setInputValues] = useState<Record<string, number>>({})
  const [predicted, setPredicted] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [scenarios, setScenarios] = useState<PredictionScenario[]>([])
  const [saveModalOpen, setSaveModalOpen] = useState(false)
  const [scenarioName, setScenarioName] = useState('')
  const [scenarioNotes, setScenarioNotes] = useState('')
  const [messageApi, contextHolder] = message.useMessage()

  useEffect(() => {
    listModels().then(r => {
      if (r.models) {
        setModels(r.models.map(m => ({ model_id: m.model_id, model_type: m.model_type, equation: m.equation })))
      }
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (selectedModel) loadScenarios(selectedModel)
  }, [selectedModel])

  useEffect(() => {
    if (!selectedModel) {
      setModelInfo(null)
      setInputValues({})
      setPredicted(null)
      return
    }
    getModelInfo({ model_id: selectedModel }).then(r => {
      setModelInfo(r)
      const defaults: Record<string, number> = {}
      if (importResult) {
        const stats = importResult.stats.column_stats
        for (const inp of r.inputs) {
          const s = stats[inp]
          defaults[inp] = s ? (s.mean ?? 0) : 0
        }
      }
      setInputValues(defaults)
    }).catch(() => {})
  }, [selectedModel, importResult])

  useEffect(() => {
    if (!modelInfo || Object.keys(inputValues).length === 0) return
    setLoading(true)
    predictOutput({ model_id: selectedModel!, input_values: inputValues })
      .then(r => setPredicted(r.predicted))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [inputValues, modelInfo, selectedModel])

  const handleInputChange = (key: string, value: number | null) => {
    if (value === null) return
    setInputValues(prev => ({ ...prev, [key]: value }))
  }

  const handleRestore = () => {
    if (!modelInfo || !importResult) return
    const defaults: Record<string, number> = {}
    for (const inp of modelInfo.inputs) {
      const stats = importResult.stats.column_stats[inp]
      defaults[inp] = stats?.mean ?? 0
    }
    setInputValues(defaults)
  }

  const loadScenarios = async (modelId: string) => {
    try {
      const r = await listScenarios({ model_id: modelId })
      setScenarios(r.scenarios)
    } catch {
      // ignore
    }
  }

  const handleSaveScenario = async () => {
    if (!selectedModel || predicted === null) return
    try {
      await saveScenario({
        name: scenarioName || `Scenario ${scenarios.length + 1}`,
        model_id: selectedModel,
        input_values: inputValues,
        predicted_output: predicted,
        operator: 'current_user',
        notes: scenarioNotes,
      })
      messageApi.success(t('prediction.saveSuccess'))
      setSaveModalOpen(false)
      setScenarioName('')
      setScenarioNotes('')
      if (selectedModel) loadScenarios(selectedModel)
    } catch {
      messageApi.error(t('prediction.saveError'))
    }
  }

  const getNgStatus = () => {
    if (predicted === null) return null
    const { lsl, usl } = spec ?? {}
    if (lsl !== null && lsl !== undefined && predicted < lsl) return { text: t('prediction.belowLSL'), color: 'error' as const }
    if (usl !== null && usl !== undefined && predicted > usl) return { text: t('prediction.aboveUSL'), color: 'error' as const }
    return { text: t('prediction.inSpec'), color: 'success' as const }
  }

  const getDistanceToLimit = () => {
    if (predicted === null) return null
    const { lsl, usl } = spec ?? {}
    const dists: string[] = []
    if (lsl !== null && lsl !== undefined) dists.push(`LSL: ${(predicted - lsl).toFixed(2)}`)
    if (usl !== null && usl !== undefined) dists.push(`USL: ${(usl - predicted).toFixed(2)}`)
    return dists.join(' / ')
  }

  const ngStatus = getNgStatus()
  const hasData = !!importResult

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {contextHolder}
      <Card title={t('prediction.title')}>
        <Space wrap style={{ marginBottom: 12 }}>
          <Select
            value={selectedModel}
            onChange={setSelectedModel}
            options={models.map(m => ({
              value: m.model_id,
              label: `${m.model_type} — ${m.equation.slice(0, 40)}...`,
            }))}
            disabled={models.length === 0}
            style={{ width: 400 }}
            placeholder={t('prediction.noModels')}
          />
          <Button onClick={handleRestore} disabled={!hasData || !modelInfo}>
            {t('prediction.restoreDefaults')}
          </Button>
        </Space>
      </Card>

      {modelInfo && (
        <Row gutter={[16, 16]} style={{ width: '100%' }}>
          <Col flex="1 1 auto" style={{ minWidth: 0 }}>
            <Card title={t('prediction.equation')} size="small">
              <pre style={{ fontSize: 13, marginBottom: 12, padding: '4px 8px', background: '#f5f5f5', borderRadius: 4, margin: '0 0 12px 0', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{modelInfo.equation}</pre>
              {modelInfo.inputs.map(inp => {
                const s = importResult?.stats.column_stats[inp]
                const val = inputValues[inp] ?? 0
                const num = (x: unknown) => (typeof x === 'number' && isFinite(x) ? x : undefined)
                const statMean = num(s?.mean)
                const statStd = num(s?.std)
                const statMin = num(s?.min)
                const statMax = num(s?.max)
                const mean = statMean ?? val
                let spread: number
                if (statStd !== undefined && statStd > 0) {
                  spread = statStd
                } else if (statMin !== undefined && statMax !== undefined && statMax > statMin) {
                  spread = Math.max((statMax - statMin) / 6, Math.abs(mean) || 1)
                } else {
                  spread = Math.abs(mean) || 1
                }
                const cap = Math.max(Math.abs(mean), 1) * 100
                if (spread > cap) spread = cap
                if (!isFinite(spread) || spread <= 0) spread = 1
                let min = mean - 3 * spread
                let max = mean + 3 * spread
                if (min >= max || !isFinite(min) || !isFinite(max)) {
                  min = mean - 1
                  max = mean + 1
                }
                if (max - min < 1) {
                  min = mean - 0.5
                  max = mean + 0.5
                }
                const step = (max - min) / 100
                return (
                    <div key={inp} style={{ marginBottom: 16 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                        <span style={{ fontWeight: 600, fontSize: 13 }}>{inp}
                          <span style={{ fontWeight: 400, fontSize: 11, color: '#999', marginLeft: 8 }}>
                            {Number(min).toFixed(2)} — {Number(max).toFixed(2)}
                          </span>
                        </span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <Button size="small" icon={<MinusOutlined />} onClick={() => handleInputChange(inp, Number(val) - Number(step))} style={{ width: 28, padding: 0, flexShrink: 0 }} />
                        <DraggableSlider
                          min={min}
                          max={max}
                          value={val}
                          onChange={v => handleInputChange(inp, v)}
                          style={{ flex: 1, minWidth: 0 }}
                        />
                        <Button size="small" icon={<PlusOutlined />} onClick={() => handleInputChange(inp, Number(val) + Number(step))} style={{ width: 28, padding: 0, flexShrink: 0 }} />
                        <InputNumber
                          value={val}
                          onChange={v => handleInputChange(inp, v)}
                          precision={2}
                          style={{ width: 90, flexShrink: 0 }}
                          min={min}
                          max={max}
                        />
                      </div>
                    </div>
                )
              })}
            </Card>
          </Col>
          <Col flex="0 0 260px">
            <Card title={t('prediction.predictedOutput')} size="small" style={{ height: '100%' }}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Statistic
                  title="Predicted Value"
                  value={predicted ?? 0}
                  precision={2}
                  loading={loading}
                />
                {ngStatus && (
                  <Tag color={ngStatus.color} style={{ fontSize: 14, padding: '4px 12px' }}>
                    {ngStatus.text}
                  </Tag>
                )}
                <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
                  <Button
                    size="small"
                    icon={<HistoryOutlined />}
                    onClick={() => loadScenarios(selectedModel!)}
                    disabled={!selectedModel}
                  >
                    {t('prediction.viewScenarios')}
                  </Button>
                  <Button
                    type="primary"
                    size="small"
                    icon={<SaveOutlined />}
                    onClick={() => setSaveModalOpen(true)}
                    disabled={predicted === null}
                  >
                    {t('prediction.saveScenario')}
                  </Button>
                </Space>
                {spec?.lsl !== null && spec?.lsl !== undefined && (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    LSL: {spec.lsl.toFixed(2)}
                  </Typography.Text>
                )}
                {spec?.usl !== null && spec?.usl !== undefined && (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    USL: {spec.usl.toFixed(2)}
                  </Typography.Text>
                )}
                {getDistanceToLimit() && (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {t('prediction.distanceToLimit')}: {getDistanceToLimit()}
                  </Typography.Text>
                )}
              </Space>
            </Card>
          </Col>
        </Row>
      )}

      {!modelInfo && importResult && (
        <Alert type="info" message={t('prediction.selectModelFirst')} showIcon />
      )}
      {!importResult && (
        <Alert type="warning" message={t('prediction.noData')} showIcon />
      )}

      <Modal
        title={t('prediction.saveScenario')}
        open={saveModalOpen}
        onCancel={() => setSaveModalOpen(false)}
        onOk={handleSaveScenario}
        okText={t('prediction.saveScenario')}
        cancelText={t('common.cancel')}
      >
        <Space direction="vertical" style={{ width: '100%' }} size={8}>
          <Input
            placeholder={t('prediction.scenarioNamePlaceholder')}
            value={scenarioName}
            onChange={e => setScenarioName(e.target.value)}
          />
          <Input.TextArea
            rows={3}
            placeholder={t('prediction.scenarioNotesPlaceholder')}
            value={scenarioNotes}
            onChange={e => setScenarioNotes(e.target.value)}
          />
          {predicted !== null && (
            <Typography.Text>
              {t('prediction.predictedValue')}: <strong>{predicted.toFixed(4)}</strong>
            </Typography.Text>
          )}
        </Space>
      </Modal>
    </div>
  )
}
