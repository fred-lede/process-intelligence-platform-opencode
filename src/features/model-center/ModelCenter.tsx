import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, Table, Select, Button, Space, Alert, Tag, message, Popconfirm, Switch, InputNumber, Typography, Descriptions } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { ExperimentOutlined, SwapOutlined } from '@ant-design/icons'
import Plot from '../../components/PlotChart'
import { useDataPipelineStore } from '../../stores/dataPipelineStore'
import { useModelStore } from '../../stores/modelStore'
import { useAssistantContextStore } from '../../stores/assistantContextStore'
import { buildModelCenterContext } from '../../lib/assistantData'
import type { ModelFitDTO, ModelType, ModelStatus, InteractionResult, SHAPResult, ExtrapolationResult, ValidationResult, FullValidationResult, ReadinessResult, SensitivityEffectResult, TimeSeriesModelResult, TimeSeriesValidationResult, TimeSeriesLadderResult } from '../../lib/engine'
import { checkModelApplicability, recommendModels, computeInteractions, computeSHAP, checkExtrapolation, analyzeValidation, runFullValidation, computeDOEStatistics, computeSensitivity, runReadiness, prepareTimeSeriesModel, validateTimeSeries, fitTimeSeriesLadder, type DoeStatisticsResult } from '../../lib/engine'

const MODEL_TYPES: { value: ModelType; labelKey: string }[] = [
  { value: 'doe_linear', labelKey: 'modelCenter.modelType.doeLinear' },
  { value: 'doe_quadratic', labelKey: 'modelCenter.modelType.doeQuadratic' },
  { value: 'random_forest', labelKey: 'modelCenter.modelType.randomForest' },
  { value: 'residual_hybrid', labelKey: 'modelCenter.modelType.residualHybrid' },
  { value: 'logistic_regression', labelKey: 'modelCenter.modelType.logisticRegression' },
  { value: 'weibull_regression', labelKey: 'modelCenter.modelType.weibullRegression' },
  { value: 'xgboost', labelKey: 'modelCenter.modelType.xgboost' },
  { value: 'lightgbm', labelKey: 'modelCenter.modelType.lightgbm' },
]

