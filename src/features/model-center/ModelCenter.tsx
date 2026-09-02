import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, Table, Select, Button, Space, Alert, Tag, message, Popconfirm } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { ExperimentOutlined, SwapOutlined } from '@ant-design/icons'
import Plot from 'react-plotly.js'
import { useDataPipelineStore } from '../../stores/dataPipelineStore'
import { useModelStore } from '../../stores/modelStore'
import type { ModelFitDTO, ModelType, ModelStatus, InteractionResult, SHAPResult } from '../../lib/engine'
import { computeInteractions, computeSHAP } from '../../lib/engine'

const MODEL_TYPES: { value: ModelType; labelKey: string }[] = [
  { value: 'doe_linear', labelKey: 'modelCenter.modelType.doeLinear' },
  { value: 'doe_quadratic', labelKey: 'modelCenter.modelType.doeQuadratic' },
  { value: 'random_forest', labelKey: 'modelCenter.modelType.randomForest' },
  { value: 'residual_hybrid', labelKey: 'modelCenter.modelType.residualHybrid' },
]

const STATUS_TRANSITIONS: Partial<Record<ModelStatus, ModelStatus[]>> = {
  draft: ['pending_validation'],
  pending_validation: ['validated'],
  validated: ['approved'],
  approved: ['retired'],
}

const STATUS_COLORS: Record<ModelStatus, string> = {
  draft: 'default',
  pending_validation: 'processing',
  validated: 'success',
  approved: 'gold',
  retired: 'error',
}

