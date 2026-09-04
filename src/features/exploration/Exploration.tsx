import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, Select, Space, Button, Alert, Spin, Empty, Tabs, Typography, Table, InputNumber, Form, Row, Col, Statistic, Tag } from 'antd'
import Plot from 'react-plotly.js'
import { LineChartOutlined, BarChartOutlined, AreaChartOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  fitDistribution,
  getColumnSeries,
  getTimeSeriesFeatures,
  analyzeGRR,
  type DistributionFitResult,
  type ColumnSeries,
  type TimeSeriesFeatures,
  type GrrResult,
} from '../../lib/engine'
import { useDataPipelineStore } from '../../stores/dataPipelineStore'
import { useAssistantContextStore } from '../../stores/assistantContextStore'
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
  const { importResult, fields, spec } = useDataPipelineStore()
  const { setContext } = useAssistantContextStore()
  const [column, setColumn] = useState<string | undefined>(spec?.outputField)
  const [trendColumn, setTrendColumn] = useState<string | undefined>(spec?.outputField)
  const [loading, setLoading] = useState(false)
  const [fits, setFits] = useState<DistributionFitResult[] | null>(null)
  const [series, setSeries] = useState<ColumnSeries | null>(null)
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

  const numericColumns = useMemo(() => {
    if (!importResult) return []
    const stats = importResult.stats.column_stats
    return Object.entries(stats)
      .filter(([, s]) => s.numeric)
      .map(([name]) => name)
  }, [importResult])

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

  useEffect(() => {
    if (!timeColumn && timestampColumns.length > 0) {
      setTimeColumn(timestampColumns[0])
    }
  }, [timeColumn, timestampColumns])

  useEffect(() => {
    setContext('exploration', buildExplorationContext({ fits, series, tsFeatures, grrResult }))
  }, [fits, series, tsFeatures, grrResult, setContext])

  const loadFits = async () => {
    if (!importResult || !column) return
    setLoading(true)
    setError(null)
    try {
      const result = await fitDistribution(importResult.dataset_id, column)
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
      const result = await getColumnSeries(importResult.dataset_id, trendColumn)
      setSeries(result)
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
            .filter((name) => confirmedInputs.has(name) || name === spec?.outputField)
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
              setTsLoading(true)
              try {
                const result = await getTimeSeriesFeatures({
                  dataset_id: importResult.dataset_id,
                  time_column: timeColumn,
                  value_columns: [tsColumn],
                  window_sizes: windowSizes,
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
                  const vals = tsFeatures.preview.map((r: Record<string, unknown>) => r[feat] as number | null)
                  const nonNull = vals.filter((v): v is number => v !== null && v !== undefined)
                  if (nonNull.length === 0) continue
                  traces.push({
                    x: nonNull.map((_, i) => i),
                    y: nonNull,
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
            columns={tsFeatures.feature_columns.slice(0, 6).map((c) => ({
              title: c,
              dataIndex: c,
              key: c,
              render: (v: number) => v?.toFixed(4),
            }))}
            pagination={{ pageSize: 10 }}
            rowKey={(r) => String(r[timeColumn ?? ''])}
          />
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
              description={grrResult.warnings.map((w, i) => <div key={i} style={{ fontSize: 12 }}>{w}</div>)}
            />
          )}
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>{grrResult.verdict_reason}</Typography.Text>
        </Space>
      ) : null}
    </Space>
  )

  return (
    <Card title={t('exploration.title')}>
      <Tabs
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