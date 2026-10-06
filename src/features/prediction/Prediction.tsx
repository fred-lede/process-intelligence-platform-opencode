import { useEffect, useRef, useState, useCallback } from 'react'
import type { CSSProperties, PointerEvent as ReactPointerEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, Select, Space, Button, Alert, Typography, Tag, InputNumber, Statistic, Modal, Input, message, Row, Col } from 'antd'
import { PlusOutlined, MinusOutlined, SaveOutlined, HistoryOutlined } from '@ant-design/icons'
import { useDataPipelineStore } from '../../stores/dataPipelineStore'
import { useAssistantContextStore } from '../../stores/assistantContextStore'
import { predictOutput, getModelInfo, listModels, saveScenario, listScenarios, recommendProfilerSettings, runOptQuest, compareMonteCarlo, type ModelInfo, type PredictionScenario, type OptQuestResult, type MonteCarloComparison } from '../../lib/engine'
import { buildPredictionContext } from '../../lib/assistantData'
import Plot from '../../components/PlotChart'

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
  const { setContext } = useAssistantContextStore()

  const [models, setModels] = useState<Array<{ model_id: string; model_type: string; equation: string }>>([])
  const [selectedModel, setSelectedModel] = useState<string | undefined>()
  const [optimizationObjective, setOptimizationObjective] = useState<'maximize' | 'minimize' | 'target'>('target')
  const [profilerRecommendation, setProfilerRecommendation] = useState<Record<string, unknown> | null>(null)
  const [profilerLoading, setProfilerLoading] = useState(false)
  const [modelInfo, setModelInfo] = useState<ModelInfo | null>(null)
  const [inputValues, setInputValues] = useState<Record<string, number>>({})
  const [predicted, setPredicted] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [scenarios, setScenarios] = useState<PredictionScenario[]>([])
  const [saveModalOpen, setSaveModalOpen] = useState(false)
  const [scenarioName, setScenarioName] = useState('')
  const [scenarioNotes, setScenarioNotes] = useState('')
  const [messageApi, contextHolder] = message.useMessage()
  // OptQuest 卡 state
  const [optObjective, setOptObjective] = useState<'maximize_yield' | 'minimize_dpmo' | 'hit_target'>('maximize_yield')
  const [optTarget, setOptTarget] = useState<number | undefined>(undefined)
  const [optCpkMin, setOptCpkMin] = useState<number>(1.33)
  const [optCandidates, setOptCandidates] = useState<number>(200)
  const [optEvalSamples, setOptEvalSamples] = useState<number>(500)
  const [optSeed, setOptSeed] = useState<number>(42)
  const [optAdvanced, setOptAdvanced] = useState<boolean>(false)
  const [optResult, setOptResult] = useState<OptQuestResult | null>(null)
  const [optLoading, setOptLoading] = useState(false)
  const [optMcComparison, setOptMcComparison] = useState<MonteCarloComparison | null>(null)
  const [optMcLoading, setOptMcLoading] = useState(false)

  useEffect(() => {
    setContext('prediction', buildPredictionContext({ modelInfo, inputValues, predicted }))
  }, [modelInfo, inputValues, predicted, setContext])

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

  const handleOptQuest = async () => {
    if (!selectedModel || !importResult) return
    setOptLoading(true)
    setOptResult(null)
    try {
      const res = await runOptQuest({
        model_id: selectedModel,
        dataset_id: importResult.dataset_id,
        objective: optObjective,
        lsl: spec?.lsl ?? undefined,
        usl: spec?.usl ?? undefined,
        target_value: optObjective === 'hit_target' ? (optTarget ?? spec?.target ?? undefined) : undefined,
        cpk_min: optCpkMin,
        n_candidates: optCandidates,
        n_eval_samples: optEvalSamples,
        seed: optSeed,
      })
      if (!res.success || !res.result) {
        messageApi.error(res.error?.message ?? res.error?.code ?? t('prediction.optquestError'))
        return
      }
      setOptResult(res.result)
    } catch (e) {
      messageApi.error(e instanceof Error ? e.message : String(e))
    } finally {
      setOptLoading(false)
    }
  }

  const handleApplyBestPoint = () => {
    if (!optResult) return
    setInputValues(prev => ({ ...prev, ...optResult.best_point }))
  }

  const handleOptQuestMcCompare = async () => {
    if (!selectedModel || !importResult || !optResult) return
    setOptMcLoading(true)
    setOptMcComparison(null)
    try {
      const baseParams = {
        dataset_id: importResult.dataset_id,
        model_id: selectedModel,
        n_simulations: 2000,
        seed: 42,
        sampling_method: 'auto' as const,
        lsl: spec?.lsl ?? undefined,
        usl: spec?.usl ?? undefined,
      }
      const res = await compareMonteCarlo({
        baseline: baseParams,
        candidate: { ...baseParams, input_means: optResult.best_point },
      })
      if (!res.success || !res.comparison) {
        messageApi.error(res.error?.message ?? res.error?.code ?? t('prediction.optquestError'))
        return
      }
      setOptMcComparison(res.comparison)
    } catch (e) {
      messageApi.error(e instanceof Error ? e.message : String(e))
    } finally {
      setOptMcLoading(false)
    }
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

  const profilerPerInput = (() => {
    if (!profilerRecommendation) return []
    const rec = profilerRecommendation as {
      objective?: string; target_value?: number;
      current?: Record<string, number>;
      candidates?: Array<{input: string; value: number; predicted: number}>;
      ranges?: Record<string, {min: number; max: number}>;
    }
    const obj = rec.objective ?? 'maximize'
    const target = rec.target_value ?? 0
    const cur = rec.current ?? {}
    const cands = rec.candidates ?? []
    const byInput = new Map<string, Array<{value: number; predicted: number}>>()
    for (const c of cands) {
      const list = byInput.get(c.input) ?? []
      list.push(c)
      byInput.set(c.input, list)
    }
    return Array.from(byInput.entries()).map(([input, items]) => {
      const score = (c: {predicted: number}) =>
        obj === 'target' ? Math.abs(c.predicted - target)
          : obj === 'maximize' ? -c.predicted : c.predicted
      const best = items.reduce((a, b) => (score(a) < score(b) ? a : b))
      return { input, current: cur[input] ?? null, value: best.value, predicted: best.predicted }
    })
  })()

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
          <Select value={optimizationObjective} onChange={setOptimizationObjective} style={{ width: 220 }} options={[{ value: 'maximize', label: t('prediction.objectiveMaximize') }, { value: 'minimize', label: t('prediction.objectiveMinimize') }, { value: 'target', label: t('prediction.objectiveTarget') }]} />
          <Button loading={profilerLoading} disabled={!selectedModel || !importResult} onClick={async () => { if (!selectedModel || !importResult) return; setProfilerLoading(true); try { setProfilerRecommendation(await recommendProfilerSettings({ model_id: selectedModel, dataset_id: importResult.dataset_id, objective: optimizationObjective, target_value: spec?.target ?? undefined, current: inputValues })) } finally { setProfilerLoading(false) } }}>{t('prediction.generateRecommendation')}</Button>
          <Button onClick={handleRestore} disabled={!hasData || !modelInfo}>
            {t('prediction.restoreDefaults')}
          </Button>
        </Space>
      </Card>

      {modelInfo && (
        <Row gutter={[16, 16]} style={{ width: '100%' }}>
          <Col flex="1 1 auto" style={{ minWidth: 0 }}>
            <Card title={t('prediction.profilerTitle')} size="small">
              <Alert type="warning" showIcon message={t('prediction.profilerLimit')} style={{ marginBottom: 12 }} />
              {profilerRecommendation && profilerPerInput.length > 0 && (
                <Alert type="info" showIcon message={t('prediction.recommendationReady')} description={
                  <div style={{ fontSize: 12 }}>
                    {profilerPerInput.map(({ input, current: cur, value, predicted }) => (
                      <div key={input} style={{ marginBottom: 2 }}>
                        <span style={{ fontWeight: 600 }}>{input}</span>: {cur !== null ? `${cur.toFixed(2)} → ` : ''}
                        <span style={{ color: '#1677ff' }}>{value.toFixed(2)}</span>
                        {' '}<span style={{ color: '#888' }}>(predicted: {predicted.toFixed(4)})</span>
                      </div>
                    ))}
                  </div>
                } style={{ marginBottom: 12 }} />
              )}
              <pre style={{ fontSize: 13, marginBottom: 12, padding: '4px 8px', background: '#f5f5f5', borderRadius: 4, margin: '0 0 12px 0', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{modelInfo.equation}</pre>
              <Alert
                type="info"
                showIcon
                message={t('prediction.effectTitle')}
                description={(
                  <Space direction="vertical" size={2}>
                    {modelInfo.inputs.map((inp) => {
                      const coef = modelInfo.coefficients?.[inp] ?? 0
                      const std = importResult?.stats.column_stats[inp]?.std ?? 1
                      const effect = coef * (typeof std === 'number' && isFinite(std) ? std : 1)
                      const target = spec?.target ?? null
                      const targetDirection = target !== null && predicted !== null ? predicted < target : null
                      const actionIncrease = optimizationObjective === 'minimize' ? effect < 0 : optimizationObjective === 'target' && targetDirection !== null ? (targetDirection ? effect >= 0 : effect < 0) : effect >= 0
                      const action = optimizationObjective === 'target' && targetDirection === null ? t('prediction.effectTargetOnly') : actionIncrease ? t('prediction.effectActionIncrease') : t('prediction.effectActionDecrease')
                      return <span key={inp}>{inp}: {effect >= 0 ? '+' : ''}{effect.toFixed(4)} · {effect >= 0 ? t('prediction.effectIncrease') : t('prediction.effectDecrease')} · {action}</span>
                    })}
                    <span>{t('prediction.effectAdvice')}</span>
                  </Space>
                )}
                style={{ marginBottom: 12 }}
              />
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
                {modelInfo?.model_type === 'logistic_regression' ? (
                  <>
                    <Statistic
                      title={t('prediction.predictedProbability')}
                      value={(predicted ?? 0) * 100}
                      precision={1}
                      suffix="%"
                      loading={loading}
                    />
                    <Tag color={(predicted ?? 0) > 0.5 ? 'red' : 'green'} style={{ fontSize: 14, padding: '4px 12px' }}>
                      {t((predicted ?? 0) > 0.5 ? 'prediction.ng' : 'prediction.ok')}
                      {' · '}
                      {(predicted ?? 0) > 0.5 ? t('prediction.highRisk') : t('prediction.lowRisk')}
                    </Tag>
                  </>
                ) : modelInfo?.model_type === 'weibull_regression' ? (
                  <>
                    <Statistic
                      title={t('prediction.predictedMeanTTF')}
                      value={predicted ?? 0}
                      precision={2}
                      loading={loading}
                    />
                    <Tag color={(predicted ?? 0) > 1 ? 'green' : 'orange'} style={{ fontSize: 12, padding: '2px 8px' }}>
                      {(predicted ?? 0) > 1 ? t('prediction.longLife') : t('prediction.shortLife')}
                    </Tag>
                  </>
                ) : (
                  <>
                    <Statistic
                      title={t('prediction.predictedOutput')}
                      value={predicted ?? 0}
                      precision={2}
                      loading={loading}
                    />
                    {ngStatus && (
                      <Tag color={ngStatus.color} style={{ fontSize: 14, padding: '4px 12px' }}>
                        {ngStatus.text}
                      </Tag>
                    )}
                  </>
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

      {modelInfo && importResult && (
        <Card title={t('prediction.optquestTitle')} size="small">
          <Alert type="info" showIcon message={t('prediction.optquestDesc')} style={{ marginBottom: 12 }} />
          <Space wrap style={{ marginBottom: 12 }}>
            <Select value={optObjective} onChange={setOptObjective} style={{ width: 260 }} options={[
              { value: 'maximize_yield', label: t('prediction.optquestMaxYield') },
              { value: 'minimize_dpmo', label: t('prediction.optquestMinDpmo') },
              { value: 'hit_target', label: t('prediction.optquestHitTarget') },
            ]} />
            {optObjective === 'hit_target' && (
              <InputNumber placeholder={t('prediction.optquestTarget')} value={optTarget}
                           onChange={v => setOptTarget(v ?? undefined)} style={{ width: 140 }} />
            )}
            {optObjective === 'hit_target' && (
              <InputNumber min={0.5} max={2.5} step={0.01} value={optCpkMin}
                           onChange={v => setOptCpkMin(v ?? 1.33)} style={{ width: 120 }}
                           addonBefore={t('prediction.optquestCpkMin')} />
            )}
            <Button type="primary" loading={optLoading}
                    disabled={!selectedModel || !importResult}
                    onClick={handleOptQuest}>
              {t('prediction.optquestRun')}
            </Button>
            <Button type="link" onClick={() => setOptAdvanced(!optAdvanced)}>
              {optAdvanced ? t('prediction.optquestAdvancedHide') : t('prediction.optquestAdvanced')}
            </Button>
          </Space>
          {optAdvanced && (
            <Space wrap style={{ marginBottom: 12 }}>
              <InputNumber min={20} max={2000} step={20} value={optCandidates}
                           onChange={v => setOptCandidates(v ?? 200)}
                           addonBefore={t('prediction.optquestCandidates')} style={{ width: 180 }} />
              <InputNumber min={50} max={5000} step={50} value={optEvalSamples}
                           onChange={v => setOptEvalSamples(v ?? 500)}
                           addonBefore={t('prediction.optquestEvalSamples')} style={{ width: 180 }} />
              <InputNumber min={0} value={optSeed} onChange={v => setOptSeed(v ?? 42)}
                           addonBefore={t('prediction.optquestSeed')} style={{ width: 140 }} />
            </Space>
          )}
          {optResult && (
            <>
              {optResult.exploratory_warning && <Alert type="warning" showIcon message="探索性結果" description={optResult.exploratory_warning} style={{ marginBottom: 8 }} />}
              <Space wrap style={{ marginBottom: 8 }} align="center">
                <Tag color={optResult.feasible ? 'green' : 'red'}>
                  {optResult.feasible ? t('prediction.optquestFeasible') : t('prediction.optquestInfeasible')}
                </Tag>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {t('prediction.optquestCandidates')}: {optResult.n_candidates} · {t('prediction.optquestEvalSamples')}: {optResult.n_eval_samples} · seed {optResult.seed}
                </Typography.Text>
              </Space>
              <Row gutter={16} style={{ marginBottom: 8 }}>
                <Col span={12}>
                  <Card size="small" title={t('prediction.optquestBaseline')}>
                    {optResult.baseline && (
                      <Statistic value={optResult.baseline.predicted_mean} precision={3}
                                 title={t('prediction.optquestPredictedMean')} />
                    )}
                    {optResult.baseline?.yield != null && (
                      <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block' }}>
                        {t('prediction.optquestYield')}: {(optResult.baseline.yield * 100).toFixed(2)}% · DPMO: {optResult.baseline.dpmo?.toFixed(0)}
                      </Typography.Text>
                    )}
                  </Card>
                </Col>
                <Col span={12}>
                  <Card size="small" title={t('prediction.optquestBest')}>
                    <Statistic value={optResult.best.predicted_mean} precision={3}
                               title={t('prediction.optquestPredictedMean')} />
                    {optResult.best.yield != null && (
                      <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block' }}>
                        {t('prediction.optquestYield')}: {(optResult.best.yield * 100).toFixed(2)}% · DPMO: {optResult.best.dpmo?.toFixed(0)}
                      </Typography.Text>
                    )}
                  </Card>
                </Col>
              </Row>
              <Card size="small" title={t('prediction.optquestBestPoint')} style={{ marginBottom: 8 }}>
                <Space wrap>
                  {Object.entries(optResult.best_point).map(([k, v]) => (
                    <Tag key={k} color="blue">{k}: {v.toFixed(3)}</Tag>
                  ))}
                  <Button size="small" type="primary" onClick={handleApplyBestPoint}>
                    {t('prediction.optquestApply')}
                  </Button>
                  <Button size="small" loading={optMcLoading} onClick={handleOptQuestMcCompare}>
                    {t('prediction.optquestMcCompare')}
                  </Button>
                </Space>
              </Card>
              {optMcComparison && (
                <Card size="small" title={t('prediction.optquestMcComparison')} style={{ marginBottom: 8 }}>
                  <Plot
                    data={[
                      {
                        x: optMcComparison.baseline.histogram.bins.slice(0, -1),
                        y: optMcComparison.baseline.histogram.counts,
                        type: 'bar', name: t('monteCarlo.baseline'),
                        marker: { color: '#1677ff', opacity: 0.6 },
                      },
                      {
                        x: optMcComparison.candidate.histogram.bins.slice(0, -1),
                        y: optMcComparison.candidate.histogram.counts,
                        type: 'bar', name: t('prediction.optquestMcCandidate'),
                        marker: { color: '#52c41a', opacity: 0.6 },
                      },
                    ]}
                    layout={{
                      barmode: 'overlay', height: 320,
                      xaxis: { title: t('monteCarlo.outputDistribution') },
                      yaxis: { title: t('monteCarlo.frequency') },
                      legend: { orientation: 'h', y: -0.25 },
                    }}
                  />
                  <Row gutter={16}>
                    <Col span={8}>
                      <Statistic title={t('monteCarlo.meanShift')}
                                 value={optMcComparison.mean_shift} precision={3}
                                 valueStyle={{ color: optMcComparison.mean_shift >= 0 ? '#52c41a' : '#ff4d4f' }} />
                    </Col>
                    <Col span={8}>
                      <Statistic title={t('monteCarlo.stdReduction')}
                                 value={optMcComparison.std_reduction_pct * 100} precision={1}
                                 suffix="%"
                                 valueStyle={{ color: optMcComparison.std_reduction_pct >= 0 ? '#52c41a' : '#ff4d4f' }} />
                    </Col>
                    <Col span={8}>
                      {optMcComparison.dpmo_baseline != null && optMcComparison.dpmo_candidate != null && (
                        <Statistic title={t('monteCarlo.dpmo')}
                                   value={optMcComparison.dpmo_candidate} precision={0}
                                   valueStyle={{ color: optMcComparison.dpmo_candidate <= optMcComparison.dpmo_baseline ? '#52c41a' : '#ff4d4f' }} />
                      )}
                    </Col>
                  </Row>
                  <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 8 }}>
                    {t('monteCarlo.overlayHint')}
                  </Typography.Text>
                </Card>
              )}
              <Card size="small" title={t('prediction.optquestTrajectory')}>
                <Plot
                  data={[{
                    x: optResult.trajectory.map(s => s.step),
                    y: optResult.trajectory.map(s => s.best_so_far),
                    type: 'scatter', mode: 'lines',
                    line: { color: '#722ed1', width: 2 },
                  }]}
                  layout={{
                    height: 260, margin: { l: 50, r: 20, t: 10, b: 40 },
                    xaxis: { title: t('prediction.optquestCandidateStep') },
                    yaxis: { title: t('prediction.optquestBestSoFar') },
                  }}
                />
              </Card>
              <Alert type="warning" showIcon message={optResult.note} style={{ marginTop: 8 }} />
            </>
          )}
        </Card>
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
