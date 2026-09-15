import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, Table, Select, Button, Space, Alert, Tag, message, Popconfirm, Switch, Input, InputNumber, Typography, Descriptions } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { ExperimentOutlined, SwapOutlined } from '@ant-design/icons'
import Plot from '../../components/PlotChart'
import { useDataPipelineStore } from '../../stores/dataPipelineStore'
import { useModelStore } from '../../stores/modelStore'
import { useAssistantContextStore } from '../../stores/assistantContextStore'
import { buildModelCenterContext } from '../../lib/assistantData'
import type { ModelFitDTO, ModelType, ModelStatus, InteractionResult, SHAPResult, ExtrapolationResult, ValidationResult, FullValidationResult, ReadinessResult, SensitivityEffectResult, TimeSeriesModelResult, TimeSeriesValidationResult, TimeSeriesLadderResult, TimeSeriesHybridResult, TimeSeriesWindowRecommendation, TimeSeriesValidationGateModelType, TimeSeriesValidationGateResult, TimeSeriesExplanationResult, TimeSeriesSequenceSimulationResult } from '../../lib/engine'
import { checkModelApplicability, recommendModels, computeInteractions, computeSHAP, checkExtrapolation, analyzeValidation, runFullValidation, computeDOEStatistics, computeSensitivity, runReadiness, prepareTimeSeriesModel, validateTimeSeries, validateTimeSeriesGate, fitTimeSeriesLadder, fitTimeSeriesHybrid, recommendTimeSeriesWindows, explainTimeSeriesModel, runTimeSeriesSequenceSimulation, getModelInfo, type DoeStatisticsResult, type ModelInfo } from '../../lib/engine'

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

const TIME_SERIES_GATE_MODEL_TYPES: TimeSeriesValidationGateModelType[] = [
  'naive',
  'seasonal_naive',
  'dynamic_regression',
  'time_feature_random_forest',
  'transformer',
  'temporal_fusion_transformer',
]