export default function ModelCenter() {
  const { t } = useTranslation()
  const [messageApi, contextHolder] = message.useMessage()
  const { importResult, fields, spec } = useDataPipelineStore()
  const {
    models, fitting, transitioning, error,
    selectedModelId, loadModels, fit, transition,
    selectModel, clearError,
  } = useModelStore()

  const [modelType, setModelType] = useState<ModelType>('doe_linear')
  const [selectedInputs, setSelectedInputs] = useState<string[]>([])
  const [target, setTarget] = useState<string | undefined>(spec?.outputField || undefined)
  const [compareIds, setCompareIds] = useState<string[]>([])
  const [interactions, setInteractions] = useState<InteractionResult | null>(null)
  const [interactionsLoading, setInteractionsLoading] = useState(false)
  const [shapResult, setShapResult] = useState<SHAPResult | null>(null)
  const [shapLoading, setShapLoading] = useState(false)

  const datasetId = importResult?.dataset_id
  const inputOptions = fields
    .filter((f) => f.role === 'input')
    .map((f) => ({ label: f.originalName, value: f.originalName }))
  const outputOptions = fields
    .filter((f) => f.role === 'output')
    .map((f) => ({ label: f.originalName, value: f.originalName }))

  useEffect(() => { loadModels() }, [])

  const handleFit = async () => {
    if (!datasetId || !target || selectedInputs.length === 0) return
    const result = await fit({ dataset_id: datasetId, model_type: modelType, target, inputs: selectedInputs })
    if (result) {
      messageApi.success(t('modelCenter.fitSuccess'))
    }
  }

  const handleTransition = async (modelId: string, newStatus: ModelStatus) => {
    await transition(modelId, newStatus)
    messageApi.success(t('modelCenter.transitionSuccess', { status: newStatus }))
  }

  const handleComputeInteractions = async () => {
    if (!models.length) return
    const modelId = models[models.length - 1].model_id
    if (!datasetId) return
    setInteractionsLoading(true)
    try {
      const result = await computeInteractions({ model_id: modelId, dataset_id: datasetId })
      setInteractions(result)
    } catch {
      messageApi.error('Failed to compute interactions')
    } finally {
      setInteractionsLoading(false)
    }
  }

  const handleComputeSHAP = async () => {
    if (!models.length || !datasetId) return
    const modelId = models[models.length - 1].model_id
    setShapLoading(true)
    try {
      const result = await computeSHAP({ model_id: modelId, dataset_id: datasetId })
      setShapResult(result)
    } catch {
      messageApi.error(t('modelCenter.shapError'))
    } finally {
      setShapLoading(false)
    }
  }

  const compareModels = models.filter((m) => compareIds.includes(m.model_id))

  const bestMetric = (key: 'r2' | 'rmse' | 'mae' | 'adj_r2') => {
    if (compareModels.length === 0) return null
    const higher = key === 'r2' || key === 'adj_r2'
    const vals = compareModels.map((m) => m.metrics[key])
    return higher ? Math.max(...vals) : Math.min(...vals)
  }

  if (!datasetId) {
    return (
      <Card title={t('modelCenter.title')}>
        <Alert type="info" showIcon message={t('modelCenter.noData')} />
      </Card>
    )
  }

  const columns: ColumnsType<ModelFitDTO> = [
    { title: t('modelCenter.column.type'), dataIndex: 'model_type', key: 'type', width: 150 },
    { title: t('modelCenter.column.version'), dataIndex: 'version', key: 'version', width: 80 },
    {
      title: t('modelCenter.column.status'), dataIndex: 'status', key: 'status', width: 160,
      render: (status: ModelStatus) => <Tag color={STATUS_COLORS[status]}>{status}</Tag>,
    },
    { title: 'R²', dataIndex: ['metrics', 'r2'], key: 'r2', width: 100, render: (v: number) => v?.toFixed(4) },
    { title: 'RMSE', dataIndex: ['metrics', 'rmse'], key: 'rmse', width: 100, render: (v: number) => v?.toFixed(4) },
    { title: 'MAE', dataIndex: ['metrics', 'mae'], key: 'mae', width: 100, render: (v: number) => v?.toFixed(4) },
    { title: 'Adj R²', dataIndex: ['metrics', 'adj_r2'], key: 'adj_r2', width: 100, render: (v: number) => v?.toFixed(4) },
    {
      title: t('modelCenter.column.actions'), key: 'actions', width: 200,
      render: (_, record) => {
        const nextStatuses = STATUS_TRANSITIONS[record.status] || []
        return (
          <Space size="small">
            {nextStatuses.map((s) => (
              <Popconfirm key={s} title={t('modelCenter.confirmTransition', { status: s })} onConfirm={() => handleTransition(record.model_id, s)}>
                <Button size="small" loading={transitioning}>{s}</Button>
              </Popconfirm>
            ))}
          </Space>
        )
      },
    },
  ]

  return (
    <>
      {contextHolder}
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {error && <Alert type="error" showIcon message={error} closable onClose={clearError} />}

        <Card title={t('modelCenter.fitTitle')} extra={<ExperimentOutlined />}>
          <Space direction="vertical" style={{ width: '100%' }}>
            <div>
              <label>{t('modelCenter.modelType.label')}</label>
              <Select
                style={{ width: 240, marginLeft: 8 }}
                value={modelType}
                onChange={setModelType}
                options={MODEL_TYPES.map((m) => ({ value: m.value, label: t(m.labelKey) }))}
              />
            </div>
            <div>
              <label>{t('modelCenter.target.label')}</label>
              <Select
                style={{ width: 240, marginLeft: 8 }}
                value={target}
                onChange={setTarget}
                options={outputOptions}
                placeholder={t('modelCenter.target.placeholder')}
              />
            </div>
            <div>
              <label>{t('modelCenter.inputs.label')}</label>
              <Select
                mode="multiple"
                style={{ width: 400, marginLeft: 8 }}
                value={selectedInputs}
                onChange={setSelectedInputs}
                options={inputOptions}
                placeholder={t('modelCenter.inputs.placeholder')}
              />
            </div>
            <Button type="primary" loading={fitting} onClick={handleFit} disabled={!datasetId || !target || selectedInputs.length === 0}>
              {t('modelCenter.fitButton')}
            </Button>
          </Space>
        </Card>

        <Card title={t('modelCenter.listTitle')} size="small"
          extra={compareIds.length >= 2 && (
            <Button size="small" icon={<SwapOutlined />} onClick={() => {}}>
              {t('modelCenter.compareButton')} ({compareIds.length})
            </Button>
          )}
        >
          <Table
            size="small"
            rowKey="model_id"
            columns={columns}
            dataSource={models}
            pagination={false}
            rowSelection={{
              selectedRowKeys: compareIds,
              onChange: (keys) => setCompareIds(keys as string[]),
            }}
            rowClassName={(r) => (r.model_id === selectedModelId ? 'ant-table-row-selected' : '')}
            onRow={(record) => ({ onClick: () => selectModel(record.model_id) })}
          />
        </Card>

        {compareModels.length >= 2 && (
          <Card title={t('modelCenter.compareTitle')} size="small">
            <Table
              size="small"
              pagination={false}
              dataSource={[
                { metric: 'R²', key: 'r2', higher: true },
                { metric: 'RMSE', key: 'rmse', higher: false },
                { metric: 'MAE', key: 'mae', higher: false },
                { metric: 'Adj R²', key: 'adj_r2', higher: true },
              ]}
              columns={[
                { title: t('modelCenter.compareMetric'), dataIndex: 'metric', key: 'metric', width: 120 },
                ...compareModels.map((m) => ({
                  title: `${m.model_type} v${m.version}`,
                  key: m.model_id,
                  width: 140,
                  render: (_: unknown, row: { key: string; higher: boolean }) => {
                    const val = m.metrics[row.key as keyof typeof m.metrics]
                    const best = bestMetric(row.key as 'r2' | 'rmse' | 'mae' | 'adj_r2')
                    const isBest = val === best
                    return (
                      <span style={{ fontWeight: isBest ? 700 : 400, color: isBest ? '#16a34a' : undefined }}>
                        {val?.toFixed(4)}{isBest ? ' ★' : ''}
                      </span>
                    )
                  },
                })),
              ]}
            />
          </Card>
        )}

        <Card title={t('modelCenter.interactionsTitle')} size="small">
          <Space direction="vertical" style={{ width: '100%' }} size="small">
            <Button
              type="primary"
              loading={interactionsLoading}
              onClick={handleComputeInteractions}
              disabled={models.length === 0 || !datasetId}
            >
              {interactionsLoading ? t('modelCenter.computing') : t('modelCenter.computeInteractions')}
            </Button>
            {interactions ? (
              <Table
                size="small"
                pagination={false}
                dataSource={interactions.factors.map((rowFactor, ri) => ({
                   ...interactions.factors.reduce((acc, _, ci) => {
                    acc[`col_${ci}`] = interactions.matrix[ri]?.[ci] ?? 0
                    return acc
                  }, {} as Record<string, number>),
                  factor: rowFactor,
                }))}
                columns={[
                  {
                    title: '',
                    dataIndex: 'factor',
                    key: 'factor',
                    width: 120,
                    render: (v: string) => <strong>{v}</strong>,
                  },
                  ...interactions.factors.map((_, ci) => ({
                    title: <strong>{interactions.factors[ci]}</strong>,
                    key: `col_${ci}`,
                    width: 80,
                    render: (record: Record<string, number>) => {
                      const strength = record[`col_${ci}`] ?? 0
                      const max = Math.max(...interactions.matrix.flat())
                      const intensity = max > 0 ? strength / max : 0
                      return (
                        <div
                          style={{
                            height: 24,
                            backgroundColor: `rgba(220, 38, 38, ${intensity * 0.8})`,
                            borderRadius: 2,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            color: intensity > 0.3 ? '#fff' : '#000',
                            fontSize: 11,
                          }}
                        >
                          {strength > 0 ? strength.toFixed(2) : ''}
                        </div>
                      )
                    },
                  })),
                ]}
                rowKey="factor"
              />
            ) : (
              <Alert type="info" showIcon message={t('modelCenter.noInteraction')} />
            )}
          </Space>
        </Card>

        <Card title={t('modelCenter.shapTitle')} size="small">
          <Space direction="vertical" style={{ width: '100%' }} size="small">
            <Button
              type="primary"
              loading={shapLoading}
              onClick={handleComputeSHAP}
              disabled={models.length === 0 || !datasetId}
            >
              {shapLoading ? t('modelCenter.computingSHAP') : t('modelCenter.computeSHAP')}
            </Button>
            {shapResult ? (
              <Space direction="vertical" style={{ width: '100%' }} size="small">
                <Plot
                  data={[{
                    x: shapResult.feature_importance.map(f => f.importance),
                    y: shapResult.feature_importance.map(f => f.name),
                    type: 'bar' as const,
                    orientation: 'h',
                    marker: { color: '#2563EB' }
                  }]}
                  layout={{
                    title: { text: t('modelCenter.shapImportanceTitle') },
                    xaxis: { title: { text: t('modelCenter.shapImportance') } },
                    margin: { l: 100 }
                  }}
                  useResizeHandler
                  style={{ width: '100%', height: 200 }}
                />
                <Plot
                  data={[{
                    x: shapResult.shap_values.flat(),
                    y: shapResult.feature_importance.map((_, i) =>
                      Array(shapResult.shap_values.length).fill(shapResult.feature_importance[i].name)
                    ).flat(),
                    type: 'scatter' as const,
                    mode: 'markers',
                    marker: { size: 6, opacity: 0.6 }
                  }]}
                  layout={{
                    title: { text: t('modelCenter.shapSummaryTitle') },
                    yaxis: { automargin: true },
                    xaxis: { title: { text: 'SHAP value' } },
                    margin: { l: 60 }
                  }}
                  useResizeHandler
                  style={{ width: '100%', height: 300 }}
                />
              </Space>
            ) : (
              <Alert type="info" showIcon message={t('modelCenter.noInteraction')} />
            )}
          </Space>
        </Card>
      </Space>
    </>
  )
}