const MODEL_DESC_KEY: Record<ModelType, string> = {
  doe_linear: 'doeLinear',
  doe_quadratic: 'doeQuadratic',
  random_forest: 'randomForest',
  residual_hybrid: 'residualHybrid',
  logistic_regression: 'logisticRegression',
  weibull_regression: 'weibullRegression',
  xgboost: 'xgboost',
  lightgbm: 'lightgbm',
}

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
  const { t, i18n } = useTranslation()
  const [messageApi, contextHolder] = message.useMessage()
  const { importResult, fields, spec } = useDataPipelineStore()
  const { setContext } = useAssistantContextStore()
  const {
    models, fitting, transitioning, deleting, error,
    selectedModelId, loadModels, fit, transition, deleteModel: deleteModelFn,
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
  const [doeStats, setDoeStats] = useState<DoeStatisticsResult | null>(null)
  const [doeStatsLoading, setDoeStatsLoading] = useState(false)
  const [sensitivity, setSensitivity] = useState<SensitivityEffectResult | null>(null)
  const [sensitivityLoading, setSensitivityLoading] = useState(false)
  const [nEstimators, setNEstimators] = useState(200)
  const [maxDepth, setMaxDepth] = useState(10)
  const [minSamplesLeaf, setMinSamplesLeaf] = useState(3)
  const [learningRate, setLearningRate] = useState(0.1)
  const [autoSelectFeatures, setAutoSelectFeatures] = useState(false)
  const [governance, setGovernance] = useState<string[]>([])
  const [recommended, setRecommended] = useState<string[]>([])
  const [readiness, setReadiness] = useState<ReadinessResult | null>(null)
  const [modelingMode, setModelingMode] = useState<'standard' | 'time_series'>('standard')
  const [timeColumn, setTimeColumn] = useState<string | undefined>(
    fields.find((field) => field.role === 'timestamp')?.originalName,
  )
  const [timeWindowDays, setTimeWindowDays] = useState(30)
  const [timeLags, setTimeLags] = useState<number[]>([1, 7])
  const [rollingWindows, setRollingWindows] = useState<number[]>([7])
  const [timeValidationStrategy, setTimeValidationStrategy] = useState<'holdout' | 'walk_forward'>('holdout')
  const [timeSeriesLoading, setTimeSeriesLoading] = useState(false)
  const [timeSeriesLadder, setTimeSeriesLadder] = useState<TimeSeriesLadderResult | null>(null)
  const [timeSeriesLadderLoading, setTimeSeriesLadderLoading] = useState(false)
  const timeSeriesRequestId = useRef(0)
  const timeSeriesLadderRequestId = useRef(0)
  const [timeSeriesRun, setTimeSeriesRun] = useState<{
    model: TimeSeriesModelResult
    validation: TimeSeriesValidationResult | null
    windowDays: number
    validationFailed: boolean
  } | null>(null)

  useEffect(() => {
    setContext(
      'modelCenter',
      buildModelCenterContext({ interactions, shapResult, extrapResult, validationResult, fullValidation, doeStats, sensitivity, governanceWarnings: governance, recommendedInputs: recommended, readiness: readiness ?? undefined }),
    )
  }, [interactions, shapResult, extrapResult, validationResult, fullValidation, doeStats, sensitivity, governance, recommended, readiness, setContext])

  const datasetId = importResult?.dataset_id
  const latestModel = models[models.length - 1]
  const interactionModelType = latestModel?.model_type ?? modelType
  const interactionMode = interactionModelType === 'doe_linear'
    ? 'notModeled'
    : interactionModelType === 'doe_quadratic'
      ? 'explicit'
      : ['random_forest', 'xgboost', 'lightgbm'].includes(interactionModelType)
        ? 'implicit'
        : interactionModelType === 'residual_hybrid' ? 'hybrid' : 'notModeled'
  useEffect(() => {
    if (!datasetId || !fields.length) return
    runReadiness(datasetId, fields.filter(f => f.role === 'input' || f.role === 'output').map(f => ({ name: f.originalName, role: f.role }))).then(setReadiness).catch(() => setReadiness(null))
  }, [datasetId, fields])
  useEffect(() => {
    let active = true
    setGovernance([])
    setRecommended([])
    if (datasetId && target && selectedInputs.length) {
      Promise.all([
        checkModelApplicability(datasetId, target, selectedInputs, modelType === 'logistic_regression'),
        recommendModels(importResult?.row_count ?? 0, selectedInputs.length, modelType === 'logistic_regression', false, true),
      ]).then(([check, rec]) => { if (active) { setGovernance(check.warnings); setRecommended(rec.recommendations) } })
        .catch(e => { if (active) setGovernance([String(e)]) })
    }
    return () => { active = false }
  }, [datasetId, target, selectedInputs, modelType])
  const inputOptions = fields
    .filter((f) => f.role === 'input')
    .map((f) => ({ label: f.originalName, value: f.originalName }))
  const outputOptions = fields
    .filter((f) => f.role === 'output')
    .map((f) => ({ label: f.originalName, value: f.originalName }))
  const binaryTargetOptions = importResult
    ? Object.entries(importResult.stats.column_stats)
        .filter(([, s]) => (s.numeric && s.unique_count <= 10) || s.unique_count === 2)
        .map(([name]) => ({ label: name, value: name }))
    : []
  const targetOptions = modelType === 'logistic_regression'
    ? binaryTargetOptions.length > 0
      ? binaryTargetOptions
      : outputOptions
    : outputOptions
  const visibleTargetOptions = modelingMode === 'time_series' ? outputOptions : targetOptions
  const timeColumnOptions = (importResult?.columns ?? []).map((name) => ({
    label: fields.find((field) => field.originalName === name)?.role === 'timestamp'
      ? `${name} (${t('modelCenter.timeSeries.detectedTimestamp')})`
      : name,
    value: name,
  }))

  useEffect(() => { loadModels() }, [])

  const invalidateTimeSeriesRun = () => {
    timeSeriesRequestId.current += 1
    timeSeriesLadderRequestId.current += 1
    setTimeSeriesRun(null)
    setTimeSeriesLadder(null)
    setTimeSeriesLoading(false)
    setTimeSeriesLadderLoading(false)
  }

  const handleFitTimeSeriesLadder = async () => {
    if (!datasetId || !timeColumn || !target || selectedInputs.length === 0) return
    const requestId = timeSeriesLadderRequestId.current + 1
    timeSeriesLadderRequestId.current = requestId
    setTimeSeriesLadderLoading(true)
    try {
      const result = await fitTimeSeriesLadder({ dataset_id: datasetId, time_column: timeColumn, target, inputs: selectedInputs, lags: timeLags, rolling_windows: rollingWindows, modeling_timezone: 'UTC', window_days: timeWindowDays })
      if (requestId !== timeSeriesLadderRequestId.current) return
      setTimeSeriesLadder(result)
      messageApi.success(t('modelCenter.timeSeries.ladderSuccess'))
    } catch (err) {
      if (requestId !== timeSeriesLadderRequestId.current) return
      messageApi.error(`${t('modelCenter.timeSeries.ladderError')}: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      if (requestId === timeSeriesLadderRequestId.current) setTimeSeriesLadderLoading(false)
    }
  }

  const timeSeriesModelLabel = (name: string) => t(`modelCenter.timeSeries.models.${name}`, { defaultValue: name })
  const timeSeriesReason = (reason?: string | null, code?: string | null) => {
    if (!reason && !code) return '—'
    if (code) return t(`modelCenter.timeSeries.reasons.${code}`, { defaultValue: t('modelCenter.timeSeries.reasons.unknown') })
    return t('modelCenter.timeSeries.reasons.unknown')
  }

  useEffect(() => {
    invalidateTimeSeriesRun()
  }, [datasetId])

  useEffect(() => {
    if (!timeColumn) {
      setTimeColumn(fields.find((field) => field.role === 'timestamp')?.originalName)
    }
  }, [fields, timeColumn])

  const handleFit = async () => {
    if (!datasetId || !target || selectedInputs.length === 0) return
    if (modelType === 'logistic_regression') {
      const uq = importResult?.stats.column_stats?.[target]?.unique_count ?? 0
      if (uq > 10) {
        messageApi.warning(t('modelCenter.continuousTarget', { column: target, n: uq }))
        return
      }
    }
    const params: {
      dataset_id: string
      model_type: ModelType
      target: string
      inputs: string[]
      n_estimators?: number
      max_depth?: number
      min_samples_leaf?: number
      learning_rate?: number
      auto_select_features?: boolean
    } = {
      dataset_id: datasetId,
      model_type: modelType,
      target,
      inputs: selectedInputs,
    }
    if (['random_forest', 'xgboost', 'lightgbm'].includes(modelType)) {
      params.n_estimators = nEstimators
      params.max_depth = maxDepth
      params.min_samples_leaf = modelType === 'random_forest' ? minSamplesLeaf : undefined
      if (modelType !== 'random_forest') {
        params.learning_rate = learningRate
      }
      params.auto_select_features = autoSelectFeatures
    }
    const result = await fit(params)
    if (result) {
      if (result.selected_inputs && result.selected_inputs.length < selectedInputs.length) {
        setSelectedInputs(result.selected_inputs)
        messageApi.info(t('modelCenter.featureSelected', { count: result.selected_inputs.length }))
      }
      messageApi.success(t('modelCenter.fitSuccess'))
    }
  }

  const handlePrepareTimeSeries = async () => {
    if (!datasetId || !timeColumn || !target || selectedInputs.length === 0) return
    const requestId = timeSeriesRequestId.current + 1
    timeSeriesRequestId.current = requestId
    setTimeSeriesLoading(true)
    try {
      const model = await prepareTimeSeriesModel({
        dataset_id: datasetId,
        time_column: timeColumn,
        target,
        inputs: selectedInputs,
        lags: timeLags,
        rolling_windows: rollingWindows,
        modeling_timezone: 'UTC',
        window_days: timeWindowDays,
      })
      if (requestId !== timeSeriesRequestId.current) return
      setTimeSeriesRun({ model, validation: null, windowDays: timeWindowDays, validationFailed: false })
      const validationParams = timeValidationStrategy === 'holdout'
        ? {
            dataset_id: datasetId,
            time_column: timeColumn,
            strategy: 'holdout' as const,
            train_ratio: 0.7,
            validation_ratio: 0.15,
            prediction_time_column: timeColumn,
            window_days: timeWindowDays,
          }
        : {
            dataset_id: datasetId,
            time_column: timeColumn,
            strategy: 'walk_forward' as const,
            initial_train_size: Math.max(1, Math.floor(model.sorted_row_count * 0.6)),
            horizon: Math.max(1, Math.floor(model.sorted_row_count * 0.2)),
            step: Math.max(1, Math.floor(model.sorted_row_count * 0.2)),
            prediction_time_column: timeColumn,
            window_days: timeWindowDays,
          }
      try {
        const validation = await validateTimeSeries({ ...validationParams, modeling_timezone: 'UTC' })
        if (requestId !== timeSeriesRequestId.current) return
        setTimeSeriesRun({ model, validation, windowDays: timeWindowDays, validationFailed: false })
        messageApi.success(t('modelCenter.timeSeries.runSuccess'))
      } catch {
        if (requestId !== timeSeriesRequestId.current) return
        setTimeSeriesRun({ model, validation: null, windowDays: timeWindowDays, validationFailed: true })
        messageApi.warning(t('modelCenter.timeSeries.validationUnavailable'))
      }
    } catch (err) {
      if (requestId !== timeSeriesRequestId.current) return
      setTimeSeriesRun(null)
      messageApi.error(`${t('modelCenter.timeSeries.runError')}: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      if (requestId === timeSeriesRequestId.current) setTimeSeriesLoading(false)
    }
  }

  const handleTransition = async (modelId: string, newStatus: ModelStatus) => {
    await transition(modelId, newStatus)
    messageApi.success(t('modelCenter.transitionSuccess', { status: newStatus }))
  }

  const handleDeleteModel = async (modelId: string) => {
    await deleteModelFn(modelId)
    messageApi.success(t('modelCenter.deleteModelSuccess'))
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

  const handleComputeDOEStatistics = async () => {
    if (!models.length) return
    const modelId = models[models.length - 1].model_id
    if (!datasetId) return
    setDoeStatsLoading(true)
    try {
      const result = await computeDOEStatistics({ model_id: modelId, dataset_id: datasetId })
      setDoeStats(result.statistics)
    } catch {
      setDoeStats(null)
    } finally {
      setDoeStatsLoading(false)
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

  const handleComputeSensitivity = async () => {
    if (!models.length || !datasetId) return
    setSensitivityLoading(true)
    try {
      const result = await computeSensitivity(models[models.length - 1].model_id, datasetId)
      setSensitivity(result.analysis)
    } catch {
      messageApi.error(t('modelCenter.sensitivityError'))
    } finally {
      setSensitivityLoading(false)
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
    } catch (err) {
      messageApi.error(`${t('modelCenter.fullValidationError')}: ${err instanceof Error ? err.message : String(err)}`)
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

  const formatSplitRange = (indices: number[]) => {
    if (!timeSeriesRun?.validation || indices.length === 0) return '—'
    const timestamps = indices
      .map((index) => timeSeriesRun.validation?.normalized_timestamps[index])
      .filter((value): value is string => value !== null && value !== undefined)
      .map((value) => new Date(value))
      .filter((value) => !Number.isNaN(value.getTime()))
      .sort((a, b) => a.getTime() - b.getTime())
    if (timestamps.length === 0) return '—'
    const locale = i18n.resolvedLanguage ?? i18n.language
    const timeZone = String(timeSeriesRun.validation.configuration.modeling_timezone ?? 'UTC')
    const includeTime = ['minute', 'hourly'].includes(timeSeriesRun.model.feature_configuration.frequency)
    const formatter = new Intl.DateTimeFormat(locale, {
      timeZone,
      year: 'numeric', month: '2-digit', day: '2-digit',
      ...(includeTime ? { hour: '2-digit', minute: '2-digit' } : {}),
    })
    const first = formatter.format(timestamps[0])
    const last = formatter.format(timestamps[timestamps.length - 1])
    return first === last ? first : `${first} → ${last}`
  }

  const timeSeriesWarnings = timeSeriesRun ? [
    ...(timeSeriesRun.model.quality.missing_timestamps > 0
      ? [t('modelCenter.timeSeries.warning.missingTimestamps', { count: timeSeriesRun.model.quality.missing_timestamps })]
      : []),
    ...(timeSeriesRun.model.quality.excluded_undated_rows > 0
      ? [t('modelCenter.timeSeries.warning.excludedUndatedRows', { count: timeSeriesRun.model.quality.excluded_undated_rows })]
      : []),
    ...(timeSeriesRun.model.quality.duplicate_timestamps > 0
      ? [t('modelCenter.timeSeries.warning.duplicateTimestamps', { count: timeSeriesRun.model.quality.duplicate_timestamps })]
      : []),
    ...(timeSeriesRun.model.quality.timezone_errors > 0
      ? [t('modelCenter.timeSeries.warning.timezone', { zones: timeSeriesRun.model.quality.timezone_representations.join(', ') })]
      : []),
    ...(timeSeriesRun.model.quality.interval_summary.count > 1
      && timeSeriesRun.model.quality.interval_summary.min_seconds !== timeSeriesRun.model.quality.interval_summary.max_seconds
      ? [t('modelCenter.timeSeries.warning.irregularIntervals')]
      : []),
    ...timeSeriesRun.model.feature_warnings
      .filter((warning) => warning.startsWith('missing_values:'))
      .map((warning) => t('modelCenter.timeSeries.warning.missingValues', { column: warning.split(':')[1] })),
  ] : []

  const timeSplitRows = timeSeriesRun?.validation?.splits.map((split, index) => ({
    key: index,
    fold: index + 1,
    trainRows: split.train_indices.length,
    trainDates: formatSplitRange(split.train_indices),
    validationRows: split.validation_indices.length,
    validationDates: formatSplitRange(split.validation_indices),
    testRows: split.test_indices?.length ?? 0,
    testDates: formatSplitRange(split.test_indices ?? []),
  })) ?? []

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
    {
      title: t('modelCenter.column.equation'), dataIndex: 'equation', key: 'equation', width: 260,
      render: (eq: string) => (
        <Typography.Text code style={{ fontSize: 11 }}>{eq || '—'}</Typography.Text>
      ),
    },
    { title: 'R²', dataIndex: ['metrics', 'r2'], key: 'r2', width: 90, render: (v: number) => v?.toFixed(4) ?? '—' },
    { title: 'RMSE', dataIndex: ['metrics', 'rmse'], key: 'rmse', width: 90, render: (v: number) => v?.toFixed(4) ?? '—' },
    { title: 'AUC', dataIndex: ['metrics', 'auc'], key: 'auc', width: 90, render: (v: number) => v?.toFixed(4) ?? '—' },
    { title: t('modelCenter.column.accuracy'), dataIndex: ['metrics', 'accuracy'], key: 'accuracy', width: 90, render: (v: number) => v?.toFixed(4) ?? '—' },
    { title: t('modelCenter.column.shape_k'), dataIndex: ['metrics', 'shape_k'], key: 'shape_k', width: 90, render: (v: number) => v?.toFixed(4) ?? '—' },
    { title: t('modelCenter.column.aic'), dataIndex: ['metrics', 'aic'], key: 'aic', width: 90, render: (v: number) => v?.toFixed(4) ?? '—' },
    {
      title: t('modelCenter.column.actions'), key: 'actions', width: 240,
      render: (_, record) => {
        const nextStatuses = STATUS_TRANSITIONS[record.status] || []
        return (
          <Space size="small">
            {nextStatuses.map((s) => (
              <Popconfirm key={s} title={t('modelCenter.confirmTransition', { status: s })} onConfirm={() => handleTransition(record.model_id, s)}>
                <Button size="small" loading={transitioning}>{s}</Button>
              </Popconfirm>
            ))}
            <Popconfirm
              title={t('modelCenter.confirmDeleteModel')}
              onConfirm={() => handleDeleteModel(record.model_id)}
              okText={t('common.delete')}
              cancelText={t('common.cancel')}
              okButtonProps={{ danger: true }}
            >
              <Button size="small" danger type="text" loading={deleting}>
                {t('common.delete')}
              </Button>
            </Popconfirm>
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
          {governance.map((warning, i) => <Alert key={i} type="warning" showIcon message={warning.includes('Multicollinearity warning:') ? t('modelCenter.multicollinearityWarning', { warning: warning.replace('Multicollinearity warning: ', '') }) : warning} />)}
          <Space>{recommended.map(name => <Tag key={name}>{name}</Tag>)}</Space>
          <Space direction="vertical" style={{ width: '100%' }}>
            <div>
              <label>{t('modelCenter.mode.label')}</label>
              <Select
                style={{ width: 240, marginLeft: 8 }}
                value={modelingMode}
                onChange={(value) => { setModelingMode(value); invalidateTimeSeriesRun() }}
                options={[
                  { value: 'standard', label: t('modelCenter.mode.standard') },
                  { value: 'time_series', label: t('modelCenter.mode.timeSeries') },
                ]}
              />
            </div>
            {modelingMode === 'standard' && <div>
              <label>{t('modelCenter.modelType.label')}</label>
              <Select
                style={{ width: 240, marginLeft: 8 }}
                value={modelType}
                onChange={setModelType}
                options={MODEL_TYPES.map((m) => ({ value: m.value, label: t(m.labelKey) }))}
              />
              <Typography.Text type="secondary" style={{ marginLeft: 12, fontSize: 12 }}>
                {t(`modelCenter.modelType.desc.${MODEL_DESC_KEY[modelType]}`)}
              </Typography.Text>
            </div>}
            <div>
              <label>{t('modelCenter.target.label')}</label>
              <Select
                style={{ width: 240, marginLeft: 8 }}
                value={target}
                onChange={(value) => { setTarget(value); invalidateTimeSeriesRun() }}
                options={visibleTargetOptions}
                placeholder={t('modelCenter.target.placeholder')}
              />
            </div>
            <div>
              <label>{t('modelCenter.inputs.label')}</label>
              <Select
                mode="multiple"
                style={{ width: 400, marginLeft: 8 }}
                value={selectedInputs}
                onChange={(value) => { setSelectedInputs(value); invalidateTimeSeriesRun() }}
                options={inputOptions}
                placeholder={t('modelCenter.inputs.placeholder')}
              />
            </div>
            {modelingMode === 'standard' && ['random_forest', 'xgboost', 'lightgbm'].includes(modelType) && (
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
            {readiness?.status === 'critical' && <Alert type="error" showIcon message={t('modelCenter.readinessBlocked')} />}
            {modelingMode === 'standard' ? (
              <Button type="primary" loading={fitting} onClick={handleFit} disabled={!datasetId || !target || selectedInputs.length === 0 || readiness?.status === 'critical'}>
                {t('modelCenter.fitButton')}
              </Button>
            ) : (
              <Card title={t('modelCenter.timeSeries.title')} size="small">
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Alert type="info" showIcon message={t('modelCenter.timeSeries.foundationNotice')} />
                  <Space wrap>
                    <label>{t('modelCenter.timeSeries.timeColumn')}</label>
                    <Select
                      style={{ width: 220 }}
                      value={timeColumn}
                      onChange={(value) => { setTimeColumn(value); invalidateTimeSeriesRun() }}
                      options={timeColumnOptions}
                      placeholder={t('modelCenter.timeSeries.selectTimeColumn')}
                    />
                    <label>{t('modelCenter.timeSeries.window')}</label>
                    <Select
                      style={{ width: 140 }}
                      value={timeWindowDays}
                      onChange={(value) => { setTimeWindowDays(value); invalidateTimeSeriesRun() }}
                      options={[7, 30, 60, 90].map((days) => ({ value: days, label: t('modelCenter.timeSeries.days', { count: days }) }))}
                    />
                    <label>{t('modelCenter.timeSeries.validationStrategy')}</label>
                    <Select
                      style={{ width: 190 }}
                      value={timeValidationStrategy}
                      onChange={(value) => { setTimeValidationStrategy(value); invalidateTimeSeriesRun() }}
                      options={[
                        { value: 'holdout', label: t('modelCenter.timeSeries.holdout') },
                        { value: 'walk_forward', label: t('modelCenter.timeSeries.walkForward') },
                      ]}
                    />
                  </Space>
                  <Space wrap>
                    <label>{t('modelCenter.timeSeries.lags')}</label>
                    <Select
                      mode="multiple"
                      style={{ minWidth: 260 }}
                      value={timeLags}
                      onChange={(value) => { setTimeLags(value); invalidateTimeSeriesRun() }}
                      options={[1, 2, 3, 7, 14, 24, 30, 60, 90].map((value) => ({ value, label: String(value) }))}
                    />
                    <label>{t('modelCenter.timeSeries.rollingWindows')}</label>
                    <Select
                      mode="multiple"
                      style={{ minWidth: 260 }}
                      value={rollingWindows}
                      onChange={(value) => { setRollingWindows(value); invalidateTimeSeriesRun() }}
                      options={[2, 3, 7, 14, 24, 30, 60, 90].map((value) => ({ value, label: String(value) }))}
                    />
                  </Space>
                  <Button
                    type="primary"
                    loading={timeSeriesLoading}
                    onClick={handlePrepareTimeSeries}
                    disabled={!timeColumn || !target || selectedInputs.length === 0 || timeLags.length === 0 || rollingWindows.length === 0 || (importResult?.row_count ?? 0) < 7 || readiness?.status === 'critical'}
                  >
                    {timeSeriesLoading ? t('modelCenter.timeSeries.running') : t('modelCenter.timeSeries.run')}
                  </Button>
                  <Button
                    onClick={handleFitTimeSeriesLadder}
                    loading={timeSeriesLadderLoading}
                    disabled={!timeColumn || !target || selectedInputs.length === 0 || readiness?.status === 'critical'}
                  >
                    {timeSeriesLadderLoading ? t('modelCenter.timeSeries.ladderRunning') : t('modelCenter.timeSeries.fitLadder')}
                  </Button>
                  {(importResult?.row_count ?? 0) < 7 && <Alert type="warning" showIcon message={t('modelCenter.timeSeries.warning.tooFewRows')} />}
                  {timeSeriesLadder && <Card title={t('modelCenter.timeSeries.ladderTitle')} size="small">
                    <Table size="small" pagination={false} rowKey="model_type" dataSource={timeSeriesLadder.results} columns={[
                      { title: t('modelCenter.timeSeries.modelType'), dataIndex: 'model_type', key: 'model_type', render: (value: string) => timeSeriesModelLabel(value) },
                      { title: t('modelCenter.timeSeries.status'), dataIndex: 'status', key: 'status', render: (value: string) => <Tag color={value === 'available' ? 'success' : 'warning'}>{value === 'available' ? t('modelCenter.timeSeries.available') : t('modelCenter.timeSeries.unavailable')}</Tag> },
                      { title: 'MAE', key: 'mae', render: (_: unknown, row: TimeSeriesLadderResult['results'][number]) => row.metrics?.mae.toFixed(4) ?? '—' },
                      { title: 'RMSE', key: 'rmse', render: (_: unknown, row: TimeSeriesLadderResult['results'][number]) => row.metrics?.rmse.toFixed(4) ?? '—' },
                      { title: 'R²', key: 'r2', render: (_: unknown, row: TimeSeriesLadderResult['results'][number]) => row.metrics?.r2.toFixed(4) ?? '—' },
                      { title: t('modelCenter.timeSeries.validationStrategy'), key: 'validation', render: (_: unknown, row: TimeSeriesLadderResult['results'][number]) => row.validation?.strategy || '—' },
                      { title: t('modelCenter.timeSeries.trainTestRange'), key: 'range', render: (_: unknown, row: TimeSeriesLadderResult['results'][number]) => row.evaluation?.test_start && row.evaluation?.test_end ? `${row.evaluation.test_start} → ${row.evaluation.test_end}` : row.validation?.train_end && row.validation?.test_start ? `${row.validation.train_end} → ${row.validation.test_start}` : '—' },
                      { title: t('modelCenter.timeSeries.leakageStatus'), key: 'leakage', render: () => timeSeriesLadder.provenance?.leakage_check ? t('modelCenter.timeSeries.leakage.passed') : '—' },
                      { title: t('modelCenter.timeSeries.persistence'), key: 'persisted', render: () => timeSeriesLadder.provenance?.persisted == null ? '—' : timeSeriesLadder.provenance.persisted ? t('modelCenter.timeSeries.persisted') : t('modelCenter.timeSeries.notPersisted') },
                      { title: t('modelCenter.timeSeries.reason'), key: 'error', render: (_: unknown, row: TimeSeriesLadderResult['results'][number]) => timeSeriesReason(row.error, row.reason_code) },
                    ]} />
                    <Alert type="info" showIcon message={t('modelCenter.timeSeries.ladderAdvice')} />
                  </Card>}
                  {timeSeriesRun && (
                    <Space direction="vertical" style={{ width: '100%' }}>
                      {timeSeriesWarnings.length === 0
                        ? <Alert type="success" showIcon message={t('modelCenter.timeSeries.qualityPassed')} />
                        : timeSeriesWarnings.map((warning, index) => <Alert key={index} type="warning" showIcon message={warning} />)}
                      <Descriptions bordered size="small" column={{ xs: 1, sm: 2, md: 3 }} title={t('modelCenter.timeSeries.featureConfiguration')}>
                        <Descriptions.Item label={t('modelCenter.timeSeries.requestedWindow')}>{t('modelCenter.timeSeries.days', { count: timeSeriesRun.windowDays })}</Descriptions.Item>
                        <Descriptions.Item label={t('modelCenter.timeSeries.actualWindow')}>{timeSeriesRun.model.feature_configuration.window_start} → {timeSeriesRun.model.feature_configuration.window_end}</Descriptions.Item>
                        <Descriptions.Item label={t('modelCenter.timeSeries.target')}>{timeSeriesRun.model.feature_configuration.target}</Descriptions.Item>
                        <Descriptions.Item label={t('modelCenter.timeSeries.inputs')}>{timeSeriesRun.model.feature_configuration.inputs.join(', ')}</Descriptions.Item>
                        <Descriptions.Item label={t('modelCenter.timeSeries.frequency')}>{t(`modelCenter.timeSeries.frequencyValue.${timeSeriesRun.model.feature_configuration.frequency}`, { defaultValue: timeSeriesRun.model.feature_configuration.frequency })}</Descriptions.Item>
                        <Descriptions.Item label={t('modelCenter.timeSeries.calendarTimezone')}>{timeSeriesRun.model.feature_configuration.calendar_timezone}</Descriptions.Item>
                        <Descriptions.Item label={t('modelCenter.timeSeries.lags')}>{timeSeriesRun.model.feature_configuration.lags.join(', ')}</Descriptions.Item>
                        <Descriptions.Item label={t('modelCenter.timeSeries.rollingWindows')}>{timeSeriesRun.model.feature_configuration.rolling_windows.join(', ')}</Descriptions.Item>
                        <Descriptions.Item label={t('modelCenter.timeSeries.generatedFeatures')}>{timeSeriesRun.model.feature_names.length}</Descriptions.Item>
                        <Descriptions.Item label={t('modelCenter.timeSeries.usableRows')}>{timeSeriesRun.model.feature_row_count}</Descriptions.Item>
                        <Descriptions.Item label={t('modelCenter.timeSeries.warmupRows')}>{timeSeriesRun.model.dropped_warmup_rows}</Descriptions.Item>
                        <Descriptions.Item label={t('modelCenter.timeSeries.invalidRows')}>{timeSeriesRun.model.dropped_invalid_rows}</Descriptions.Item>
                      </Descriptions>
                      {timeSeriesRun.validationFailed && <Alert type="warning" showIcon message={t('modelCenter.timeSeries.validationUnavailable')} />}
                      {timeSeriesRun.validation && <>
                        <Descriptions bordered size="small" column={{ xs: 1, sm: 2, md: 3 }} title={t('modelCenter.timeSeries.timeOutMetrics')}>
                          <Descriptions.Item label={t('modelCenter.timeSeries.strategy')}>{t(`modelCenter.timeSeries.${timeSeriesRun.validation.strategy === 'holdout' ? 'holdout' : 'walkForward'}`)}</Descriptions.Item>
                          <Descriptions.Item label={t('modelCenter.timeSeries.foldCount')}>{timeSeriesRun.validation.splits.length}</Descriptions.Item>
                          <Descriptions.Item label={t('modelCenter.timeSeries.leakageStatus')}>
                            <Tag color={timeSeriesRun.validation.leakage_check.status === 'passed' ? 'success' : 'warning'}>
                              {t(`modelCenter.timeSeries.leakage.${timeSeriesRun.validation.leakage_check.status === 'passed' ? 'passed' : 'notChecked'}`)}
                            </Tag>
                          </Descriptions.Item>
                        </Descriptions>
                        <Alert type="info" showIcon message={t('modelCenter.timeSeries.metricsUnavailable')} />
                        <Table
                          size="small"
                          pagination={false}
                          dataSource={timeSplitRows}
                          columns={[
                            { title: t('modelCenter.timeSeries.fold'), dataIndex: 'fold', key: 'fold', width: 70 },
                            { title: t('modelCenter.timeSeries.trainRows'), dataIndex: 'trainRows', key: 'trainRows', width: 100 },
                            { title: t('modelCenter.timeSeries.trainDates'), dataIndex: 'trainDates', key: 'trainDates' },
                            { title: t('modelCenter.timeSeries.validationRows'), dataIndex: 'validationRows', key: 'validationRows', width: 110 },
                            { title: t('modelCenter.timeSeries.validationDates'), dataIndex: 'validationDates', key: 'validationDates' },
                            ...(timeSeriesRun.validation.strategy === 'holdout' ? [
                              { title: t('modelCenter.timeSeries.testRows'), dataIndex: 'testRows', key: 'testRows', width: 90 },
                              { title: t('modelCenter.timeSeries.testDates'), dataIndex: 'testDates', key: 'testDates' },
                            ] : []),
                          ]}
                        />
                      </>}
                    </Space>
                  )}
                </Space>
              </Card>
            )}
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
            <Alert
              type={interactionMode === 'notModeled' ? 'warning' : 'info'}
              showIcon
              message={t(`modelCenter.interactionMode.${interactionMode}.title`)}
              description={t(`modelCenter.interactionMode.${interactionMode}.description`)}
            />
            <Button
              type="primary"
              loading={interactionsLoading}
              onClick={handleComputeInteractions}
              disabled={models.length === 0 || !datasetId}
            >
              {interactionsLoading ? t('modelCenter.computing') : t('modelCenter.computeInteractions')}
            </Button>
            {interactions ? (
              <>
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
                            backgroundColor: interactionMode === 'notModeled'
                              ? '#f3f4f6'
                              : `rgba(220, 38, 38, ${intensity * 0.8})`,
                            borderRadius: 2,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            color: interactionMode === 'notModeled' ? '#6b7280' : intensity > 0.3 ? '#fff' : '#000',
                            fontSize: 11,
                          }}
                        >
                          {strength !== 0 ? strength.toFixed(6) : '0.000000'}
                        </div>
                      )
                    },
                  })),
                ]}
                rowKey="factor"
              />
              <Alert type="info" showIcon message={t('modelCenter.interactionSummary')} description={t('modelCenter.interactionAdvice', { pair: '—', strength: '0.000000' })} />
              </>
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
                <Alert type="info" showIcon message={t('modelCenter.shapSummary')} description={t('modelCenter.shapAdvice')} />
              </Space>
            ) : (
              <Alert type="info" showIcon message={t('modelCenter.noInteraction')} />
            )}
          </Space>
        </Card>

        <Card title={t('modelCenter.sensitivityTitle')} size="small">
          <Button type="primary" loading={sensitivityLoading} onClick={handleComputeSensitivity} disabled={!models.length || !datasetId}>
            {sensitivityLoading ? t('modelCenter.computing') : t('modelCenter.computeSensitivity')}
          </Button>
          {sensitivity && <Table size="small" pagination={false} rowKey="input" dataSource={sensitivity.items} columns={[
            { title: t('modelCenter.input'), dataIndex: 'input', key: 'input' },
            { title: t('modelCenter.sensitivity'), dataIndex: 'sensitivity', key: 'sensitivity', render: (v: number) => `${(v * 100).toFixed(1)}%` },
            { title: t('modelCenter.effectSize'), dataIndex: 'effect_size', key: 'effect_size', render: (v: number) => v.toFixed(3) },
          ]} />}
          {sensitivity && <Alert type="info" showIcon message={t('modelCenter.sensitivitySummary')} description={t('modelCenter.sensitivityAdvice')} />}
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
                      message={t(rec.type === 'interaction'
                        ? 'modelCenter.recInteraction'
                        : rec.type === 'transformation'
                        ? (rec.method === 'log' ? 'modelCenter.recTransformationRightSkewed' : 'modelCenter.recTransformationLeftSkewed')
                        : rec.type === 'range_expansion'
                        ? 'modelCenter.recRangeExpansion'
                        : 'modelCenter.recNewFactor',
                        { factorA: (rec as any).factors?.[0] ?? '', factorB: (rec as any).factors?.[1] ?? '', strength: (rec as any).strength?.toFixed(2) ?? '', skewness: (rec as any).skewness?.toFixed(2) ?? '', corr: (rec as any).corr?.toFixed(2) ?? '' }
                      )}
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

        <Card title={t('modelCenter.doeStatisticsTitle')} size="small">
          <Space direction="vertical" style={{ width: '100%' }} size="small">
            <Button
              type="primary"
              loading={doeStatsLoading}
              onClick={handleComputeDOEStatistics}
              disabled={models.length === 0 || !datasetId}
              size="small"
            >
              {doeStatsLoading ? t('modelCenter.computing') : t('modelCenter.computeDOEStatistics')}
            </Button>
            {doeStats ? (
              <Space direction="vertical" style={{ width: '100%' }} size="small">
                {doeStats.anova ? (
                  <>
                    <div>
                      <strong>{t('modelCenter.doeR2')}:</strong>
                      <span style={{ marginLeft: 8 }}>R²={doeStats.r2?.toFixed(4)}</span>
                      <span style={{ marginLeft: 8 }}>AdjR²={doeStats.adj_r2?.toFixed(4)}</span>
                    </div>
                    <div>
                      <strong>{t('modelCenter.doeAnova')}:</strong>
                      <span style={{ marginLeft: 8 }}>F={doeStats.anova.f_stat.toFixed(2)}</span>
                      <span style={{ marginLeft: 8 }}>p={doeStats.anova.p_value.toFixed(6)}</span>
                      <Tag color={doeStats.anova.significant ? 'success' : 'error'} style={{ marginLeft: 8 }}>
                        {doeStats.anova.significant
                          ? `${t('modelCenter.doeSignificant')} (p<0.05)`
                          : `${t('modelCenter.doeNotSignificant')} (p≥0.05)`}
                      </Tag>
                    </div>
                    <div>
                      <strong>{t('modelCenter.doeSigTerms')}:</strong>
                      <span style={{ marginLeft: 8 }}>{doeStats.sig_count}/{doeStats.total_terms} {t('modelCenter.doeTermsSignificant')}</span>
                    </div>
                    <Alert
                      type={doeStats.anova!.significant ? 'success' : 'warning'}
                      message={t(`modelCenter.doeFit${doeStats.fit_level ? doeStats.fit_level.charAt(0).toUpperCase() + doeStats.fit_level.slice(1) : 'Moderate'}`)}
                      showIcon
                      style={{ marginTop: 4 }}
                    />
                    <Table
                      size="small"
                      dataSource={doeStats.coefficients}
                      pagination={false}
                      scroll={{ x: 600 }}
                      columns={[
                        { title: t('modelCenter.doeColumn'), dataIndex: 'name', key: 'name', width: 150 },
                        { title: 'Coef', dataIndex: 'coef', key: 'coef', width: 80, render: (v: number) => v?.toFixed(4) },
                        { title: 'SE', dataIndex: 'std_err', key: 'std_err', width: 80, render: (v: number) => v?.toFixed(6) },
                        { title: 't', dataIndex: 't_stat', key: 't_stat', width: 60, render: (v: number) => v?.toFixed(2) },
                        { title: 'p', dataIndex: 'p_value', key: 'p_value', width: 80, render: (v: number) => v?.toFixed(6) },
                        {
                          title: t('modelCenter.doeCI'), dataIndex: 'ci_lower', key: 'ci', width: 180,
                          render: (_: unknown, row: { ci_lower: number; ci_upper: number }) =>
                            `${row.ci_lower.toFixed(4)} ~ ${row.ci_upper.toFixed(4)}`,
                        },
                        {
                          title: t('modelCenter.doeSig'), dataIndex: 'significant', key: 'significant', width: 70,
                          render: (v: boolean) => v
                            ? <Tag color="success">✓</Tag>
                            : <Tag color="default">—</Tag>,
                        },
                      ]}
                    />
                  </>
                ) : (
                  <Alert type="info" showIcon message={doeStats.note || t('modelCenter.doeNotAvailable')} />
                )}
              </Space>
            ) : (
              <Alert type="info" showIcon message={t('modelCenter.doeNoResult')} />
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
                    {' '}({t(fullValidation.residual_analysis.durbin_watson.interpretation.startsWith('modelCenter.') ? fullValidation.residual_analysis.durbin_watson.interpretation : `modelCenter.${fullValidation.residual_analysis.durbin_watson.interpretation}`)})
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
                            {t(`modelCenter.priority${rec.priority.charAt(0).toUpperCase()}${rec.priority.slice(1)}`)}
                          </Tag>
                          {t((rec.key.includes('.') ? rec.key : `modelCenter.${rec.key}`) as any, {
                            factorA: rec.factors?.[0] ?? '',
                            factorB: rec.factors?.[1] ?? '',
                            strength: rec.strength?.toFixed(2) ?? '',
                            skewness: rec.skewness?.toFixed(2) ?? '',
                            corr: rec.corr?.toFixed(2) ?? '',
                          })}
                        </span>
                      }
                      showIcon
                    />
                  ))}
                  <div style={{ marginTop: 4, fontSize: 12, color: '#6b7280' }}>
                    {fullValidation.experiment_recommendations.summary_key
                      ? t((fullValidation.experiment_recommendations.summary_key.includes('.') ? fullValidation.experiment_recommendations.summary_key : `modelCenter.${fullValidation.experiment_recommendations.summary_key}`) as any)
                      : fullValidation.experiment_recommendations.summary}
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