const isTimeSeriesGateModel = (modelType: string): modelType is TimeSeriesValidationGateModelType =>
  TIME_SERIES_GATE_MODEL_TYPES.includes(modelType as TimeSeriesValidationGateModelType)

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
  const [timeEvaluationProtocol, setTimeEvaluationProtocol] = useState<'fixed_horizon_forecast' | 'observed_feature_holdout'>('fixed_horizon_forecast')
  const [timeSeriesLoading, setTimeSeriesLoading] = useState(false)
  const [timeSeriesLadder, setTimeSeriesLadder] = useState<TimeSeriesLadderResult | null>(null)
  const [timeSeriesLadderLoading, setTimeSeriesLadderLoading] = useState(false)
  const [timeSeriesPersisting, setTimeSeriesPersisting] = useState(false)
  const [timeSeriesHybrid, setTimeSeriesHybrid] = useState<TimeSeriesHybridResult | null>(null)
  const [timeSeriesHybridLoading, setTimeSeriesHybridLoading] = useState(false)
  const [selectedTimeSeriesModels, setSelectedTimeSeriesModels] = useState<string[]>([])
  const [timeWindowRecommendation, setTimeWindowRecommendation] = useState<TimeSeriesWindowRecommendation | null>(null)
  const [timeWindowRecommendationLoading, setTimeWindowRecommendationLoading] = useState(false)
  const [timeSeriesGateResults, setTimeSeriesGateResults] = useState<Partial<Record<TimeSeriesValidationGateModelType, TimeSeriesValidationGateResult>>>({})
  const [activeTimeSeriesGateModel, setActiveTimeSeriesGateModel] = useState<TimeSeriesValidationGateModelType | null>(null)
  const [timeSeriesGateLoading, setTimeSeriesGateLoading] = useState<TimeSeriesValidationGateModelType | null>(null)
  const timeSeriesRequestId = useRef(0)
  const timeSeriesLadderRequestId = useRef(0)
  const timeSeriesGateRequestId = useRef(0)
  const timeSeriesExplanationRequestId = useRef(0)
  const [timeSeriesRun, setTimeSeriesRun] = useState<{
    model: TimeSeriesModelResult
    validation: TimeSeriesValidationResult | null
    windowDays: number
    validationFailed: boolean
  } | null>(null)
  const [selectedModelInfo, setSelectedModelInfo] = useState<ModelInfo | null>(null)
  const [selectedModelInfoLoading, setSelectedModelInfoLoading] = useState(false)
  const [timeSeriesExplanation, setTimeSeriesExplanation] = useState<TimeSeriesExplanationResult | null>(null)
  const [timeSeriesExplanationLoading, setTimeSeriesExplanationLoading] = useState(false)
  const [sequenceSimulationModelId, setSequenceSimulationModelId] = useState<string | undefined>()
  const [sequenceSimulationHorizon, setSequenceSimulationHorizon] = useState(1)
  const [sequenceSimulationMode, setSequenceSimulationMode] = useState<'sequence_aware' | 'sequence_stochastic'>('sequence_aware')
  const [sequenceSimulationCount, setSequenceSimulationCount] = useState(100)
  const [sequenceSimulationSeed, setSequenceSimulationSeed] = useState(42)
  const [sequenceSimulationHistory, setSequenceSimulationHistory] = useState('[]')
  const [sequenceSimulationScenarios, setSequenceSimulationScenarios] = useState('[]')
  const [sequenceSimulationResult, setSequenceSimulationResult] = useState<TimeSeriesSequenceSimulationResult | null>(null)
  const [sequenceSimulationLoading, setSequenceSimulationLoading] = useState(false)

  useEffect(() => {
    setContext(
      'modelCenter',
      buildModelCenterContext({ interactions, shapResult, extrapResult, validationResult, fullValidation, doeStats, sensitivity, governanceWarnings: governance, recommendedInputs: recommended, readiness: readiness ?? undefined }),
    )
  }, [interactions, shapResult, extrapResult, validationResult, fullValidation, doeStats, sensitivity, governance, recommended, readiness, setContext])

  const datasetId = importResult?.dataset_id
  const latestModel = models[models.length - 1]
  const timeSeriesActive = modelingMode === 'time_series' || Boolean(latestModel?.model_type?.startsWith('time_series_'))
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

  useEffect(() => {
    let active = true
    if (!selectedModelId) {
      setSelectedModelInfo(null)
      return
    }
    setSelectedModelInfoLoading(true)
    getModelInfo({ model_id: selectedModelId })
      .then((info) => { if (active) setSelectedModelInfo(info) })
      .catch(() => { if (active) setSelectedModelInfo(null) })
      .finally(() => { if (active) setSelectedModelInfoLoading(false) })
    return () => { active = false }
  }, [selectedModelId])

  useEffect(() => {
    timeSeriesExplanationRequestId.current += 1
    setTimeSeriesExplanation(null)
    setTimeSeriesExplanationLoading(false)
  }, [datasetId, selectedModelId])

  useEffect(() => {
    setSequenceSimulationResult(null)
    if (selectedModelId && selectedModelInfo?.model_type === 'time_series_transformer') {
      setSequenceSimulationModelId(selectedModelId)
    }
  }, [datasetId, selectedModelId, selectedModelInfo?.model_type])

  const invalidateTimeSeriesRun = () => {
    timeSeriesRequestId.current += 1
    timeSeriesLadderRequestId.current += 1
    timeSeriesGateRequestId.current += 1
    setTimeSeriesRun(null)
    setTimeSeriesLadder(null)
    setTimeSeriesLoading(false)
    setTimeSeriesLadderLoading(false)
    setTimeSeriesHybrid(null)
    setTimeSeriesHybridLoading(false)
    setTimeSeriesGateResults({})
    setActiveTimeSeriesGateModel(null)
    setTimeSeriesGateLoading(null)
  }

  const handleFitTimeSeriesHybrid = async () => {
    if (!datasetId || !timeColumn || !target || selectedInputs.length === 0) return
    setTimeSeriesHybridLoading(true)
    try {
      const result = await fitTimeSeriesHybrid({ dataset_id: datasetId, time_column: timeColumn, target, inputs: selectedInputs, lags: timeLags, rolling_windows: rollingWindows, modeling_timezone: 'UTC', window_days: timeWindowDays, evaluation_protocol: timeEvaluationProtocol })
      setTimeSeriesHybrid(result)
      messageApi.success(t('modelCenter.timeSeries.hybridSuccess'))
    } catch (err) {
      messageApi.error(`${t('modelCenter.timeSeries.hybridError')}: ${err instanceof Error ? err.message : String(err)}`)
    } finally { setTimeSeriesHybridLoading(false) }
  }

  const handleRecommendTimeWindows = async () => {
    if (!datasetId || !timeColumn) return
    setTimeWindowRecommendationLoading(true)
    try {
      setTimeWindowRecommendation(await recommendTimeSeriesWindows({ dataset_id: datasetId, time_column: timeColumn, modeling_timezone: 'UTC' }))
    } catch (err) {
      messageApi.error(`${t('modelCenter.timeSeries.windowRecommendationError')}: ${err instanceof Error ? err.message : String(err)}`)
    } finally { setTimeWindowRecommendationLoading(false) }
  }

  const handleFitTimeSeriesLadder = async () => {
    if (!datasetId || !timeColumn || !target || selectedInputs.length === 0) return
    const requestId = timeSeriesLadderRequestId.current + 1
    timeSeriesLadderRequestId.current = requestId
    timeSeriesGateRequestId.current += 1
    setTimeSeriesGateResults({})
    setActiveTimeSeriesGateModel(null)
    setTimeSeriesGateLoading(null)
    setTimeSeriesLadderLoading(true)
    try {
      const result = await fitTimeSeriesLadder({ dataset_id: datasetId, time_column: timeColumn, target, inputs: selectedInputs, lags: timeLags, rolling_windows: rollingWindows, modeling_timezone: 'UTC', window_days: timeWindowDays, evaluation_protocol: timeEvaluationProtocol })
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

  const handleValidateTimeSeriesGate = async (modelType: string) => {
    if (!datasetId || !timeColumn || !target || !isTimeSeriesGateModel(modelType)) return
    const requestId = timeSeriesGateRequestId.current + 1
    timeSeriesGateRequestId.current = requestId
    const foldCount = 3
    const horizon = Math.max(1, Math.floor((timeSeriesLadder?.validation.test_rows ?? foldCount) / foldCount))
    setTimeSeriesGateLoading(modelType)
    try {
      const result = await validateTimeSeriesGate({
        dataset_id: datasetId,
        time_column: timeColumn,
        target,
        inputs: selectedInputs,
        model_type: modelType,
        evaluation_protocol: timeEvaluationProtocol,
        fold_count: foldCount,
        horizon,
        lags: timeLags,
        rolling_windows: rollingWindows,
        modeling_timezone: 'UTC',
      })
      if (requestId !== timeSeriesGateRequestId.current) return
      setTimeSeriesGateResults((current) => ({ ...current, [modelType]: result }))
      setActiveTimeSeriesGateModel(modelType)
      if (result.gate_status === 'approved') {
        messageApi.success(t('modelCenter.timeSeries.gateApproved'))
      } else {
        const reasons = result.gate_reasons.map((reason) => timeSeriesGateReason(reason)).join('；')
        messageApi.warning(`${t(`modelCenter.timeSeries.gateStatus.${result.gate_status}`)}${reasons ? `：${reasons}` : ''}`)
      }
    } catch (err) {
      if (requestId !== timeSeriesGateRequestId.current) return
      messageApi.error(`${t('modelCenter.timeSeries.gateError')}: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      if (requestId === timeSeriesGateRequestId.current) setTimeSeriesGateLoading(null)
    }
  }

  const handlePersistTimeSeriesModels = async () => {
    const gatesApproved = selectedTimeSeriesModels.length > 0 && selectedTimeSeriesModels.every((model) =>
      isTimeSeriesGateModel(model) && timeSeriesGateResults[model]?.gate_status === 'approved')
    if (!datasetId || !timeColumn || !target || selectedInputs.length === 0 || !gatesApproved) return
    setTimeSeriesPersisting(true)
    try {
      const validationGateEvidence = Object.fromEntries(selectedTimeSeriesModels
        .filter(isTimeSeriesGateModel)
        .map((model) => [model, timeSeriesGateResults[model]!]))
      const result = await fitTimeSeriesLadder({ dataset_id: datasetId, time_column: timeColumn, target, inputs: selectedInputs, lags: timeLags, rolling_windows: rollingWindows, modeling_timezone: 'UTC', window_days: timeWindowDays, evaluation_protocol: timeEvaluationProtocol, persist_models: true, persist_model_types: selectedTimeSeriesModels, validation_gate_evidence: validationGateEvidence })
      setTimeSeriesLadder(result)
      setSelectedTimeSeriesModels([])
      messageApi.success(t('modelCenter.timeSeries.persistenceSuccess'))
      loadModels()
    } catch (err) {
      messageApi.error(`${t('modelCenter.timeSeries.persistenceError')}: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setTimeSeriesPersisting(false)
    }
  }

  const handleExplainTimeSeriesModel = async () => {
    if (!datasetId || !selectedModelId || !selectedModelInfo?.model_type.startsWith('time_series_')) return
    const requestId = timeSeriesExplanationRequestId.current + 1
    timeSeriesExplanationRequestId.current = requestId
    setTimeSeriesExplanationLoading(true)
    try {
      const result = await explainTimeSeriesModel({ model_id: selectedModelId, dataset_id: datasetId })
      if (requestId !== timeSeriesExplanationRequestId.current) return
      setTimeSeriesExplanation(result)
      messageApi.success(t('modelCenter.timeSeries.explanation.success'))
    } catch (err) {
      if (requestId !== timeSeriesExplanationRequestId.current) return
      setTimeSeriesExplanation(null)
      messageApi.error(`${t('modelCenter.timeSeries.explanation.error')}: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      if (requestId === timeSeriesExplanationRequestId.current) setTimeSeriesExplanationLoading(false)
    }
  }

  const handleRunSequenceSimulation = async () => {
    if (!datasetId || !sequenceSimulationModelId) return
    let historyRows: Array<Record<string, unknown>>
    let inputScenarios: Array<Record<string, unknown>>
    try {
      const parsedHistory: unknown = JSON.parse(sequenceSimulationHistory)
      const parsedScenarios: unknown = JSON.parse(sequenceSimulationScenarios)
      if (!Array.isArray(parsedHistory) || !Array.isArray(parsedScenarios)) throw new Error(t('modelCenter.timeSeries.sequenceSimulation.invalidRows'))
      historyRows = parsedHistory as Array<Record<string, unknown>>
      inputScenarios = parsedScenarios as Array<Record<string, unknown>>
    } catch (err) {
      messageApi.error(err instanceof Error ? err.message : t('modelCenter.timeSeries.sequenceSimulation.invalidRows'))
      return
    }
    setSequenceSimulationLoading(true)
    setSequenceSimulationResult(null)
    try {
      const result = await runTimeSeriesSequenceSimulation({
        model_id: sequenceSimulationModelId,
        dataset_id: datasetId,
        horizon: sequenceSimulationHorizon,
        history_rows: historyRows,
        input_scenarios: inputScenarios,
        simulation_mode: sequenceSimulationMode,
        ...(sequenceSimulationMode === 'sequence_stochastic'
          ? { n_simulations: sequenceSimulationCount, seed: sequenceSimulationSeed }
          : {}),
      })
      setSequenceSimulationResult(result)
      if (result.status === 'dry_run') messageApi.success(t('modelCenter.timeSeries.sequenceSimulation.success'))
    } catch (err) {
      messageApi.error(`${t('modelCenter.timeSeries.sequenceSimulation.error')}: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setSequenceSimulationLoading(false)
    }
  }

  const timeSeriesModelLabel = (name: string) => t(`modelCenter.timeSeries.models.${name}`, { defaultValue: name })
  const timeSeriesReason = (reason?: string | null, code?: string | null) => {
    if (!reason && !code) return '—'
    if (code) return t(`modelCenter.timeSeries.reasons.${code}`, { defaultValue: t('modelCenter.timeSeries.reasons.unknown') })
    return t('modelCenter.timeSeries.reasons.unknown')
  }
  const timeSeriesGateStatusColor = (status: TimeSeriesValidationGateResult['gate_status']) =>
    status === 'approved' ? 'success' : status === 'needs_review' ? 'warning' : 'error'
  const timeSeriesGateReason = (reason: string) =>
    t(`modelCenter.timeSeries.gateReasons.${reason}`, { defaultValue: reason })
  const timeSeriesProvenanceKind = (kind: string) =>
    t(`modelCenter.timeSeries.explanation.provenanceKinds.${kind}`, { defaultValue: kind })
  const timeSeriesAvailability = (availability: string) =>
    t(`modelCenter.timeSeries.explanation.availability.${availability}`, { defaultValue: availability })
  const timeSeriesProtocol = (protocol: string) => protocol === 'fixed_horizon_forecast'
    ? t('modelCenter.timeSeries.fixedHorizon')
    : protocol === 'observed_feature_holdout'
      ? t('modelCenter.timeSeries.observedFeatureHoldout')
      : protocol
  const formatCoverage = (coverage: number | null) => coverage == null ? t('modelCenter.timeSeries.unavailable') : `${(coverage * 100).toFixed(1)}%`
  const ladderProtocols = timeSeriesLadder?.results
    .filter((row) => row.status === 'available' && row.evaluation?.protocol !== 'not_supported' && row.evaluation?.protocol !== 'not_applicable')
    .map((row) => row.evaluation?.protocol).filter(Boolean) ?? []
  const hasMixedLadderProtocols = new Set(ladderProtocols).size > 1
  const unavailableLadderCount = timeSeriesLadder?.results.filter((row) => row.status !== 'available').length ?? 0
  const activeTimeSeriesGate = activeTimeSeriesGateModel ? timeSeriesGateResults[activeTimeSeriesGateModel] : undefined
  const timeSeriesPersistenceAllowed = selectedTimeSeriesModels.length > 0 && selectedTimeSeriesModels.every((model) =>
    isTimeSeriesGateModel(model) && timeSeriesGateResults[model]?.gate_status === 'approved')
  const ladderRows = timeSeriesLadder
    ? [...timeSeriesLadder.results].sort((a, b) => {
        const protocolA = a.evaluation?.protocol ?? ''
        const protocolB = b.evaluation?.protocol ?? ''
        if (protocolA !== protocolB) return protocolA.localeCompare(protocolB)
        const metricA = a.metrics?.rmse
        const metricB = b.metrics?.rmse
        if (metricA == null && metricB == null) return 0
        if (metricA == null) return 1
        if (metricB == null) return -1
        return metricA - metricB
      })
    : []
  const selectedTimeSeriesLadderRow = timeSeriesLadder?.results.find((row) => row.model_id === selectedModelId)
  const timeSeriesBackendDetails = (row: TimeSeriesLadderResult['results'][number]) => {
    const backend = row.backend ?? row.capability?.backend
    if (!backend) return '—'
    const framework = row.framework_version ? ` ${row.framework_version}` : ''
    const device = row.device ? `/${row.device}` : ''
    const dependency = row.capability?.dependency
    return dependency
      ? `${backend}${device}${framework} · ${dependency.name}: ${t(dependency.available ? 'modelCenter.timeSeries.dependencyAvailable' : 'modelCenter.timeSeries.dependencyMissing')}`
      : `${backend}${device}${framework}`
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
            {nextStatuses.map((s) => {
              const ladderModelType = record.model_type.replace(/^time_series_/, '')
              const approvalBlocked = s === 'approved'
                && record.model_type.startsWith('time_series_')
                && (!isTimeSeriesGateModel(ladderModelType) || timeSeriesGateResults[ladderModelType]?.gate_status !== 'approved')
              return (
                <Popconfirm key={s} title={t('modelCenter.confirmTransition', { status: s })} onConfirm={() => handleTransition(record.model_id, s)} disabled={approvalBlocked}>
                  <Button size="small" loading={transitioning} disabled={approvalBlocked} title={approvalBlocked ? t('modelCenter.timeSeries.approvalGateRequired') : undefined}>{s}</Button>
                </Popconfirm>
              )
            })}
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
                    <label>{t('modelCenter.timeSeries.evaluationProtocol')}</label>
                    <Select
                      style={{ width: 250 }}
                      value={timeEvaluationProtocol}
                      onChange={(value) => { setTimeEvaluationProtocol(value); invalidateTimeSeriesRun() }}
                      options={[
                        { value: 'fixed_horizon_forecast', label: t('modelCenter.timeSeries.fixedHorizon') },
                        { value: 'observed_feature_holdout', label: t('modelCenter.timeSeries.observedFeatureHoldout') },
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
                  <Button loading={timeWindowRecommendationLoading} onClick={handleRecommendTimeWindows} disabled={!timeColumn || !datasetId}>
                    {t('modelCenter.timeSeries.checkWindowCoverage')}
                  </Button>
                  {timeWindowRecommendation && <Card size="small" title={t('modelCenter.timeSeries.windowCoverageTitle')}>
                    <Alert type="info" showIcon message={t('modelCenter.timeSeries.windowCoverageSummary', { days: timeWindowRecommendation.observed_span_days.toFixed(1), rows: timeWindowRecommendation.valid_timestamp_rows })} />
                    <Table size="small" pagination={false} rowKey="window_days" dataSource={timeWindowRecommendation.windows} columns={[
                      { title: t('modelCenter.timeSeries.window'), dataIndex: 'window_days', key: 'window_days', render: (v: number) => t('modelCenter.timeSeries.days', { count: v }) },
                      { title: t('modelCenter.timeSeries.status'), dataIndex: 'status', key: 'status', render: (v: string) => <Tag color={v === 'available' ? 'success' : 'warning'}>{v === 'available' ? t('modelCenter.timeSeries.windowAvailable') : t('modelCenter.timeSeries.windowSkipped')}</Tag> },
                      { title: t('modelCenter.timeSeries.reason'), dataIndex: 'reason', key: 'reason', render: (v: string | null) => v || '—' },
                    ]} />
                    <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>{t('modelCenter.timeSeries.windowCoverageAdvice')}</Typography.Paragraph>
                  </Card>}
                  <Button
                    type="primary"
                    loading={timeSeriesLoading}
                    onClick={handlePrepareTimeSeries}
                    disabled={!timeColumn || !target || selectedInputs.length === 0 || timeLags.length === 0 || rollingWindows.length === 0 || (importResult?.row_count ?? 0) < 7 || readiness?.status === 'critical'}
                  >
                    {timeSeriesLoading ? t('modelCenter.timeSeries.running') : t('modelCenter.timeSeries.run')}
                  </Button>
                  <Button onClick={handleFitTimeSeriesHybrid} loading={timeSeriesHybridLoading} disabled={!timeColumn || !target || selectedInputs.length === 0 || readiness?.status === 'critical'}>
                    {t('modelCenter.timeSeries.fitHybrid')}
                  </Button>
                  {timeSeriesHybrid && <Card title={t('modelCenter.timeSeries.hybridTitle')} size="small">
                    <Alert type="info" showIcon message={t(`modelCenter.timeSeries.${timeSeriesHybrid.evaluation_protocol === 'fixed_horizon_forecast' ? 'formalProtocolAdvice' : 'exploratoryProtocolAdvice'}`)} />
                    <Descriptions bordered size="small" column={{ xs: 1, sm: 2, md: 3 }}>
                      <Descriptions.Item label={t('modelCenter.timeSeries.hybridBaseline')}>{timeSeriesModelLabel(timeSeriesHybrid.baseline.model_type)}</Descriptions.Item>
                      <Descriptions.Item label={t('modelCenter.timeSeries.hybridResidual')}>{timeSeriesModelLabel(timeSeriesHybrid.residual_model.model_type)}</Descriptions.Item>
                      <Descriptions.Item label={t('modelCenter.timeSeries.hybridFeatures')}>{timeSeriesHybrid.residual_model.features.length}</Descriptions.Item>
                      <Descriptions.Item label={t('modelCenter.timeSeries.trainRows')}>{timeSeriesHybrid.validation.train_rows}</Descriptions.Item>
                      <Descriptions.Item label={t('modelCenter.timeSeries.testRows')}>{timeSeriesHybrid.validation.test_rows}</Descriptions.Item>
                      <Descriptions.Item label={t('modelCenter.timeSeries.observedTarget')}>{timeSeriesHybrid.uses_observed_target ? t('modelCenter.timeSeries.yes') : t('modelCenter.timeSeries.no')}</Descriptions.Item>
                      <Descriptions.Item label={t('modelCenter.timeSeries.leakageStatus')}><Tag color="success">{t('modelCenter.timeSeries.leakage.passed')}</Tag></Descriptions.Item>
                    </Descriptions>
                    <Table size="small" pagination={false} rowKey="model" dataSource={[
                      { model: t('modelCenter.timeSeries.hybridBaseline'), ...timeSeriesHybrid.baseline.metrics },
                      { model: t('modelCenter.timeSeries.hybridOutput'), ...timeSeriesHybrid.hybrid.metrics },
                    ]} columns={[{ title: t('modelCenter.timeSeries.modelType'), dataIndex: 'model', key: 'model' }, { title: 'MAE', dataIndex: 'mae', key: 'mae', render: (v: number) => v.toFixed(4) }, { title: 'RMSE', dataIndex: 'rmse', key: 'rmse', render: (v: number) => v.toFixed(4) }, { title: 'R²', dataIndex: 'r2', key: 'r2', render: (v: number) => v.toFixed(4) }]} />
                    <Alert type={timeSeriesHybrid.improvement.rmse > 0 ? 'success' : 'warning'} showIcon message={t('modelCenter.timeSeries.hybridImprovement', { mae: timeSeriesHybrid.improvement.mae.toFixed(4), rmse: timeSeriesHybrid.improvement.rmse.toFixed(4) })} />
                  </Card>}
                  <Button
                    onClick={handleFitTimeSeriesLadder}
                    loading={timeSeriesLadderLoading}
                    disabled={!timeColumn || !target || selectedInputs.length === 0 || readiness?.status === 'critical'}
                  >
                    {timeSeriesLadderLoading ? t('modelCenter.timeSeries.ladderRunning') : t('modelCenter.timeSeries.fitLadder')}
                  </Button>
                  {(importResult?.row_count ?? 0) < 7 && <Alert type="warning" showIcon message={t('modelCenter.timeSeries.warning.tooFewRows')} />}
                  {timeSeriesLadder && <Card title={t('modelCenter.timeSeries.ladderTitle')} size="small">
                    {hasMixedLadderProtocols && <Alert type="warning" showIcon message={t('modelCenter.timeSeries.mixedProtocols')} />}
                    <Alert type="info" showIcon message={timeEvaluationProtocol === 'fixed_horizon_forecast' ? t('modelCenter.timeSeries.formalProtocolAdvice') : t('modelCenter.timeSeries.exploratoryProtocolAdvice')} />
                    <Space style={{ marginBottom: 8 }}>
                      <Popconfirm
                        title={t('modelCenter.timeSeries.persistenceConfirm')}
                        onConfirm={handlePersistTimeSeriesModels}
                        okText={t('common.confirm')}
                        cancelText={t('common.cancel')}
                        disabled={!timeSeriesPersistenceAllowed}
                      >
                        <Button type="primary" loading={timeSeriesPersisting} disabled={!timeSeriesPersistenceAllowed} title={!timeSeriesPersistenceAllowed ? t('modelCenter.timeSeries.persistenceGateRequired') : undefined}>
                          {t('modelCenter.timeSeries.persistSelected')} ({selectedTimeSeriesModels.length})
                        </Button>
                      </Popconfirm>
                    </Space>
                    {selectedTimeSeriesModels.length > 0 && !timeSeriesPersistenceAllowed && (
                      <Alert type="warning" showIcon message={t('modelCenter.timeSeries.persistenceGateRequired')} />
                    )}
                    <Table size="small" pagination={false} rowKey="model_type" dataSource={ladderRows} rowSelection={{ selectedRowKeys: selectedTimeSeriesModels, onChange: (keys) => setSelectedTimeSeriesModels(keys as string[]), getCheckboxProps: (row) => ({ disabled: row.status !== 'available' || row.persisted === true }) }} columns={[
                      { title: t('modelCenter.timeSeries.modelType'), dataIndex: 'model_type', key: 'model_type', render: (value: string) => timeSeriesModelLabel(value) },
                      { title: t('modelCenter.timeSeries.status'), dataIndex: 'status', key: 'status', render: (value: string) => <Tag color={value === 'available' ? 'success' : 'warning'}>{value === 'available' ? t('modelCenter.timeSeries.available') : value === 'not_supported' ? t('modelCenter.timeSeries.notSupported') : value === 'not_applicable' ? t('modelCenter.timeSeries.notApplicable') : t('modelCenter.timeSeries.unavailable')}</Tag> },
                      { title: t('modelCenter.timeSeries.backend'), key: 'backend', render: (_: unknown, row: TimeSeriesLadderResult['results'][number]) => timeSeriesBackendDetails(row) },
                      { title: 'MAE', key: 'mae', render: (_: unknown, row: TimeSeriesLadderResult['results'][number]) => row.metrics?.mae.toFixed(4) ?? '—' },
                      { title: 'RMSE', key: 'rmse', render: (_: unknown, row: TimeSeriesLadderResult['results'][number]) => row.metrics?.rmse.toFixed(4) ?? '—' },
                      { title: 'R²', key: 'r2', render: (_: unknown, row: TimeSeriesLadderResult['results'][number]) => row.metrics?.r2.toFixed(4) ?? '—' },
                      { title: t('modelCenter.timeSeries.predictionIntervalCoverage'), key: 'intervalCoverage', render: (_: unknown, row: TimeSeriesLadderResult['results'][number]) => row.uncertainty?.calibration?.coverage_ratio == null ? '—' : `${formatCoverage(row.uncertainty.calibration.coverage_ratio)} (${row.uncertainty.calibration.covered_rows ?? 0}/${row.uncertainty.calibration.evaluated_rows ?? 0})` },
                      { title: t('modelCenter.timeSeries.validationStrategy'), key: 'validation', render: (_: unknown, row: TimeSeriesLadderResult['results'][number]) => row.validation?.strategy || '—' },
                      { title: t('modelCenter.timeSeries.protocol'), key: 'protocol', render: (_: unknown, row: TimeSeriesLadderResult['results'][number]) => row.evaluation?.protocol || '—' },
                      { title: t('modelCenter.timeSeries.trainRows'), key: 'trainRows', render: (_: unknown, row: TimeSeriesLadderResult['results'][number]) => row.validation?.train_rows ?? '—' },
                      { title: t('modelCenter.timeSeries.testRows'), key: 'testRows', render: (_: unknown, row: TimeSeriesLadderResult['results'][number]) => row.evaluation?.rows ?? row.validation?.test_rows ?? '—' },
                      { title: t('modelCenter.timeSeries.trainTestRange'), key: 'range', render: (_: unknown, row: TimeSeriesLadderResult['results'][number]) => row.evaluation?.train_start && row.evaluation?.test_end ? `${row.evaluation.train_start} → ${row.evaluation.test_end}` : row.validation?.train_end && row.validation?.test_start ? `${row.validation.train_end} → ${row.validation.test_start}` : '—' },
                      { title: t('modelCenter.timeSeries.observedTarget'), key: 'observedTarget', render: (_: unknown, row: TimeSeriesLadderResult['results'][number]) => row.evaluation?.uses_observed_target == null ? '—' : row.evaluation.uses_observed_target ? t('modelCenter.timeSeries.yes') : t('modelCenter.timeSeries.no') },
                      { title: t('modelCenter.timeSeries.leakageStatus'), key: 'leakage', render: () => timeSeriesLadder.provenance?.leakage_check ? t('modelCenter.timeSeries.leakage.passed') : '—' },
                      { title: t('modelCenter.timeSeries.persistence'), key: 'persisted', render: (_: unknown, row: TimeSeriesLadderResult['results'][number]) => row.persisted ? `${t('modelCenter.timeSeries.persisted')} (${row.model_id ?? '—'})` : t('modelCenter.timeSeries.notPersisted') },
                      { title: t('modelCenter.timeSeries.reason'), key: 'error', render: (_: unknown, row: TimeSeriesLadderResult['results'][number]) => row.status !== 'available' ? (row.reason_code === 'adapter_error' && row.error ? row.error : timeSeriesReason(row.error, row.reason_code)) : row.persistence_blocked_reason ?? '—' },
                      { title: t('modelCenter.timeSeries.validationGate'), key: 'validationGate', render: (_: unknown, row: TimeSeriesLadderResult['results'][number]) => {
                        const gateModelType = row.model_type
                        const supported = isTimeSeriesGateModel(gateModelType)
                        const gate = supported ? timeSeriesGateResults[gateModelType] : undefined
                        return <Space size="small">
                          {gate
                            ? <Tag color={timeSeriesGateStatusColor(gate.gate_status)}>{t(`modelCenter.timeSeries.gateStatus.${gate.gate_status}`)}</Tag>
                            : <Tag>{supported ? t('modelCenter.timeSeries.gateStatus.notRun') : t('modelCenter.timeSeries.notSupported')}</Tag>}
                          <Button size="small" onClick={() => handleValidateTimeSeriesGate(row.model_type)} loading={timeSeriesGateLoading === row.model_type} disabled={row.status !== 'available' || !supported || timeSeriesGateLoading !== null}>
                            {t('modelCenter.timeSeries.runValidationGate')}
                          </Button>
                        </Space>
                      } },
                    ]} />
                    {activeTimeSeriesGateModel && activeTimeSeriesGate && (
                      <Card size="small" title={t('modelCenter.timeSeries.gateEvidenceTitle', { model: timeSeriesModelLabel(activeTimeSeriesGateModel) })}>
                        <Space direction="vertical" style={{ width: '100%' }}>
                          <Alert
                            type={activeTimeSeriesGate.gate_status === 'approved' ? 'success' : activeTimeSeriesGate.gate_status === 'needs_review' ? 'warning' : 'error'}
                            showIcon
                            message={t(`modelCenter.timeSeries.gateStatus.${activeTimeSeriesGate.gate_status}`)}
                          />
                          {activeTimeSeriesGate.gate_reasons.map((reason) => (
                            <Alert key={reason} type="warning" showIcon message={timeSeriesGateReason(reason)} />
                          ))}
                          <Descriptions bordered size="small" column={{ xs: 1, sm: 2, md: 3 }}>
                            <Descriptions.Item label={t('modelCenter.timeSeries.protocol')}>
                              {t(`modelCenter.timeSeries.${activeTimeSeriesGate.leakage_status.evaluation_protocol === 'fixed_horizon_forecast' ? 'fixedHorizon' : 'observedFeatureHoldout'}`)}
                            </Descriptions.Item>
                            <Descriptions.Item label={t('modelCenter.timeSeries.foldCount')}>{activeTimeSeriesGate.folds.length}</Descriptions.Item>
                            <Descriptions.Item label={t('modelCenter.timeSeries.leakageStatus')}>
                              <Tag color={activeTimeSeriesGate.leakage_status.status === 'passed' ? 'success' : 'warning'}>
                                {t(`modelCenter.timeSeries.leakage.${activeTimeSeriesGate.leakage_status.status === 'passed' ? 'passed' : 'needsReview'}`)}
                              </Tag>
                            </Descriptions.Item>
                            <Descriptions.Item label={t('modelCenter.timeSeries.predictionIntervalCoverage')}>
                              {formatCoverage(activeTimeSeriesGate.prediction_interval_coverage.coverage_ratio)}
                              {activeTimeSeriesGate.prediction_interval_coverage.status === 'available'
                                ? ` (${activeTimeSeriesGate.prediction_interval_coverage.covered_rows}/${activeTimeSeriesGate.prediction_interval_coverage.evaluated_rows})`
                                : ''}
                            </Descriptions.Item>
                            <Descriptions.Item label={t('modelCenter.timeSeries.windowCoverage')}>
                              {formatCoverage(activeTimeSeriesGate.window_coverage.coverage_ratio)} ({activeTimeSeriesGate.window_coverage.evaluated_folds}/{activeTimeSeriesGate.window_coverage.requested_folds})
                            </Descriptions.Item>
                            <Descriptions.Item label={t('modelCenter.timeSeries.groupCoverage')}>
                              {activeTimeSeriesGate.group_coverage.status === 'not_applicable'
                                ? t('modelCenter.timeSeries.notApplicable')
                                : `${formatCoverage(activeTimeSeriesGate.group_coverage.coverage_ratio)} (${activeTimeSeriesGate.group_coverage.covered_groups}/${activeTimeSeriesGate.group_coverage.total_groups})`}
                            </Descriptions.Item>
                            <Descriptions.Item label={t('modelCenter.timeSeries.observedTarget')}>
                              {activeTimeSeriesGate.leakage_status.uses_observed_validation_targets ? t('modelCenter.timeSeries.yes') : t('modelCenter.timeSeries.no')}
                            </Descriptions.Item>
                            <Descriptions.Item label="MAE">{activeTimeSeriesGate.aggregate_metrics?.mae.toFixed(4) ?? '—'}</Descriptions.Item>
                            <Descriptions.Item label="RMSE">{activeTimeSeriesGate.aggregate_metrics?.rmse.toFixed(4) ?? '—'}</Descriptions.Item>
                            <Descriptions.Item label="R²">{activeTimeSeriesGate.aggregate_metrics?.r2.toFixed(4) ?? '—'}</Descriptions.Item>
                          </Descriptions>
                          <Table
                            size="small"
                            pagination={false}
                            rowKey="fold"
                            dataSource={activeTimeSeriesGate.folds}
                            locale={{ emptyText: t('modelCenter.timeSeries.noFoldEvidence') }}
                            columns={[
                              { title: t('modelCenter.timeSeries.fold'), dataIndex: 'fold', key: 'fold' },
                              { title: t('modelCenter.timeSeries.trainRows'), dataIndex: 'train_rows', key: 'trainRows' },
                              { title: t('modelCenter.timeSeries.trainDates'), key: 'trainDates', render: (_: unknown, row) => `${row.train_start} → ${row.train_end}` },
                              { title: t('modelCenter.timeSeries.validationRows'), dataIndex: 'validation_rows', key: 'validationRows' },
                              { title: t('modelCenter.timeSeries.validationDates'), key: 'validationDates', render: (_: unknown, row) => `${row.validation_start} → ${row.validation_end}` },
                              { title: 'MAE', key: 'mae', render: (_: unknown, row) => row.metrics.mae.toFixed(4) },
                              { title: 'RMSE', key: 'rmse', render: (_: unknown, row) => row.metrics.rmse.toFixed(4) },
                              { title: 'R²', key: 'r2', render: (_: unknown, row) => row.metrics.r2.toFixed(4) },
                              { title: t('modelCenter.timeSeries.predictionIntervalCoverage'), key: 'coverage', render: (_: unknown, row) => `${formatCoverage(row.prediction_interval_coverage.coverage_ratio)} (${row.prediction_interval_coverage.covered_rows}/${row.prediction_interval_coverage.evaluated_rows})` },
                            ]}
                          />
                        </Space>
                      </Card>
                    )}
                    <Alert type="info" showIcon message={unavailableLadderCount > 0 ? t('modelCenter.timeSeries.ladderAdvice') : t('modelCenter.timeSeries.allModelsAvailableAdvice')} />
                    {timeSeriesLadder.provenance?.persisted === false && (
                      <Alert type="warning" showIcon message={t('modelCenter.timeSeries.persistenceNotice')} />
                    )}
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
          {selectedModelId && (
            <Card type="inner" size="small" title={t('modelCenter.selectedModel.title')} style={{ marginTop: 12 }} loading={selectedModelInfoLoading}>
              {selectedModelInfo ? (
                <>
                  <Descriptions size="small" column={{ xs: 1, sm: 2, md: 3 }} bordered>
                    <Descriptions.Item label={t('modelCenter.selectedModel.status')}>
                      <Tag color="success">{t('modelCenter.selectedModel.loaded')}</Tag>
                    </Descriptions.Item>
                    <Descriptions.Item label={t('modelCenter.selectedModel.type')}>{selectedModelInfo.model_type}</Descriptions.Item>
                    <Descriptions.Item label={t('modelCenter.selectedModel.target')}>{selectedModelInfo.target}</Descriptions.Item>
                    <Descriptions.Item label={t('modelCenter.selectedModel.inputs')}>{selectedModelInfo.inputs.join(', ') || '—'}</Descriptions.Item>
                    <Descriptions.Item label={t('modelCenter.selectedModel.trainingRows')}>{selectedModelInfo.n_train}</Descriptions.Item>
                    {selectedTimeSeriesLadderRow && (
                      <Descriptions.Item label={t('modelCenter.timeSeries.backend')}>
                        {timeSeriesBackendDetails(selectedTimeSeriesLadderRow)}
                      </Descriptions.Item>
                    )}
                    <Descriptions.Item label={t('modelCenter.selectedModel.replay')}>
                      <Tag color="green">{t('modelCenter.selectedModel.replayReady')}</Tag>
                    </Descriptions.Item>
                  </Descriptions>
                  {selectedModelInfo.model_type.startsWith('time_series_') && (
                    <Space direction="vertical" style={{ width: '100%', marginTop: 12 }} size="middle">
                      <Card size="small" title={t('modelCenter.timeSeries.sequenceSimulation.title')}>
                        <Space direction="vertical" style={{ width: '100%' }}>
                          <Alert type="info" showIcon message={t('modelCenter.timeSeries.sequenceSimulation.description')} />
                          <Space wrap>
                            <Select
                              value={sequenceSimulationModelId}
                              onChange={setSequenceSimulationModelId}
                              placeholder={t('modelCenter.timeSeries.sequenceSimulation.selectModel')}
                              style={{ minWidth: 260 }}
                              options={models
                                .filter((model) => String(model.model_type) === 'time_series_transformer')
                                .map((model) => ({ value: model.model_id, label: `${model.model_type} v${model.version}` }))}
                            />
                            <InputNumber
                              min={1}
                              value={sequenceSimulationHorizon}
                              onChange={(value) => setSequenceSimulationHorizon(value ?? 1)}
                              addonBefore={t('modelCenter.timeSeries.sequenceSimulation.horizon')}
                            />
                            <Select
                              value={sequenceSimulationMode}
                              onChange={setSequenceSimulationMode}
                              style={{ minWidth: 180 }}
                              options={[
                                { value: 'sequence_aware', label: t('modelCenter.timeSeries.sequenceSimulation.deterministicMode') },
                                { value: 'sequence_stochastic', label: t('modelCenter.timeSeries.sequenceSimulation.stochasticMode') },
                              ]}
                            />
                            {sequenceSimulationMode === 'sequence_stochastic' && (
                              <>
                                <InputNumber min={1} value={sequenceSimulationCount} onChange={(value) => setSequenceSimulationCount(value ?? 1)} addonBefore={t('modelCenter.timeSeries.sequenceSimulation.simulationCount')} />
                                <InputNumber value={sequenceSimulationSeed} onChange={(value) => setSequenceSimulationSeed(value ?? 0)} addonBefore={t('modelCenter.timeSeries.sequenceSimulation.seed')} />
                              </>
                            )}
                            <Button type="primary" loading={sequenceSimulationLoading} onClick={handleRunSequenceSimulation} disabled={!datasetId || !sequenceSimulationModelId}>
                              {sequenceSimulationLoading
                                ? t('modelCenter.timeSeries.sequenceSimulation.running')
                                : t('modelCenter.timeSeries.sequenceSimulation.run')}
                            </Button>
                          </Space>
                          <Input.TextArea
                            value={sequenceSimulationHistory}
                            onChange={(event) => setSequenceSimulationHistory(event.target.value)}
                            rows={4}
                            placeholder={t('modelCenter.timeSeries.sequenceSimulation.historyPlaceholder')}
                          />
                          <Input.TextArea
                            value={sequenceSimulationScenarios}
                            onChange={(event) => setSequenceSimulationScenarios(event.target.value)}
                            rows={4}
                            placeholder={t('modelCenter.timeSeries.sequenceSimulation.scenariosPlaceholder')}
                          />
                          {sequenceSimulationResult?.status === 'blocked' && (
                            <Alert type="error" showIcon message={t('modelCenter.timeSeries.sequenceSimulation.blocked')} description={sequenceSimulationResult.final_gate.reasons.join(', ')} />
                          )}
                          {sequenceSimulationResult?.status === 'not_supported' && (
                            <Alert type="warning" showIcon message={t('modelCenter.timeSeries.sequenceSimulation.needsSequence')} />
                          )}
                          {sequenceSimulationResult?.status === 'dry_run' && (
                            <>
                              <Alert type="success" showIcon message={t('modelCenter.timeSeries.sequenceSimulation.deterministic')} description={t('modelCenter.timeSeries.sequenceSimulation.uncertaintyUnavailable')} />
                              <Descriptions bordered size="small" column={{ xs: 1, sm: 2, md: 3 }}>
                                <Descriptions.Item label={t('modelCenter.timeSeries.sequenceSimulation.windowRows')}>{sequenceSimulationResult.history_window?.rows}</Descriptions.Item>
                                <Descriptions.Item label={t('modelCenter.timeSeries.sequenceSimulation.sequenceLength')}>{sequenceSimulationResult.history_window?.sequence_length}</Descriptions.Item>
                                <Descriptions.Item label={t('modelCenter.timeSeries.sequenceSimulation.forecastMode')}>{sequenceSimulationResult.scenario_provenance?.forecast_mode}</Descriptions.Item>
                                <Descriptions.Item label={t('modelCenter.timeSeries.backend')}>{sequenceSimulationResult.final_gate.provenance.backend}</Descriptions.Item>
                                <Descriptions.Item label={t('modelCenter.timeSeries.sequenceSimulation.schemaVersion')}>{sequenceSimulationResult.final_gate.provenance.schema_version}</Descriptions.Item>
                                <Descriptions.Item label={t('modelCenter.timeSeries.sequenceSimulation.modelVersion')}>{sequenceSimulationResult.final_gate.provenance.model_version}</Descriptions.Item>
                              </Descriptions>
                              <Table
                                size="small"
                                pagination={false}
                                rowKey="timestamp"
                                dataSource={sequenceSimulationResult.predictions ?? []}
                                columns={[
                                  { title: t('modelCenter.timeSeries.sequenceSimulation.timestamp'), dataIndex: 'timestamp', key: 'timestamp' },
                                  { title: t('modelCenter.timeSeries.sequenceSimulation.predicted'), dataIndex: 'predicted', key: 'predicted', render: (value: number) => value.toFixed(6) },
                                ]}
                              />
                            </>
                          )}
                          {sequenceSimulationResult?.status === 'stochastic' && (
                            <>
                              <Alert type="success" showIcon message={t('modelCenter.timeSeries.sequenceSimulation.stochasticComplete')} description={t('modelCenter.timeSeries.sequenceSimulation.coverageUnavailable')} />
                              <Descriptions bordered size="small" column={{ xs: 1, sm: 2, md: 3 }}>
                                <Descriptions.Item label={t('modelCenter.timeSeries.sequenceSimulation.residualMethod')}>{sequenceSimulationResult.simulation?.residual_method}</Descriptions.Item>
                                <Descriptions.Item label={t('modelCenter.timeSeries.sequenceSimulation.residualScale')}>{sequenceSimulationResult.provenance?.residual_scale?.toFixed(6)}</Descriptions.Item>
                                <Descriptions.Item label={t('modelCenter.timeSeries.sequenceSimulation.simulationCount')}>{sequenceSimulationResult.simulation?.n_simulations}</Descriptions.Item>
                                <Descriptions.Item label={t('modelCenter.timeSeries.sequenceSimulation.seed')}>{sequenceSimulationResult.simulation?.seed}</Descriptions.Item>
                                <Descriptions.Item label={t('modelCenter.timeSeries.backend')}>{sequenceSimulationResult.provenance?.backend}</Descriptions.Item>
                                <Descriptions.Item label={t('modelCenter.timeSeries.sequenceSimulation.schemaVersion')}>{sequenceSimulationResult.provenance?.schema_version}</Descriptions.Item>
                              </Descriptions>
                              <Table size="small" pagination={false} rowKey="timestamp" dataSource={sequenceSimulationResult.summary ?? []} columns={[
                                { title: t('modelCenter.timeSeries.sequenceSimulation.timestamp'), dataIndex: 'timestamp', key: 'timestamp' },
                                ...(['mean', 'p05', 'p50', 'p95'] as const).map((key) => ({ title: key.toUpperCase(), dataIndex: key, key, render: (value: number) => value.toFixed(6) })),
                              ]} />
                            </>
                          )}
                        </Space>
                      </Card>
                      <Card size="small" title={t('modelCenter.timeSeries.explanation.title')}>
                        <Space direction="vertical" style={{ width: '100%' }}>
                        <Button type="primary" loading={timeSeriesExplanationLoading} onClick={handleExplainTimeSeriesModel}>
                          {timeSeriesExplanationLoading
                            ? t('modelCenter.timeSeries.explanation.running')
                            : t('modelCenter.timeSeries.explanation.run')}
                        </Button>
                        <Alert
                          type="warning"
                          showIcon
                          message={t('modelCenter.timeSeries.explanation.nonCausalTitle')}
                          description={t('modelCenter.timeSeries.explanation.nonCausalDescription')}
                        />
                        {timeSeriesExplanation && (
                          <Space direction="vertical" style={{ width: '100%' }}>
                            <Descriptions bordered size="small" column={{ xs: 1, sm: 2, md: 3 }}>
                              <Descriptions.Item label={t('modelCenter.timeSeries.explanation.evidenceStatus')}>
                                <Tag color="processing">{t('modelCenter.timeSeries.explanation.modelInferred')}</Tag>
                              </Descriptions.Item>
                              <Descriptions.Item label={t('modelCenter.timeSeries.protocol')}>{timeSeriesProtocol(timeSeriesExplanation.metadata.evaluation_protocol)}</Descriptions.Item>
                              <Descriptions.Item label={t('modelCenter.timeSeries.explanation.expectedValue')}>{timeSeriesExplanation.feature_importance.expected_value.toFixed(4)}</Descriptions.Item>
                              <Descriptions.Item label={t('modelCenter.timeSeries.explanation.importanceMethod')}>{t(`modelCenter.timeSeries.explanation.methods.${timeSeriesExplanation.feature_importance.method}`, { defaultValue: timeSeriesExplanation.feature_importance.method })}</Descriptions.Item>
                              <Descriptions.Item label={t('modelCenter.timeSeries.explanation.blockSize')}>{timeSeriesExplanation.sensitivity.block_size}</Descriptions.Item>
                              <Descriptions.Item label={t('modelCenter.timeSeries.explanation.randomSeed')}>{timeSeriesExplanation.sensitivity.random_seed}</Descriptions.Item>
                            </Descriptions>

                            <Typography.Title level={5}>{t('modelCenter.timeSeries.explanation.featureImportanceTitle')}</Typography.Title>
                            <Table
                              size="small"
                              pagination={false}
                              rowKey="name"
                              dataSource={timeSeriesExplanation.feature_importance.features}
                              columns={[
                                { title: t('modelCenter.timeSeries.explanation.feature'), dataIndex: 'name', key: 'name' },
                                { title: t('modelCenter.timeSeries.explanation.importance'), dataIndex: 'importance', key: 'importance', render: (value: number) => `${(value * 100).toFixed(2)}%` },
                                { title: t('modelCenter.timeSeries.explanation.sourceColumn'), key: 'sourceColumn', render: (_: unknown, row: TimeSeriesExplanationResult['feature_importance']['features'][number]) => row.provenance.source_column },
                                { title: t('modelCenter.timeSeries.explanation.derivation'), key: 'kind', render: (_: unknown, row: TimeSeriesExplanationResult['feature_importance']['features'][number]) => timeSeriesProvenanceKind(row.provenance.kind) },
                                { title: t('modelCenter.timeSeries.lags'), key: 'lag', render: (_: unknown, row: TimeSeriesExplanationResult['feature_importance']['features'][number]) => row.provenance.lag ?? '—' },
                                { title: t('modelCenter.timeSeries.explanation.window'), key: 'window', render: (_: unknown, row: TimeSeriesExplanationResult['feature_importance']['features'][number]) => row.provenance.window ?? '—' },
                                { title: t('modelCenter.timeSeries.explanation.availabilityTitle'), key: 'availability', render: (_: unknown, row: TimeSeriesExplanationResult['feature_importance']['features'][number]) => timeSeriesAvailability(row.provenance.availability) },
                              ]}
                            />

                            <Typography.Title level={5}>{t('modelCenter.timeSeries.explanation.sensitivityTitle')}</Typography.Title>
                            <Alert type="info" showIcon message={t('modelCenter.timeSeries.explanation.sensitivityDescription')} />
                            <Table
                              size="small"
                              pagination={false}
                              rowKey="name"
                              dataSource={timeSeriesExplanation.sensitivity.features}
                              columns={[
                                { title: t('modelCenter.timeSeries.explanation.feature'), dataIndex: 'name', key: 'name' },
                                { title: t('modelCenter.timeSeries.explanation.maeIncrease'), dataIndex: 'mae_increase', key: 'maeIncrease', render: (value: number) => value.toFixed(4) },
                                { title: t('modelCenter.timeSeries.explanation.baselineMae'), dataIndex: 'baseline_mae', key: 'baselineMae', render: (value: number) => value.toFixed(4) },
                                { title: t('modelCenter.timeSeries.explanation.perturbedMae'), dataIndex: 'perturbed_mae', key: 'perturbedMae', render: (value: number) => value.toFixed(4) },
                              ]}
                            />

                            <Typography.Title level={5}>{t('modelCenter.timeSeries.explanation.interactionsTitle')}</Typography.Title>
                            <Alert type="info" showIcon message={t('modelCenter.timeSeries.explanation.interactionsDescription')} />
                            <Table
                              size="small"
                              pagination={{ pageSize: 8, hideOnSinglePage: true }}
                              rowKey={(row) => `${row.feature}:${row.conditioning_feature}`}
                              dataSource={timeSeriesExplanation.interactions.pairs}
                              columns={[
                                { title: t('modelCenter.timeSeries.explanation.feature'), dataIndex: 'feature', key: 'feature' },
                                { title: t('modelCenter.timeSeries.explanation.conditioningFeature'), dataIndex: 'conditioning_feature', key: 'conditioningFeature' },
                                { title: t('modelCenter.timeSeries.explanation.strength'), dataIndex: 'strength', key: 'strength', render: (value: number) => value.toFixed(6) },
                                { title: t('modelCenter.timeSeries.explanation.stratumContrasts'), dataIndex: 'stratum_contrasts', key: 'stratumContrasts', render: (values: number[]) => values.map((value) => value.toFixed(4)).join(', ') || '—' },
                                { title: t('modelCenter.timeSeries.explanation.evidenceStatus'), key: 'evidenceStatus', render: () => <Tag color="processing">{t('modelCenter.timeSeries.explanation.modelInferred')}</Tag> },
                              ]}
                            />
                          </Space>
                        )}
                        </Space>
                      </Card>
                    </Space>
                  )}
                </>
              ) : (
                <Alert type="warning" showIcon message={t('modelCenter.selectedModel.unavailable')} />
              )}
            </Card>
          )}
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
              disabled={models.length === 0 || !datasetId || timeSeriesActive}
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
              <Alert type="info" showIcon message={timeSeriesActive ? t('modelCenter.timeSeries.notApplicable') : t('modelCenter.noInteraction')} />
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
              <Alert type="info" showIcon message={timeSeriesActive ? t('modelCenter.timeSeries.notApplicable') : t('modelCenter.noInteraction')} />
            )}
          </Space>
        </Card>

        <Card title={t('modelCenter.sensitivityTitle')} size="small">
          <Button type="primary" loading={sensitivityLoading} onClick={handleComputeSensitivity} disabled={!models.length || !datasetId || timeSeriesActive}>
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
                disabled={models.length === 0 || !datasetId || timeSeriesActive}
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
              disabled={models.length === 0 || !datasetId || timeSeriesActive}
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
                        {
                          title: t('modelCenter.doeColumn'), dataIndex: 'name', key: 'name', width: 150,
                          render: (name: string) => name === '1' ? '截距（Intercept）' : name,
                        },
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
              disabled={models.length === 0 || !datasetId || timeSeriesActive}
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
