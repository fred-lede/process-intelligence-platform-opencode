import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, Select, Space, Button, Alert, Spin, Empty, Tabs, Typography, Table } from 'antd'
import Plot from 'react-plotly.js'
import { LineChartOutlined, BarChartOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  fitDistribution,
  getColumnSeries,
  type DistributionFitResult,
  type ColumnSeries,
} from '../../lib/engine'
import { useDataPipelineStore } from '../../stores/dataPipelineStore'

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
  const [column, setColumn] = useState<string | undefined>(spec?.outputField)
  const [trendColumn, setTrendColumn] = useState<string | undefined>(spec?.outputField)
  const [loading, setLoading] = useState(false)
  const [fits, setFits] = useState<DistributionFitResult[] | null>(null)
  const [series, setSeries] = useState<ColumnSeries | null>(null)
  const [error, setError] = useState<string | null>(null)

  const numericColumns = useMemo(() => {
    if (!importResult) return []
    const stats = importResult.stats.column_stats
    return Object.entries(stats)
      .filter(([, s]) => s.numeric)
      .map(([name]) => name)
  }, [importResult])

  const confirmedInputs = useMemo(
    () => new Set(fields.filter((f) => f.confirmed).map((f) => f.originalName)),
    [fields],
  )

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

  return (
    <Card title={t('exploration.title')}>
      <Tabs
        items={[
          { key: 'distribution', label: t('exploration.distributionTab'), children: distributionTab },
          { key: 'trend', label: t('exploration.trendTab'), children: trendTab },
        ]}
      />
    </Card>
  )
}