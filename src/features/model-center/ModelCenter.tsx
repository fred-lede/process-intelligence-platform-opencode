import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, Table, Select, Button, Space, Alert, Tag, message, Popconfirm, Switch, InputNumber } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { ExperimentOutlined, SwapOutlined } from '@ant-design/icons'
import Plot from 'react-plotly.js'
import { useDataPipelineStore } from '../../stores/dataPipelineStore'
import { useModelStore } from '../../stores/modelStore'
import { useAssistantContextStore } from '../../stores/assistantContextStore'
import { buildModelCenterContext } from '../../lib/assistantData'
import type { ModelFitDTO, ModelType, ModelStatus, InteractionResult, SHAPResult, ExtrapolationResult, ValidationResult, FullValidationResult } from '../../lib/engine'
import { computeInteractions, computeSHAP, checkExtrapolation, analyzeValidation, runFullValidation } from '../../lib/engine'

const MODEL_TYPES: { value: ModelType; labelKey: string }[] = [
  { value: 'doe_linear', labelKey: 'modelCenter.modelType.doeLinear' },
  { value: 'doe_quadratic', labelKey: 'modelCenter.modelType.doeQuadratic' },
  { value: 'random_forest', labelKey: 'modelCenter.modelType.randomForest' },
  { value: 'residual_hybrid', labelKey: 'modelCenter.modelType.residualHybrid' },
  { value: 'logistic_regression', labelKey: 'modelCenter.modelType.logisticRegression' },
  { value: 'weibull_regression', labelKey: 'modelCenter.modelType.weibullRegression' },
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
  const { setContext } = useAssistantContextStore()
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
  const [extrapResult, setExtrapResult] = useState<ExtrapolationResult | null>(null)
  const [extrapLoading, setExtrapLoading] = useState(false)
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null)
  const [validationLoading, setValidationLoading] = useState(false)
  const [cvFolds, setCvFolds] = useState(5)
  const [fullValidation, setFullValidation] = useState<FullValidationResult | null>(null)
  const [fullValidationLoading, setFullValidationLoading] = useState(false)
  const [nEstimators, setNEstimators] = useState(200)
  const [maxDepth, setMaxDepth] = useState(10)
  const [minSamplesLeaf, setMinSamplesLeaf] = useState(3)
  const [learningRate, setLearningRate] = useState(0.1)
  const [autoSelectFeatures, setAutoSelectFeatures] = useState(false)

  useEffect(() => {
    setContext(
      'modelCenter',
      buildModelCenterContext({ interactions, shapResult, extrapResult, validationResult, fullValidation }),
    )
  }, [interactions, shapResult, extrapResult, validationResult, fullValidation, setContext])

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
    const params: any = {
      dataset_id: datasetId,
      model_type: modelType,
      target,
      inputs: selectedInputs,
    }
    if (['random_forest', 'xgboost', 'lightgbm'].includes(modelType)) {
      params.n_estimators = nEstimators
      params.max_depth = maxDepth
      params.min_samples_leaf = modelType === 'random_forest' ? minSamplesLeaf : undefined
      params.learning_rate = learningRate
      params.auto_select_features = autoSelectFeatures
    }
    const result = await fit(params)
    if (result) {
      if (result.selected_inputs && result.selected_inputs.length < selectedInputs.length) {
        setSelectedInputs(result.selected_inputs)
      }
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

  const handleCheckExtrapolation = async () => {
    if (!datasetId || !models.length) return
    const latestModel = models[models.length - 1]
    const predictionPoints = [
      { ...latestModel.inputs.reduce((acc, inp) => ({ ...acc, [inp]: 5.0 }), {} as Record<string, number>) },
      { ...latestModel.inputs.reduce((acc, inp) => ({ ...acc, [inp]: 15.0 }), {} as Record<string, number>) },
      { ...latestModel.inputs.reduce((acc, inp) => ({ ...acc, [inp]: -5.0 }), {} as Record<string, number>) },
    ]
    setExtrapLoading(true)
    try {
      const result = await checkExtrapolation({ dataset_id: datasetId, prediction_points: predictionPoints })
      setExtrapResult(result)
    } catch {
      messageApi.error(t('modelCenter.extrapError'))
    } finally {
      setExtrapLoading(false)
    }
  }

  const handleRunValidation = async () => {
    if (!models.length || !datasetId) return
    const modelId = models[models.length - 1].model_id
    setValidationLoading(true)
    try {
      const result = await analyzeValidation({ model_id: modelId, dataset_id: datasetId, k: cvFolds })
      setValidationResult(result)
    } catch {
      messageApi.error(t('modelCenter.validationError'))
    } finally {
      setValidationLoading(false)
    }
  }

  const handleRunFullValidation = async () => {
    if (!datasetId || !models.length) return
    const modelIds = models.map(m => m.model_id)
    setFullValidationLoading(true)
    try {
      const result = await runFullValidation({ dataset_id: datasetId, model_ids: modelIds })
      setFullValidation(result)
    } catch {
      messageApi.error(t('modelCenter.fullValidationError'))
    } finally {
      setFullValidationLoading(false)
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
            {['random_forest', 'xgboost', 'lightgbm'].includes(modelType) && (
              <Card title={t('modelCenter.treeModelAdvanced')} size="small">
                <Space direction="vertical" style={{ width: '100%' }}>
                  <div>
                    <Switch
                      checked={autoSelectFeatures}
                      onChange={setAutoSelectFeatures}
                      checkedChildren={t('modelCenter.autoFeatureSelect')}
                      unCheckedChildren={t('modelCenter.autoFeatureSelect')}
                    />
                  </div>
                  {!autoSelectFeatures && (
                    <>
                      <div>
                        <label>{t('modelCenter.nEstimators')}</label>
                        <InputNumber
                          min={50}
                          max={500}
                          value={nEstimators}
                          onChange={(v) => setNEstimators(v || 200)}
                          style={{ marginLeft: 8, width: 100 }}
                        />
                      </div>
                      <div>
                        <label>{t('modelCenter.maxDepth')}</label>
                        <InputNumber
                          min={1}
                          max={20}
                          value={maxDepth}
                          onChange={(v) => setMaxDepth(v || 10)}
                          style={{ marginLeft: 8, width: 100 }}
                        />
                      </div>
                      <div>
                        <label>{t('modelCenter.learningRate')}</label>
                        <InputNumber
                          min={0.01}
                          max={1}
                          step={0.01}
                          value={learningRate}
                          onChange={(v) => setLearningRate(v || 0.1)}
                          style={{ marginLeft: 8, width: 100 }}
                        />
                      </div>
                      {modelType === 'random_forest' && (
                        <div>
                          <label>{t('modelCenter.minSamplesLeaf')}</label>
                          <InputNumber
                            min={1}
                            max={10}
                            value={minSamplesLeaf}
                            onChange={(v) => setMinSamplesLeaf(v || 3)}
                            style={{ marginLeft: 8, width: 100 }}
                          />
                        </div>
                      )}
                    </>
                  )}
                </Space>
              </Card>
            )}
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

        <Card title={t('modelCenter.extrapTitle')} size="small">
          <Space direction="vertical" style={{ width: '100%' }} size="small">
            <Button
              type="primary"
              loading={extrapLoading}
              onClick={handleCheckExtrapolation}
              disabled={models.length === 0 || !datasetId}
            >
              {extrapLoading ? t('modelCenter.checking') : t('modelCenter.checkExtrapolation')}
            </Button>
            {extrapResult ? (
              <Space direction="vertical" style={{ width: '100%' }} size="small">
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <span style={{ fontWeight: 500 }}>{t('modelCenter.riskScore')}:</span>
                  <span style={{
                    fontSize: 24,
                    fontWeight: 700,
                    color: extrapResult.max_risk === 0 ? '#16a34a' : extrapResult.max_risk < 0.5 ? '#ca8a04' : '#dc2626',
                  }}>
                    {extrapResult.max_risk.toFixed(2)}
                  </span>
                  <Tag color={extrapResult.max_risk === 0 ? 'success' : extrapResult.max_risk < 0.5 ? 'warning' : 'error'}>
                    {extrapResult.is_extrapolation ? 'Extrapolation Detected' : 'All within range'}
                  </Tag>
                </div>
                <div>
                  <strong>{t('modelCenter.safeRange')}:</strong>
                  {Object.entries(extrapResult.factor_risks).map(([name, data]) => (
                    <div key={name} style={{ marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span>{name}:</span>
                      <span style={{
                        color: data.risk === 0 ? '#16a34a' : data.risk < 0.5 ? '#ca8a04' : '#dc2626',
                      }}>
                        Risk: {data.risk.toFixed(2)}
                      </span>
                      <span style={{ color: '#6b7280', fontSize: 12 }}>(range: {data.min.toFixed(1)}–{data.max.toFixed(1)})</span>
                    </div>
                  ))}
                </div>
              </Space>
            ) : (
              <Alert type="info" showIcon message={t('modelCenter.noExtrap')} />
            )}
          </Space>
        </Card>

        <Card title={t('modelCenter.validationTitle')} size="small">
          <Space direction="vertical" style={{ width: '100%' }} size="small">
            <Space>
              <span>{t('modelCenter.cvFolds')}:</span>
              <Select
                value={cvFolds}
                onChange={setCvFolds}
                options={[
                  { value: 3, label: '3' },
                  { value: 5, label: '5' },
                  { value: 10, label: '10' },
                ]}
                style={{ width: 80 }}
              />
              <Button
                type="primary"
                loading={validationLoading}
                onClick={handleRunValidation}
                disabled={models.length === 0 || !datasetId}
              >
                {validationLoading ? t('modelCenter.runningValidation') : t('modelCenter.runValidation')}
              </Button>
            </Space>
            {validationResult ? (
              <Space direction="vertical" style={{ width: '100%' }} size="small">
                <div>
                  <strong>{t('modelCenter.meanMetrics')}:</strong>
                  <span style={{ marginLeft: 8 }}>R²: {validationResult.mean_metrics.mean_r2.toFixed(4)}</span>
                  <span style={{ marginLeft: 8 }}>RMSE: {validationResult.mean_metrics.mean_rmse.toFixed(4)}</span>
                </div>
                <Table
                  size="small"
                  dataSource={validationResult.cv_results}
                  pagination={false}
                  columns={[
                    { title: 'Fold', dataIndex: 'fold', key: 'fold', width: 60 },
                    { title: 'R²', dataIndex: 'r2', key: 'r2', render: (v: number) => v?.toFixed(4) },
                    { title: 'RMSE', dataIndex: 'rmse', key: 'rmse', render: (v: number) => v?.toFixed(4) },
                  ]}
                />
                <div>
                  <strong>{t('modelCenter.residualStats')}:</strong>
                  <span style={{ marginLeft: 8 }}>mean={validationResult.stats.mean.toFixed(4)}</span>
                  <span style={{ marginLeft: 8 }}>std={validationResult.stats.std.toFixed(4)}</span>
                </div>
                <div>
                  <strong>{t('modelCenter.normalityTest')}:</strong>
                  <Tag color={validationResult.normality_test.is_normal ? 'success' : 'error'}>
                    {validationResult.normality_test.is_normal
                      ? t('modelCenter.isNormal')
                      : t('modelCenter.notNormal')}
                  </Tag>
                </div>
                <div>
                  <strong>{t('modelCenter.recommendations')}:</strong>
                  {validationResult.recommendations.map((rec, i) => (
                    <Alert
                      key={i}
                      style={{ marginTop: 4 }}
                      type={rec.type === 'interaction' ? 'warning' : 'info'}
                      message={`${rec.type}: ${rec.reason}`}
                      showIcon
                    />
                  ))}
                </div>
              </Space>
            ) : (
              <Alert type="info" showIcon message={t('modelCenter.noInteraction')} />
            )}
          </Space>
        </Card>

        <Card title={t('modelCenter.fullValidationTitle')} size="small">
          <Space direction="vertical" style={{ width: '100%' }} size="small">
            <Button
              type="primary"
              loading={fullValidationLoading}
              onClick={handleRunFullValidation}
              disabled={models.length === 0 || !datasetId}
            >
              {fullValidationLoading ? t('modelCenter.runningFullValidation') : t('modelCenter.runFullValidation')}
            </Button>
            {fullValidation ? (
              <Space direction="vertical" style={{ width: '100%' }} size="small">
                <div>
                  <strong>{t('modelCenter.bestModel')}:</strong>
                  <Tag color="gold">{fullValidation.models.find(m => m.model_id === fullValidation.best_model_id)?.model_type}</Tag>
                  <span style={{ marginLeft: 8, color: '#16a34a', fontWeight: 700 }}>
                    Score: {fullValidation.models.find(m => m.model_id === fullValidation.best_model_id)?.score.toFixed(4)}
                  </span>
                </div>
                <Table
                  size="small"
                  pagination={false}
                  dataSource={fullValidation.models.map((m, idx) => ({ ...m, key: idx }))}
                  columns={[
                    { title: t('modelCenter.column.type'), dataIndex: 'model_type', key: 'model_type', width: 150 },
                    { title: 'R²', dataIndex: ['cv_metrics', 'mean_r2'], key: 'r2', render: (v: number) => v?.toFixed(4) },
                    { title: 'RMSE', dataIndex: ['cv_metrics', 'mean_rmse'], key: 'rmse', render: (v: number) => v?.toFixed(4) },
                    {
                      title: t('modelCenter.normalityTest'),
                      dataIndex: 'residual_normal',
                      key: 'residual_normal',
                      render: (v: boolean) => (
                        <Tag color={v ? 'success' : 'error'}>{v ? t('modelCenter.isNormal') : t('modelCenter.notNormal')}</Tag>
                      ),
                    },
                    { title: 'Score', dataIndex: 'score', key: 'score', render: (v: number) => v?.toFixed(4) },
                  ]}
                />
                <div>
                  <strong>{t('modelCenter.residualDiagnostics')}:</strong>
                  <div style={{ marginTop: 4, fontSize: 12, color: '#6b7280' }}>
                    DW: {fullValidation.residual_analysis.durbin_watson.statistic.toFixed(3)}
                    {' '}({fullValidation.residual_analysis.durbin_watson.interpretation})
                  </div>
                </div>
                <div>
                  <strong>{t('modelCenter.experimentRecommendations')}:</strong>
                  {fullValidation.experiment_recommendations.recommendations.map((rec, i) => (
                    <Alert
                      key={i}
                      style={{ marginTop: 4 }}
                      type={rec.priority === 'high' ? 'warning' : rec.priority === 'medium' ? 'warning' : 'info'}
                      message={
                        <span>
                          <Tag color={rec.priority === 'high' ? 'red' : rec.priority === 'medium' ? 'orange' : 'default'}>
                            {rec.priority}
                          </Tag>
                          {rec.type}: {rec.reason}
                        </span>
                      }
                      showIcon
                    />
                  ))}
                  <div style={{ marginTop: 4, fontSize: 12, color: '#6b7280' }}>
                    {fullValidation.experiment_recommendations.summary}
                  </div>
                </div>
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
