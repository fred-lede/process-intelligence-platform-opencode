import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, Select, Space, Button, Alert, Spin, Empty, Tabs, Typography, Table, InputNumber, Form, Row, Col, Statistic, Tag } from 'antd'
import Plot from '../../components/PlotChart'
import { LineChartOutlined, BarChartOutlined, AreaChartOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import NodeSourceFilter from '../../components/NodeSourceFilter'
import {
  fitDistribution,
  getColumnSeries,
  getTimeSeriesFeatures,
  analyzeGRR,
  getFlowGraph,
  analyzeSPC,
  type DistributionFitResult,
  type ColumnSeries,
  type TimeSeriesFeatures,
  type GrrResult,
} from '../../lib/engine'
import { useDataPipelineStore } from '../../stores/dataPipelineStore'
import { useAssistantContextStore } from '../../stores/assistantContextStore'
import { useGuideContextStore } from '../../stores/guideContextStore'
import {
  consumeNodeContext,
  dataSourceLoaded,
  findNodeById,
} from '../../lib/processFlowContext'
import { buildExplorationContext } from '../../lib/assistantData'

function densityBars(fit: DistributionFitResult) {
  const edges = fit.histogram.edges
  const counts = fit.histogram.counts
  const total = counts.reduce((a, b) => a + b, 0)
  const x: number[] = []
  const widths: number[] = []
  const y: number[] = []
  for (let i = 0; i < counts.length && i + 1 < edges.length; i++) {
    const w = edges[i + 1] - edges[i]
    if (w <= 0) continue
    x.push((edges[i] + edges[i + 1]) / 2)
    widths.push(w)
    y.push(total > 0 ? counts[i] / (total * w) : 0)
  }
  return { x, y, widths }
}

const FIT_COLORS = ['#1677ff', '#722ed1', '#fa8c16']

export default function Exploration() {
  const { t } = useTranslation()
  const { importResult, fields, spec, controlLimits } = useDataPipelineStore()
  const { setContext } = useAssistantContextStore()
  const consumedRef = useRef(false)
  const [sourcedFromNode, setSourcedFromNode] = useState<{
    nodeId: string
    displayName: string
    dataSourceIds?: string[]
  } | null>(null)
  const [nodeFilterColumn, setNodeFilterColumn] = useState<string | undefined>(undefined)
  const [nodeFilterValue, setNodeFilterValue] = useState<string | undefined>(undefined)
  const [column, setColumn] = useState<string | undefined>(spec?.outputField)
  const [trendColumn, setTrendColumn] = useState<string | undefined>(spec?.outputField)
  const [loading, setLoading] = useState(false)
  const [fits, setFits] = useState<DistributionFitResult[] | null>(null)
  const [series, setSeries] = useState<ColumnSeries | null>(null)
  const [trendCtrl, setTrendCtrl] = useState<{ ucl?: number; lcl?: number } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tsFeatures, setTsFeatures] = useState<TimeSeriesFeatures | null>(null)
  const [tsLoading, setTsLoading] = useState(false)
  const [tsColumn, setTsColumn] = useState<string | undefined>(spec?.outputField)
  const [timeColumn, setTimeColumn] = useState<string | undefined>()
  const [windowSizes, setWindowSizes] = useState<number[]>([3, 5, 10])
  const [grrResult, setGrrResult] = useState<GrrResult | null>(null)
  const [grrLoading, setGrrLoading] = useState(false)
  const [grrMeasurementCol, setGrrMeasurementCol] = useState<string | undefined>()
  const [grrPartCol, setGrrPartCol] = useState<string | undefined>()
  const [grrOperatorCol, setGrrOperatorCol] = useState<string | undefined>()
  const [activeTab, setActiveTab] = useState('distribution')
  const setGuideSubtab = useGuideContextStore((s) => s.setSubtab)
  useEffect(() => { setGuideSubtab(activeTab); return () => setGuideSubtab(undefined) }, [activeTab, setGuideSubtab])

  const numericColumns = useMemo(() => {
    if (!importResult) return []
    const stats = importResult.stats.column_stats
    return Object.entries(stats)
      .filter(([, s]) => s.numeric)
      .map(([name]) => name)
  }, [importResult])

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
          if (pendingCtx.field && numericColumns.includes(pendingCtx.field)) {
            setColumn(pendingCtx.field)
            setTrendColumn(pendingCtx.field)
          }
          try {
            const graph = await getFlowGraph()
            const key = graph.association_keys[0]
            if (key && (importResult?.columns ?? []).includes(key)) {
              setNodeFilterColumn(key)
            }
          } catch {
            // ignore — filter default is optional
          }
        }
      })()
    }
  }, [])

  const timestampColumns = useMemo(() => {
    const fromRoles = fields
      .filter((f) => f.role === 'timestamp')
      .map((f) => f.originalName)
    if (fromRoles.length > 0) return fromRoles
    return (importResult?.columns || []).filter(
      (c) => !numericColumns.includes(c),
    )
  }, [fields, importResult, numericColumns])

  const confirmedInputs = useMemo(
    () => new Set(fields.filter((f) => f.confirmed).map((f) => f.originalName)),
    [fields],
  )
  const confirmedOutputs = useMemo(
    () => new Set(fields.filter((f) => f.confirmed && f.role === 'output').map((f) => f.originalName)),
    [fields],
  )

  useEffect(() => {
    if (!timeColumn && timestampColumns.length > 0) {
      setTimeColumn(timestampColumns[0])
    }
  }, [timeColumn, timestampColumns])

  useEffect(() => {
    if (numericColumns.length === 0) return
    if (tsColumn && !numericColumns.includes(tsColumn)) {
      setTsColumn(numericColumns[0])
    }
    if (trendColumn && !numericColumns.includes(trendColumn)) {
      setTrendColumn(numericColumns[0])
    }
  }, [tsColumn, trendColumn, numericColumns])


  useEffect(() => {
    setContext('exploration', buildExplorationContext({
      fits: activeTab === 'distribution' ? fits : null,
      series: activeTab === 'trend' ? series : null,
      tsFeatures: activeTab === 'timeseries' ? tsFeatures : null,
      grrResult: activeTab === 'grr' ? grrResult : null,
      filterColumn: nodeFilterColumn,
      filterValue: nodeFilterValue,
      trendControlLimits: activeTab === 'trend' ? trendCtrl ?? undefined : undefined,
      timeSeriesColumn: activeTab === 'timeseries' ? tsColumn : undefined,
      timeSeriesTimeColumn: activeTab === 'timeseries' ? timeColumn : undefined,
      grrMeasurementColumn: activeTab === 'grr' ? grrMeasurementCol : undefined,
      grrPartColumn: activeTab === 'grr' ? grrPartCol : undefined,
      grrOperatorColumn: activeTab === 'grr' ? grrOperatorCol : undefined,
    }))
  }, [activeTab, fits, series, tsFeatures, timeColumn, tsColumn, grrResult, grrMeasurementCol, grrPartCol, grrOperatorCol, nodeFilterColumn, nodeFilterValue, setContext])

  const filterArgs =
    nodeFilterColumn && nodeFilterValue
      ? { filter_column: nodeFilterColumn, filter_value: nodeFilterValue }
      : {}

  const loadFits = async () => {
    if (!importResult || !column) return
    setLoading(true)
    setError(null)
    try {
      const result = await fitDistribution(importResult.dataset_id, column, 3, filterArgs)
      setFits(result.fits)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  const loadTrend = async () => {
    if (!importResult || !trendColumn) return
    setLoading(true)
    setError(null)
    try {
      const [seriesRes, spcRes] = await Promise.all([
        getColumnSeries(importResult.dataset_id, trendColumn, filterArgs),
        analyzeSPC({ dataset_id: importResult.dataset_id, column: trendColumn, control_limits: controlLimits[trendColumn] ?? undefined }),
      ])
      setSeries(seriesRes)
      if (spcRes.control_limits) {
        const cl = spcRes.control_limits
        setTrendCtrl({ ucl: cl.i_ucl ?? cl.x_ucl, lcl: cl.i_lcl ?? cl.x_lcl })
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (column && importResult) void loadFits()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [importResult?.dataset_id])

  const scatterData = useMemo(() => {
    if (!series || !series.numeric) return null
    const ys = series.values as (number | null)[]
    return {
      x: ys.map((_, i) => i + 1),
      y: ys,
    }
  }, [series])

  const trendInsights = useMemo(() => {
    if (!scatterData?.y.length) return null
    const values = scatterData.y.filter((v): v is number => v != null)
    if (!values.length) return null
    const first = values[0]
    const last = values[values.length - 1]
    const delta = last - first
    let direction: 'up' | 'down' | 'flat' = Math.abs(delta) < 1e-12 ? 'flat' : delta > 0 ? 'up' : 'down'
    let longestRun = 1
    let run = 1
    for (let i = 1; i < values.length; i += 1) {
      const step = values[i] - values[i - 1]
      const prevStep = values[i - 1] - values[i - 2]
      if (i > 1 && step !== 0 && prevStep !== 0 && Math.sign(step) === Math.sign(prevStep)) run += 1
      else run = 1
      longestRun = Math.max(longestRun, run)
    }
    const ucl = trendCtrl?.ucl
    const lcl = trendCtrl?.lcl
    const beyond = values.filter(v => (ucl != null && v > ucl) || (lcl != null && v < lcl)).length
    return { direction, delta, longestRun, beyond, ucl, lcl }
  }, [scatterData, trendCtrl])

  const fitColumns: ColumnsType<DistributionFitResult> = [
    {
      title: t('exploration.fitName'),
      dataIndex: 'name',
      key: 'name',
      render: (name: string) => <Typography.Text strong>{name}</Typography.Text>,
    },
    { title: 'AIC', dataIndex: 'aic', key: 'aic', width: 110 },
    { title: 'BIC', dataIndex: 'bic', key: 'bic', width: 110 },
    {
      title: 'KS p-value',
      dataIndex: 'ks_p_value',
      key: 'ks_p_value',
      width: 120,
      render: (p: number) => p.toFixed(4),
    },
    {
      title: t('exploration.params'),
      dataIndex: 'params',
      key: 'params',
      render: (params: Record<string, number>) => (
        <Typography.Text code>
          {Object.entries(params)
            .map(([k, v]) => `${k}=${Number(v).toFixed(4)}`)
            .join(', ')}
        </Typography.Text>
      ),
    },
  ]

  if (!importResult) {
    return (
      <Card title={t('exploration.title')}>
        <NodeSourceFilter
          section="exploration"
          sourcedFromNode={sourcedFromNode}
          dataLoaded={false}
          columns={[]}
          filterColumn={nodeFilterColumn}
          setFilterColumn={setNodeFilterColumn}
          filterValue={nodeFilterValue}
          setFilterValue={setNodeFilterValue}
          clearFilter={() => {
            setNodeFilterColumn(undefined)
            setNodeFilterValue(undefined)
          }}
        />
        <Empty description={t('exploration.noData')} />
      </Card>
    )
  }

  const distributionTab = (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Space wrap>
        <Select
          style={{ width: 240 }}
          placeholder={t('exploration.selectColumn')}
          value={column}
          onChange={(v) => {
            setColumn(v)
            setFits(null)
          }}
          options={numericColumns.map((name) => ({ value: name, label: name }))}
        />
        <Button
          type="primary"
          icon={<BarChartOutlined />}
          loading={loading}
          onClick={() => void loadFits()}
        >
          {t('exploration.fitDistribution')}
        </Button>
      </Space>

      {error && <Alert type="error" showIcon message={error} />}

      {loading && !fits && <Spin />}

      {fits && fits.length > 0 ? (
        <>
          <Card size="small" title={t('exploration.chartTitle')}>
            <Plot
              data={[
                ...fits.map((fit, i) => ({
                  x: fit.pdf.x,
                  y: fit.pdf.y,
                  type: 'scatter' as const,
                  mode: 'lines',
                  name: `${fit.name} (AIC ${fit.aic.toFixed(1)})`,
                  line: { width: 2, color: FIT_COLORS[i % FIT_COLORS.length] },
                  yaxis: 'y',
                })),
                ...fits.slice(0, 1).map((fit) => {
                  const bars = densityBars(fit)
                  return {
                    x: bars.x,
                    y: bars.y,
                    type: 'bar' as const,
                    width: bars.widths,
                    name: t('exploration.histogram'),
                    marker: { color: 'rgba(22,119,255,0.25)' },
                  }
                }),
              ]}
              layout={{
                title: { text: column },
                xaxis: { title: { text: t('exploration.valueAxis') } },
                yaxis: { title: { text: t('exploration.densityAxis') }, rangemode: 'tozero' },
                height: 420,
                margin: { l: 60, r: 20, t: 60, b: 60 },
                legend: { orientation: 'h', y: -0.2 },
              }}
              useResizeHandler
              style={{ width: '100%' }}
              config={{ responsive: true }}
            />
          </Card>

          <Table
            size="small"
            rowKey="name"
            columns={fitColumns}
            dataSource={fits}
            pagination={false}
          />
          <Alert
            type="info"
            showIcon
            message={t('exploration.bestFitSummary', { column, distribution: fits[0].name, n: fits[0].histogram.counts.reduce((a, b) => a + b, 0) })}
            description={t('exploration.bestFitReason', {
              aic: fits[0].aic.toFixed(2),
              bic: fits[0].bic.toFixed(2),
              p: fits[0].ks_p_value.toFixed(4),
              params: Object.entries(fits[0].params).map(([k, v]) => `${k}=${Number(v).toFixed(4)}`).join(', '),
              compared: fits.slice(1).map(f => `${f.name} AIC=${f.aic.toFixed(2)}, BIC=${f.bic.toFixed(2)}`).join('; ') || '—',
            })}
          />
        </>
      ) : (
        !loading && <Empty description={t('exploration.noFit')} />
      )}
    </Space>
  )

  const trendTab = (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Space wrap>
        <Select
          style={{ width: 240 }}
          placeholder={t('exploration.selectColumn')}
          value={trendColumn}
          onChange={(v) => {
            setTrendColumn(v)
            setSeries(null)
          }}
          options={numericColumns
            .filter((name) => confirmedInputs.has(name) || confirmedOutputs.has(name))
            .map((name) => ({ value: name, label: name }))}
        />
        <Button
          type="primary"
          icon={<LineChartOutlined />}
          loading={loading}
          onClick={() => void loadTrend()}
        >
          {t('exploration.drawTrend')}
        </Button>
      </Space>

      {error && <Alert type="error" showIcon message={error} />}

      {scatterData ? (
        <>
        <Card size="small" title={t('exploration.trendChartTitle')}>
          <Plot
            data={[
              {
                x: scatterData.x,
                y: scatterData.y,
                type: 'scatter' as const,
                mode: 'lines+markers',
                name: trendColumn,
                line: { width: 1.5 },
                marker: { size: 4 },
              },
              ...(trendCtrl?.ucl != null ? [{
                x: scatterData.x,
                y: scatterData.x.map(() => trendCtrl.ucl!),
                type: 'scatter' as const,
                mode: 'lines',
                name: 'UCL',
                line: { dash: 'dash' as const, color: '#fa8c16' },
              }] : []),
              ...(trendCtrl?.lcl != null ? [{
                x: scatterData.x,
                y: scatterData.x.map(() => trendCtrl.lcl!),
                type: 'scatter' as const,
                mode: 'lines',
                name: 'LCL',
                line: { dash: 'dash' as const, color: '#fa8c16' },
              }] : []),
              ...(spec && trendColumn === spec.outputField
                ? [spec.lsl, spec.usl]
                    .filter((v): v is number => v != null)
                    .map((v, i) => ({
                      x: scatterData.x,
                      y: scatterData.x.map(() => v),
                      type: 'scatter' as const,
                      mode: 'lines',
                      name: i === 0 ? `LSL ${v}` : `USL ${v}`,
                      line: { dash: 'dash' as const, color: i === 0 ? '#f5222d' : '#fa8c16' },
                    }))
                : []),
            ]}
            layout={{
              title: { text: trendColumn },
              xaxis: { title: { text: t('exploration.rowAxis') } },
              yaxis: { title: { text: trendColumn }, rangemode: 'tozero' },
              height: 400,
              margin: { l: 60, r: 20, t: 60, b: 60 },
              legend: { orientation: 'h', y: -0.2 },
            }}
            useResizeHandler
            style={{ width: '100%' }}
            config={{ responsive: true }}
          />
        </Card>
        {trendInsights && <Alert type="info" showIcon message={t('exploration.trendSummary', { column: trendColumn, count: scatterData.y.length, first: scatterData.y[0]?.toFixed(4), last: scatterData.y[scatterData.y.length - 1]?.toFixed(4), delta: trendInsights.delta.toFixed(4), direction: t(`exploration.trendDirection.${trendInsights.direction}`), run: trendInsights.longestRun, beyond: trendInsights.beyond })} description={t('exploration.trendAdvice', { direction: t(`exploration.trendDirection.${trendInsights.direction}`), run: trendInsights.longestRun, beyond: trendInsights.beyond })} />}
        </>
      ) : (
        !loading && <Empty description={t('exploration.noTrend')} />
      )}
    </Space>
  )

  // --- Time Series Features Tab ---
  const timeSeriesTab = (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Form layout="inline" style={{ marginBottom: 8 }}>
        <Form.Item label={t('exploration.timeColumn')}>
          <Select
            style={{ width: 180 }}
            value={timeColumn}
            onChange={setTimeColumn}
            options={timestampColumns.map((c) => ({ value: c, label: c }))}
            placeholder={t('exploration.selectTimeCol')}
          />
        </Form.Item>
        <Form.Item label={t('exploration.valueColumn')}>
          <Select
            style={{ width: 180 }}
            value={tsColumn}
            onChange={setTsColumn}
            options={numericColumns.map((name) => ({ value: name, label: name }))}
            placeholder={t('exploration.selectColumn')}
          />
        </Form.Item>
        <Form.Item label={t('exploration.windowSizes')}>
          <InputNumber
            value={windowSizes[0]}
            onChange={(v) => v !== null && setWindowSizes([v, 5, 10])}
            min={2}
            max={20}
            style={{ width: 60 }}
          />
          <span style={{ margin: '0 4px' }}>,</span>
          <InputNumber
            value={windowSizes[1]}
            onChange={(v) => v !== null && setWindowSizes([windowSizes[0], v, 10])}
            min={2}
            max={20}
            style={{ width: 60 }}
          />
          <span style={{ margin: '0 4px' }}>,</span>
          <InputNumber
            value={windowSizes[2]}
            onChange={(v) => v !== null && setWindowSizes([windowSizes[0], windowSizes[1], v])}
            min={2}
            max={20}
            style={{ width: 60 }}
          />
        </Form.Item>
        <Form.Item>
          <Button
            type="primary"
            icon={<AreaChartOutlined />}
            loading={tsLoading}
            disabled={!timeColumn || !tsColumn || !importResult}
            onClick={async () => {
              if (!importResult || !timeColumn || !tsColumn) return
              if (!numericColumns.includes(tsColumn)) {
                setError(t('exploration.valueColNotNumeric'))
                return
              }
              setTsLoading(true)
              try {
                const result = await getTimeSeriesFeatures({
                  dataset_id: importResult.dataset_id,
                  time_column: timeColumn,
                  value_columns: [tsColumn],
                  window_sizes: windowSizes,
                  ...filterArgs,
                })
                setTsFeatures(result)
              } catch (err) {
                setError(err instanceof Error ? err.message : String(err))
              } finally {
                setTsLoading(false)
              }
            }}
          >
            {t('exploration.computeFeatures')}
          </Button>
        </Form.Item>
      </Form>

      {error && <Alert type="error" showIcon message={error} />}

      {tsFeatures ? (
        <>
          <Space style={{ marginBottom: 8 }}>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t('exploration.totalFeatures')}: <strong>{tsFeatures.n_features}</strong>
            </Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t('exploration.featureColumns')}: {tsFeatures.feature_columns.join(', ')}
            </Typography.Text>
          </Space>
          <Plot
            data={(() => {
              const traces: any[] = []
              if (tsFeatures.preview.length > 0) {
                const baseCol = tsColumn!
                const baseValues = tsFeatures.preview.map((r: Record<string, unknown>) => r[baseCol] as number)
                traces.push({
                  x: baseValues.map((_, i) => i),
                  y: baseValues,
                  type: 'scatter' as const,
                  mode: 'lines+markers' as const,
                  name: baseCol,
                  line: { width: 1.5 },
                  marker: { size: 3 },
                })
                for (const feat of tsFeatures.feature_columns) {
                  if (feat === baseCol) continue
                  const pts = tsFeatures.preview
                    .map((r: Record<string, unknown>, i: number) => ({
                      i,
                      v: r[feat] as number | null,
                    }))
                    .filter((p) => p.v !== null && p.v !== undefined)
                  if (pts.length === 0) continue
                  traces.push({
                    x: pts.map((p) => p.i),
                    y: pts.map((p) => p.v as number),
                    type: 'scatter' as const,
                    mode: 'lines' as const,
                    name: feat,
                    line: { width: 1, dash: 'dot' },
                    opacity: 0.7,
                  })
                }
              }
              return traces
            })()}
            layout={{
              title: { text: `${tsColumn} + Features` },
              xaxis: { title: { text: 'Row index' } },
              yaxis: { title: { text: tsColumn ?? '' } },
              height: 350,
              margin: { l: 60, r: 20, t: 60, b: 40 },
              legend: { orientation: 'h', y: -0.25 },
            }}
            useResizeHandler
            style={{ width: '100%' }}
            config={{ responsive: true }}
          />
          <Table
            size="small"
            dataSource={tsFeatures.preview}
            columns={[
              ...([timeColumn] as string[])
                .filter(Boolean)
                .map((c) => ({ title: c, dataIndex: c, key: c, width: 150 })),
              ...([tsColumn] as string[])
                .filter(Boolean)
                .map((c) => ({
                  title: c,
                  dataIndex: c,
                  key: c,
                  width: 110,
                  render: (v: number) => v?.toFixed(4),
                })),
              ...tsFeatures.feature_columns.map((c) => ({
                title: c,
                dataIndex: c,
                key: c,
                width: 120,
                render: (v: number | null) => (v == null ? '—' : v.toFixed(4)),
              })),
            ]}
            scroll={{ x: 'max-content' }}
            pagination={{ pageSize: 10, showSizeChanger: false }}
            rowKey={(r) => String(r[timeColumn ?? ''])}
          />
          <Alert type="info" showIcon message={t('exploration.timeSeriesSummary', { column: tsColumn, features: tsFeatures.n_features, rows: tsFeatures.preview.length })} description={t('exploration.timeSeriesAdvice', { time: timeColumn || '—', windows: '3, 5, 10' })} />
        </>
      ) : (
        !tsLoading && <Empty description={t('exploration.noTsData')} />
      )}
    </Space>
  )

  // --- GRR Tab ---
  const grrTab = (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Alert type="info" showIcon message={t('grr.noData')} style={{ marginBottom: 8 }} />
      <Form layout="inline">
        <Form.Item label={t('grr.measurementColumn')}>
          <Select
            style={{ width: 180 }}
            value={grrMeasurementCol}
            onChange={setGrrMeasurementCol}
            options={numericColumns.map((n) => ({ value: n, label: n }))}
            placeholder={t('exploration.selectColumn')}
          />
        </Form.Item>
        <Form.Item label={t('grr.partColumn')}>
          <Select
            style={{ width: 180 }}
            value={grrPartCol}
            onChange={setGrrPartCol}
            options={(importResult?.columns || []).map((c) => ({ value: c, label: c }))}
            placeholder={t('exploration.selectColumn')}
          />
        </Form.Item>
        <Form.Item label={t('grr.operatorColumn')}>
          <Select
            style={{ width: 180 }}
            value={grrOperatorCol}
            onChange={setGrrOperatorCol}
            options={(importResult?.columns || []).map((c) => ({ value: c, label: c }))}
            placeholder={t('exploration.selectColumn')}
          />
        </Form.Item>
        <Form.Item>
          <Button
            type="primary"
            icon={<BarChartOutlined />}
            loading={grrLoading}
            disabled={!grrMeasurementCol || !grrPartCol || !grrOperatorCol || !importResult}
            onClick={async () => {
              if (!importResult || !grrMeasurementCol || !grrPartCol || !grrOperatorCol) return
              setGrrLoading(true)
              setError(null)
              setGrrResult(null)
              try {
                const result = await analyzeGRR({
                  dataset_id: importResult.dataset_id,
                  measurement_column: grrMeasurementCol,
                  part_column: grrPartCol,
                  operator_column: grrOperatorCol,
                })
                setGrrResult(result)
              } catch (err) {
                setError(err instanceof Error ? err.message : String(err))
              } finally {
                setGrrLoading(false)
              }
            }}
          >
            {t('grr.analyze')}
          </Button>
        </Form.Item>
      </Form>

      {error && <Alert type="error" showIcon message={error} />}

      {grrResult ? (
        <Space direction="vertical" style={{ width: '100%' }} size={8}>
          <Row gutter={[16, 16]}>
            <Col span={6}>
              <Statistic
                title={t('grr.verdict')}
                value={t(`grr.${grrResult.verdict}`)}
                valueStyle={{ color: grrResult.verdict === 'acceptable' ? '#16a34a' : grrResult.verdict === 'marginal' ? '#ca8a04' : '#dc2626' }}
                suffix={<Tag color={grrResult.verdict === 'acceptable' ? 'success' : grrResult.verdict === 'marginal' ? 'warning' : 'error'}>{grrResult.pct_grr.toFixed(1)}%</Tag>}
              />
            </Col>
            <Col span={6}>
              <Statistic title={t('grr.pctGRR')} value={grrResult.pct_grr.toFixed(2)} suffix="%" />
            </Col>
            <Col span={6}>
              <Statistic title={t('grr.pctPart')} value={grrResult.pct_part.toFixed(2)} suffix="%" />
            </Col>
            <Col span={6}>
              <Statistic
                title={t('grr.GRR')}
                value={grrResult.grr_std.toFixed(6)}
                suffix={`EV:${grrResult.repeatability_std.toFixed(4)} AV:${grrResult.reproducibility_std.toFixed(4)}`}
              />
            </Col>
          </Row>
          <Row gutter={[16, 16]}>
            <Col span={8}>
              <Statistic title={t('grr.nParts')} value={grrResult.n_parts} />
            </Col>
            <Col span={8}>
              <Statistic title={t('grr.nOperators')} value={grrResult.n_operators} />
            </Col>
            <Col span={8}>
              <Statistic title={t('grr.nReps')} value={grrResult.n_reps} />
            </Col>
          </Row>
          {grrResult.warnings.length > 0 && (
            <Alert
              type="warning"
              showIcon
              message={t('grr.warnings')}
              description={grrResult.warnings.map((w, i) => <div key={i} style={{ fontSize: 12 }}>{w.includes('Repeatability (equipment variation) dominates') ? t('grr.repeatabilityWarning') : w.includes('Reproducibility (operator variation) is significant') ? t('grr.reproducibilityWarning') : w}</div>)}
            />
          )}
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>{(() => {
            const pctText = grrResult.pct_grr.toFixed(1)
            if (grrResult.verdict === 'acceptable') return t('grr.reasonAcceptable', { pct: pctText })
            if (grrResult.verdict === 'marginal') return t('grr.reasonMarginal', { pct: pctText })
            return t('grr.reasonUnacceptable', { pct: pctText })
          })()}</Typography.Text>
          <Alert type="info" showIcon message={t('grr.summaryTitle')} description={t('grr.summaryAdvice', { pct: grrResult.pct_grr.toFixed(1), part: grrResult.pct_part.toFixed(1), repeatability: grrResult.repeatability_std.toFixed(4), reproducibility: grrResult.reproducibility_std.toFixed(4) })} />
        </Space>
      ) : null}
    </Space>
  )

  return (
    <Card title={t('exploration.title')}>
      <NodeSourceFilter
        section="exploration"
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
        filterable={activeTab === 'distribution' || activeTab === 'trend'}
      />
      {nodeFilterColumn && nodeFilterValue && series && (
        <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
          篩選後樣本數：{series.values.length}
        </Typography.Text>
      )}
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          { key: 'distribution', label: t('exploration.distributionTab'), children: distributionTab },
          { key: 'trend', label: t('exploration.trendTab'), children: trendTab },
          { key: 'timeseries', label: t('exploration.timeSeriesTab'), children: timeSeriesTab },
          { key: 'grr', label: t('grr.title'), children: grrTab },
        ]}
      />
    </Card>
  )
}
