import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, Select, Space, Button, Alert, Typography, Tag, Slider, InputNumber, Row, Col, Statistic } from 'antd'
import { useDataPipelineStore } from '../../stores/dataPipelineStore'
import { predictOutput, getModelInfo, listModels, type ModelInfo } from '../../lib/engine'

export default function Prediction() {
  const { t } = useTranslation()
  const { importResult, spec } = useDataPipelineStore()

  const [models, setModels] = useState<Array<{ model_id: string; model_type: string; equation: string }>>([])
  const [selectedModel, setSelectedModel] = useState<string | undefined>()
  const [modelInfo, setModelInfo] = useState<ModelInfo | null>(null)
  const [inputValues, setInputValues] = useState<Record<string, number>>({})
  const [predicted, setPredicted] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    listModels().then(r => {
      if (r.models) {
        setModels(r.models.map(m => ({ model_id: m.model_id, model_type: m.model_type, equation: m.equation })))
      }
    }).catch(() => {})
  }, [])

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
        <Row gutter={16}>
          <Col span={16}>
            <Card title={t('prediction.equation')} size="small">
              <Typography.Text code style={{ fontSize: 14 }}>{modelInfo.equation}</Typography.Text>
              <div style={{ marginTop: 12 }}>
                {modelInfo.inputs.map(inp => {
                  const stats = importResult?.stats.column_stats[inp]
                  const min = stats?.min ?? (inputValues[inp] ?? 0) - 3 * (stats?.std ?? 5)
                  const max = stats?.max ?? (inputValues[inp] ?? 0) + 3 * (stats?.std ?? 5)
                  const val = inputValues[inp] ?? 0
                  return (
                    <div key={inp} style={{ marginBottom: 12 }}>
                      <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                        <Typography.Text strong>{inp}</Typography.Text>
                        <InputNumber
                          value={val}
                          onChange={v => handleInputChange(inp, v)}
                          precision={2}
                          style={{ width: 100 }}
                          min={min}
                          max={max}
                        />
                      </Space>
                      <Slider
                        min={min}
                        max={max}
                        value={val}
                        onChange={v => handleInputChange(inp, v)}
                        step={(max - min) / 100}
                      />
                      <Space>
                        <Typography.Text type="secondary" style={{ fontSize: 11 }}>Min: {min.toFixed(2)}</Typography.Text>
                        <Typography.Text type="secondary" style={{ fontSize: 11 }}>Mean: {stats?.mean?.toFixed(2) ?? 'N/A'}</Typography.Text>
                        <Typography.Text type="secondary" style={{ fontSize: 11 }}>Max: {max.toFixed(2)}</Typography.Text>
                      </Space>
                    </div>
                  )
                })}
              </div>
            </Card>
          </Col>
          <Col span={8}>
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
    </div>
  )
}
