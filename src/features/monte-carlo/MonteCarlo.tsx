import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, Select, Space, Button, Alert, Form, Input, Switch, Typography, Table, Tag, Row, Col, Statistic } from 'antd'
import Plot from '../../components/PlotChart'
import NodeSourceFilter from '../../components/NodeSourceFilter'
import { useDataPipelineStore } from '../../stores/dataPipelineStore'
import { useAssistantContextStore } from '../../stores/assistantContextStore'
import { analyzeMonteCarlo, getFlowGraph, listModels, type MonteCarloResult } from '../../lib/engine'
import {
  consumeNodeContext,
  dataSourceLoaded,
  findNodeById,
} from '../../lib/processFlowContext'
import { buildMonteCarloContext } from '../../lib/assistantData'

export default function MonteCarlo() {
  const { t } = useTranslation()
  const { importResult, spec } = useDataPipelineStore()
  const { setContext } = useAssistantContextStore()

  const consumedRef = useRef(false)
  const [sourcedFromNode, setSourcedFromNode] = useState<{
    nodeId: string
    displayName: string
    dataSourceIds?: string[]
  } | null>(null)
  const [nodeFilterColumn, setNodeFilterColumn] = useState<string | undefined>(undefined)
  const [nodeFilterValue, setNodeFilterValue] = useState<string | undefined>(undefined)

  useEffect(() => {
    if (consumedRef.current) return
    consumedRef.current = true
    const pendingCtx = consumeNodeContext()
    if (pendingCtx) {
      ;(async () => {
        const node = await findNodeById(pendingCtx.nodeId)
        if (!node) return
        setSourcedFromNode({
          nodeId: pendingCtx.nodeId,
          displayName: node.display_name,
          dataSourceIds: pendingCtx.dataSourceIds,
        })
        if (dataSourceLoaded(pendingCtx.dataSourceIds, importResult?.dataset_id)) {
          try {
            const graph = await getFlowGraph()
            const key = graph.association_keys[0]
            if (key && importResult?.stats.column_stats?.[key]) {
              setNodeFilterColumn(key)
            }
          } catch {
            // ignore — filter default is optional
          }
        }
      })()
    }
  }, [])

  const [models, setModels] = useState<Array<{ model_id: string; model_type: string; equation: string }>>([])
  const [selectedModel, setSelectedModel] = useState<string | undefined>()
  const [nSimulations, setNSimulations] = useState<number>(10000)
  const [seed, setSeed] = useState<number>(42)
  const [enableAnomalies, setEnableAnomalies] = useState<boolean>(false)
  const [result, setResult] = useState<MonteCarloResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listModels().then(r => {
      if (r.models) {
        setModels(r.models.map(m => ({ model_id: m.model_id, model_type: m.model_type, equation: m.equation })))
      }
    }).catch(() => {})
  }, [])

  useEffect(() => {
    setContext('monteCarlo', buildMonteCarloContext(result))
  }, [result, setContext])

  const handleRun = async () => {
    if (!importResult || !selectedModel) return
    setLoading(true)
    setError(null)
    try {
      const res = await analyzeMonteCarlo({
        dataset_id: importResult.dataset_id,
        model_id: selectedModel,
        n_simulations: nSimulations,
        seed,
        enable_anomalies: enableAnomalies,
        lsl: spec?.lsl ?? undefined,
        usl: spec?.usl ?? undefined,
        ...(nodeFilterColumn && nodeFilterValue
          ? { filter_column: nodeFilterColumn, filter_value: nodeFilterValue }
          : {}),
      })
      setResult(res.result)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  const histogramTrace = result ? {
    x: result.histogram.bins.slice(0, -1),
    y: result.histogram.counts,
    type: 'bar',
    marker: { color: '#1677ff' },
    name: 'Histogram',
  } : undefined

  const cdfTrace = result ? {
    x: result.cdf_data.x,
    y: result.cdf_data.y,
    type: 'scatter',
    mode: 'lines',
    line: { color: '#722ed1' },
    name: 'CDF',
  } : undefined

  const capColor = (val: number) => (val >= 1.33 ? '#52c41a' : val >= 1.0 ? '#fa8c16' : '#ff4d4f')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card title={t('monteCarlo.title')}>
        <NodeSourceFilter
          section="monteCarlo"
          sourcedFromNode={sourcedFromNode}
          dataLoaded={dataSourceLoaded(sourcedFromNode?.dataSourceIds, importResult?.dataset_id)}
          columns={importResult?.columns ?? []}
          filterColumn={nodeFilterColumn}
          setFilterColumn={setNodeFilterColumn}
          filterValue={nodeFilterValue}
          setFilterValue={setNodeFilterValue}
          clearFilter={() => {
            setNodeFilterColumn(undefined)
            setNodeFilterValue(undefined)
          }}
        />
        <Space wrap style={{ marginBottom: 12 }}>
          <Form.Item label={t('monteCarlo.selectModel')} style={{ margin: 0 }}>
            <Select
              value={selectedModel}
              onChange={setSelectedModel}
              options={models.map(m => ({
                value: m.model_id,
                label: `${m.model_type} — ${m.equation.slice(0, 50)}...`,
              }))}
              disabled={models.length === 0}
              style={{ width: 320 }}
              placeholder={t('monteCarlo.noModels')}
            />
          </Form.Item>
          <Form.Item label={t('monteCarlo.nSimulations')} style={{ margin: 0 }}>
            <Input
              type="number"
              min={100}
              max={100000}
              value={nSimulations}
              onChange={e => setNSimulations(Number(e.target.value))}
              style={{ width: 100 }}
            />
          </Form.Item>
          <Form.Item label={t('monteCarlo.seed')} style={{ margin: 0 }}>
            <Input
              type="number"
              value={seed}
              onChange={e => setSeed(Number(e.target.value))}
              style={{ width: 80 }}
            />
          </Form.Item>
          <Form.Item label={t('monteCarlo.enableAnomalies')} style={{ margin: 0 }}>
            <Switch checked={enableAnomalies} onChange={setEnableAnomalies} />
          </Form.Item>
          <Button type="primary" onClick={handleRun} loading={loading} disabled={!importResult || !selectedModel}>
            {t('monteCarlo.runSimulation')}
          </Button>
        </Space>
        {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 12 }} />}
      </Card>

      {result && (
        <>
          <Row gutter={16}>
            <Col span={6}>
              <Card size="small" style={{ textAlign: 'center' }}>
                <Typography.Text type="secondary">{t('monteCarlo.ngProbability')}</Typography.Text>
                <Typography.Title level={3} style={{ margin: '8px 0', color: result.ng_probability > 0.05 ? '#ff4d4f' : result.ng_probability > 0.01 ? '#fa8c16' : '#52c41a' }}>
                  {(result.ng_probability * 100).toFixed(2)}%
                </Typography.Title>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {t('monteCarlo.ngCount')}: {result.ng_count} / {result.n_simulations}
                </Typography.Text>
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" style={{ textAlign: 'center' }}>
                <Typography.Text type="secondary">{t('monteCarlo.mean')}</Typography.Text>
                <Typography.Title level={4} style={{ margin: '8px 0' }}>{result.output_mean.toFixed(2)}</Typography.Title>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>σ = {result.output_std.toFixed(2)}</Typography.Text>
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" style={{ textAlign: 'center' }}>
                <Typography.Text type="secondary">{t('monteCarlo.median')}</Typography.Text>
                <Typography.Title level={4} style={{ margin: '8px 0' }}>{result.output_median.toFixed(2)}</Typography.Title>
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" style={{ textAlign: 'center' }}>
                <Typography.Text type="secondary">{t('monteCarlo.multiAnomalyNG')}</Typography.Text>
                <Typography.Title level={4} style={{ margin: '8px 0' }}>{result.multi_anomaly_ng}</Typography.Title>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {t('monteCarlo.totalSimulations')}: {result.n_simulations}
                </Typography.Text>
              </Card>
            </Col>
          </Row>

          <Row gutter={16}>
            {[
              { label: t('monteCarlo.p1'), value: result.percentiles.p1 },
              { label: t('monteCarlo.p5'), value: result.percentiles.p5 },
              { label: t('monteCarlo.p50'), value: result.percentiles.p50 },
              { label: t('monteCarlo.p95'), value: result.percentiles.p95 },
              { label: t('monteCarlo.p99'), value: result.percentiles.p99 },
            ].map(p => (
              <Col key={p.label} span={4}>
                <Card size="small" style={{ textAlign: 'center' }}>
                  <Typography.Text type="secondary" style={{ fontSize: 11 }}>{p.label}</Typography.Text>
                  <Typography.Text strong style={{ display: 'block' }}>{p.value.toFixed(2)}</Typography.Text>
                </Card>
              </Col>
            ))}
          </Row>

          {result.capability && result.capability.pp != null && result.capability.ppk != null && result.capability.sigma_overall != null && (
            <Card title={t('monteCarlo.predictedCapability')} size="small">
              <Row gutter={16}>
                <Col span={6}>
                  <Statistic
                    title={t('monteCarlo.pp')}
                    value={result.capability.pp}
                    precision={2}
                    valueStyle={{ color: capColor(result.capability.pp) }}
                  />
                </Col>
                <Col span={6}>
                  <Statistic
                    title={t('monteCarlo.ppk')}
                    value={result.capability.ppk}
                    precision={2}
                    valueStyle={{ color: capColor(result.capability.ppk) }}
                  />
                </Col>
                <Col span={12}>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {t('monteCarlo.sigmaOverall')}: {result.capability.sigma_overall.toFixed(2)}
                  </Typography.Text>
                </Col>
              </Row>
            </Card>
          )}

          <Card title={t('monteCarlo.outputDistribution')} size="small">
            <div style={{ display: 'flex', gap: 16, width: '100%' }}>
              <Plot
                data={[
                  histogramTrace,
                  ...(spec?.lsl != null ? [{
                    x: [spec.lsl, spec.lsl],
                    y: [0, Math.max(...((histogramTrace as any)?.y ?? [0])) * 1.1],
                    type: 'scatter',
                    mode: 'lines',
                    name: `LSL ${spec.lsl}`,
                    line: { color: '#ff4d4f', width: 1.5, dash: 'dash' },
                  }] : []),
                  ...(spec?.usl != null ? [{
                    x: [spec.usl, spec.usl],
                    y: [0, Math.max(...((histogramTrace as any)?.y ?? [0])) * 1.1],
                    type: 'scatter',
                    mode: 'lines',
                    name: `USL ${spec.usl}`,
                    line: { color: '#ff4d4f', width: 1.5, dash: 'dash' },
                  }] : []),
                  ...(spec?.target != null ? [{
                    x: [spec.target, spec.target],
                    y: [0, Math.max(...((histogramTrace as any)?.y ?? [0])) * 1.1],
                    type: 'scatter',
                    mode: 'lines',
                    name: `Target ${spec.target}`,
                    line: { color: '#52c41a', width: 1.5, dash: 'dot' },
                  }] : []),
                ].filter(Boolean)}
                layout={{
                  margin: { t: 30, b: 40, l: 50, r: 30 },
                  height: 280,
                  xaxis: { title: { text: 'Output Value' } },
                  yaxis: { title: { text: 'Count' } },
                }}
                config={{ responsive: true, displayModeBar: false }}
                style={{ flex: 1 }}
              />
              <Plot
                data={[
                  cdfTrace,
                  ...(spec?.lsl != null ? [{
                    x: [spec.lsl, spec.lsl],
                    y: [0, 1],
                    type: 'scatter',
                    mode: 'lines',
                    name: 'LSL',
                    line: { color: '#ff4d4f', width: 1.5, dash: 'dash' },
                  }] : []),
                  ...(spec?.usl != null ? [{
                    x: [spec.usl, spec.usl],
                    y: [0, 1],
                    type: 'scatter',
                    mode: 'lines',
                    name: 'USL',
                    line: { color: '#ff4d4f', width: 1.5, dash: 'dash' },
                  }] : []),
                  ...(spec?.target != null ? [{
                    x: [spec.target, spec.target],
                    y: [0, 1],
                    type: 'scatter',
                    mode: 'lines',
                    name: 'Target',
                    line: { color: '#52c41a', width: 1.5, dash: 'dot' },
                  }] : []),
                ].filter(Boolean)}
                layout={{
                  margin: { t: 30, b: 40, l: 50, r: 30 },
                  height: 280,
                  xaxis: { title: { text: 'Output Value' } },
                  yaxis: { title: { text: 'Cumulative Probability' } },
                }}
                config={{ responsive: true, displayModeBar: false }}
                style={{ flex: 1 }}
              />
            </div>
          </Card>

          {result.anomaly_rankings.length > 0 && (
            <Card title={`${t('monteCarlo.anomalyRankings')} (${result.anomaly_rankings.length})`} size="small">
              <Table
                dataSource={result.anomaly_rankings}
                columns={[
                  { title: 'ID', dataIndex: 'anomaly_id', key: 'anomaly_id', width: 100 },
                  { title: 'Name', dataIndex: 'name', key: 'name' },
                  { title: 'NG Contribution', dataIndex: 'ng_contribution', key: 'ng_contribution', width: 120,
                    render: (v: number) => <Tag color="error">{v}</Tag> },
                  { title: 'Probability', dataIndex: 'probability', key: 'probability', width: 100,
                    render: (v: number) => `${(v * 100).toFixed(1)}%` },
                ]}
                rowKey="anomaly_id"
                size="small"
                pagination={false}
              />
            </Card>
          )}
        </>
      )}

      {!result && importResult && (
        <Alert type="info" message={t('monteCarlo.selectModelFirst')} showIcon />
      )}
      {!importResult && (
        <Alert type="warning" message={t('monteCarlo.noData')} showIcon />
      )}
    </div>
  )
}
