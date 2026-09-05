import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, Select, Space, Button, Alert, Form, Input, Typography, Table, Tag } from 'antd'
import Plot from 'react-plotly.js'
import NodeSourceFilter from '../../components/NodeSourceFilter'
import { useDataPipelineStore } from '../../stores/dataPipelineStore'
import { useAssistantContextStore } from '../../stores/assistantContextStore'
import { analyzeSPC, getFlowGraph, type SPCAnalysisResult } from '../../lib/engine'
import {
  consumeNodeContext,
  dataSourceLoaded,
  findNodeById,
} from '../../lib/processFlowContext'
import { buildSpcContext } from '../../lib/assistantData'

const CHART_TYPES = ['i-mr', 'xbar-r', 'xbar-s'] as const
type ChartType = typeof CHART_TYPES[number]

const WE_RULE_NAMES: Record<number, string> = {
  1: 'Rule 1: 1 point beyond 3σ',
  2: 'Rule 2: 2 of 3 points beyond 2σ',
  3: 'Rule 3: 4 of 5 points beyond 1σ',
  4: 'Rule 4: 8 points in a row on one side',
  5: 'Rule 5: 6 points in a row trending',
  6: 'Rule 6: 15 points in a row within ±1σ',
  7: 'Rule 7: 14 points in a row alternating',
}

export default function SPC() {
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
          const numericFields = new Set(
            Object.entries(importResult?.stats.column_stats ?? {})
              .filter(([, s]) => s.numeric)
              .map(([name]) => name),
          )
          if (pendingCtx.field && numericFields.has(pendingCtx.field)) {
            setColumn(pendingCtx.field)
          }
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

  const [chartType, setChartType] = useState<ChartType>('i-mr')
  const [column, setColumn] = useState<string | undefined>(spec?.outputField)
  const [subgroupSize, setSubgroupSize] = useState<number>(5)
  const [result, setResult] = useState<SPCAnalysisResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [numericColumns, setNumericColumns] = useState<string[]>([])

  useEffect(() => {
    if (!importResult) return
    const stats = importResult.stats.column_stats
    const cols = Object.entries(stats)
      .filter(([, s]) => s.numeric)
      .map(([name]) => name)
    setNumericColumns(cols)
  }, [importResult])

  useEffect(() => {
    setContext('spc', buildSpcContext(result))
  }, [result, setContext])

  const handleAnalyze = async () => {
    if (!importResult || !column) return
    setLoading(true)
    setError(null)
    try {
      const res = await analyzeSPC({
        dataset_id: importResult.dataset_id,
        column,
        chart_type: chartType,
        subgroup_size: chartType === 'i-mr' ? 1 : subgroupSize,
        lsl: spec?.lsl ?? undefined,
        usl: spec?.usl ?? undefined,
        ...(nodeFilterColumn && nodeFilterValue
          ? { filter_column: nodeFilterColumn, filter_value: nodeFilterValue }
          : {}),
      })
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  const capacityColor = (val: number | null) => {
    if (val === null) return 'default'
    if (val >= 1.33) return 'success'
    if (val >= 1.0) return 'warning'
    return 'error'
  }

  const capacityLabel = (val: number | null) => {
    if (val === null) return 'N/A'
    if (val >= 1.33) return t('spc.capacityGood')
    if (val >= 1.0) return t('spc.capacityAcceptable')
    return t('spc.capacityPoor')
  }

  const buildPlotData = () => {
    if (!result) return []
    const cl = result.control_limits
    const data: any[] = []

    const addSpecLines = (ref = false) => {
      const xs = (result.chart_type === 'i-mr'
        ? result.x_values?.map((_, i) => i)
        : result.xbar_values?.map((_, i) => i)) ?? []
      if (xs.length === 0) return
      const push = (v: number | null | undefined, name: string) => {
        if (v == null) return
        data.push({
          x: [xs[0], xs[xs.length - 1]], y: [v, v],
          mode: 'lines', name: ref ? `${name} (ref)` : name,
          line: { color: '#f5222d', width: 1.5 },
        })
      }
      push(spec?.lsl ?? null, 'LSL')
      push(spec?.usl ?? null, 'USL')
    }

    if (result.chart_type === 'i-mr') {
      const x = result.x_values?.map((_, i) => i) ?? []
      data.push({
        x, y: result.x_values ?? [], mode: 'lines+markers',
        name: 'Individuals', line: { color: '#1677ff' }, marker: { size: 6 },
      })
      if (cl.i_ucl != null && x.length > 0) {
        data.push({ x: [x[0], x[x.length - 1]], y: [cl.i_ucl, cl.i_ucl],
          mode: 'lines', name: 'UCL', line: { color: '#fa8c16', dash: 'dash' }, showlegend: false })
      }
      if (cl.i_lcl != null && x.length > 0) {
        data.push({ x: [x[0], x[x.length - 1]], y: [cl.i_lcl, cl.i_lcl],
          mode: 'lines', name: 'LCL', line: { color: '#fa8c16', dash: 'dash' }, showlegend: false })
      }
      if (cl.i_center != null && x.length > 0) {
        data.push({ x: [x[0], x[x.length - 1]], y: [cl.i_center, cl.i_center],
          mode: 'lines', name: 'CL', line: { color: '#52c41a', dash: 'dash' }, showlegend: false })
      }
      addSpecLines()
      const violX = (result.violations ?? []).map(v => x[v.point_idx] ?? v.point_idx)
      const violY = (result.violations ?? []).map(v => result.x_values?.[v.point_idx] ?? 0)
      if (violX.length > 0) {
        data.push({ x: violX, y: violY, mode: 'markers', name: 'Violations',
          marker: { color: '#ff4d4f', size: 10, symbol: 'x' }, showlegend: false })
      }
      if (result.mr_values) {
        const mrX = result.mr_values.map((_, i) => i + 1)
        data.push({
          x: mrX, y: result.mr_values, mode: 'lines+markers', name: 'MR',
          line: { color: '#722ed1' }, marker: { size: 6 },
          yaxis: 'y2',
        })
        if (cl.mr_ucl != null && mrX.length > 0) {
          data.push({ x: [mrX[0], mrX[mrX.length - 1]], y: [cl.mr_ucl, cl.mr_ucl],
            mode: 'lines', yaxis: 'y2', line: { color: '#fa8c16', dash: 'dash' }, showlegend: false })
        }
        if (cl.mr_center != null && mrX.length > 0) {
          data.push({ x: [mrX[0], mrX[mrX.length - 1]], y: [cl.mr_center, cl.mr_center],
            mode: 'lines', yaxis: 'y2', line: { color: '#52c41a', dash: 'dash' }, showlegend: false })
        }
      }
    } else {
      const x = result.xbar_values?.map((_, i) => i) ?? []
      data.push({
        x, y: result.xbar_values ?? [], mode: 'lines+markers',
        name: 'X-bar', line: { color: '#1677ff' }, marker: { size: 6 },
      })
      if (cl.x_ucl != null && x.length > 0) {
        data.push({ x: [x[0], x[x.length - 1]], y: [cl.x_ucl, cl.x_ucl],
          mode: 'lines', name: 'UCL', line: { color: '#fa8c16', dash: 'dash' }, showlegend: false })
      }
      if (cl.x_lcl != null && x.length > 0) {
        data.push({ x: [x[0], x[x.length - 1]], y: [cl.x_lcl, cl.x_lcl],
          mode: 'lines', name: 'LCL', line: { color: '#fa8c16', dash: 'dash' }, showlegend: false })
      }
      if (cl.x_center != null && x.length > 0) {
        data.push({ x: [x[0], x[x.length - 1]], y: [cl.x_center, cl.x_center],
          mode: 'lines', name: 'CL', line: { color: '#52c41a', dash: 'dash' }, showlegend: false })
      }
      addSpecLines(true)
      const violX = (result.violations ?? []).map(v => x[v.point_idx] ?? v.point_idx)
      const violY = (result.violations ?? []).map(v => result.xbar_values?.[v.point_idx] ?? 0)
      if (violX.length > 0) {
        data.push({ x: violX, y: violY, mode: 'markers', name: 'Violations',
          marker: { color: '#ff4d4f', size: 10, symbol: 'x' }, showlegend: false })
      }
      if (result.chart_type === 'xbar-r' && result.r_values) {
        const rX = result.r_values.map((_, i) => i)
        data.push({
          x: rX, y: result.r_values, mode: 'lines+markers', name: 'R',
          line: { color: '#722ed1' }, marker: { size: 6 },
          yaxis: 'y2',
        })
        if (cl.r_ucl != null && rX.length > 0) {
          data.push({ x: [rX[0], rX[rX.length - 1]], y: [cl.r_ucl, cl.r_ucl],
            mode: 'lines', yaxis: 'y2', line: { color: '#fa8c16', dash: 'dash' }, showlegend: false })
        }
        if (cl.r_center != null && rX.length > 0) {
          data.push({ x: [rX[0], rX[rX.length - 1]], y: [cl.r_center, cl.r_center],
            mode: 'lines', yaxis: 'y2', line: { color: '#52c41a', dash: 'dash' }, showlegend: false })
        }
      }
      if (result.chart_type === 'xbar-s' && result.s_values) {
        const sX = result.s_values.map((_, i) => i)
        data.push({
          x: sX, y: result.s_values, mode: 'lines+markers', name: 'S',
          line: { color: '#722ed1' }, marker: { size: 6 },
          yaxis: 'y2',
        })
        if (cl.s_ucl != null && sX.length > 0) {
          data.push({ x: [sX[0], sX[sX.length - 1]], y: [cl.s_ucl, cl.s_ucl],
            mode: 'lines', yaxis: 'y2', line: { color: '#fa8c16', dash: 'dash' }, showlegend: false })
        }
        if (cl.s_center != null && sX.length > 0) {
          data.push({ x: [sX[0], sX[sX.length - 1]], y: [cl.s_center, cl.s_center],
            mode: 'lines', yaxis: 'y2', line: { color: '#52c41a', dash: 'dash' }, showlegend: false })
        }
      }
    }
    return data
  }

  const plotLayout: any = {
    margin: { t: 30, b: 40, l: 50, r: 30 },
    height: 350,
    showlegend: true,
    legend: { orientation: 'h', y: -0.15 },
    xaxis: { title: { text: 'Point Index' } },
    yaxis: { title: { text: result?.chart_type === 'i-mr' ? 'Value' : 'X-bar' } },
  }
  plotLayout.yaxis2 = { overlaying: 'y', side: 'right', showgrid: false }

  const violColumns: any[] = [
    { title: t('spc.rule'), dataIndex: 'rule', key: 'rule', width: 140,
      render: (v: number) => <Tag>{WE_RULE_NAMES[v] ?? `Rule ${v}`}</Tag> },
    { title: t('spc.point'), dataIndex: 'point_idx', key: 'point_idx', width: 80 },
    { title: t('spc.description'), dataIndex: 'description', key: 'description' },
  ]

  const capable = result?.capability
  const hasData = !!importResult && numericColumns.length > 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card title={t('spc.title')}>
        <NodeSourceFilter
          section="spc"
          sourcedFromNode={sourcedFromNode}
          dataLoaded={dataSourceLoaded(sourcedFromNode?.dataSourceIds, importResult?.dataset_id)}
          columns={Object.keys(importResult?.stats.column_stats ?? {})}
          filterColumn={nodeFilterColumn}
          setFilterColumn={setNodeFilterColumn}
          filterValue={nodeFilterValue}
          setFilterValue={setNodeFilterValue}
          clearFilter={() => {
            setNodeFilterColumn(undefined)
            setNodeFilterValue(undefined)
          }}
          valuePlaceholder={t('spc.sameSourceHint')}
        />
        <Space wrap style={{ marginBottom: 12 }}>
          <Form.Item label={t('spc.chartType')} style={{ margin: 0 }}>
            <Select
              value={chartType}
              onChange={setChartType}
              options={[
                { value: 'i-mr', label: t('spc.iMr') },
                { value: 'xbar-r', label: t('spc.xbarR') },
                { value: 'xbar-s', label: t('spc.xbarS') },
              ]}
              style={{ width: 280 }}
            />
          </Form.Item>
          <Form.Item label={t('spc.outputColumn')} style={{ margin: 0 }}>
            <Select
              value={column}
              onChange={setColumn}
              options={numericColumns.map(name => ({ value: name, label: name }))}
              disabled={!hasData}
              style={{ width: 180 }}
              placeholder="Select column"
            />
          </Form.Item>
          {chartType !== 'i-mr' && (
            <Form.Item label={t('spc.subgroupSize')} style={{ margin: 0 }}>
              <Input
                type="number"
                min={2}
                max={10}
                value={subgroupSize}
                onChange={e => setSubgroupSize(Number(e.target.value))}
                style={{ width: 80 }}
              />
            </Form.Item>
          )}
          <Button type="primary" onClick={handleAnalyze} loading={loading} disabled={!hasData || !column}>
            {t('spc.analyze')}
          </Button>
        </Space>
        {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 12 }} />}
      </Card>

      {result && (
        <>
          <Card title={t('spc.processCapability')} size="small">
            <Space wrap>
              <Space>
                <Typography.Text>Cp:</Typography.Text>
                <Tag color={capacityColor(capable?.cp ?? null)} style={{ fontSize: 14 }}>
                  {capable?.cp?.toFixed(2) ?? 'N/A'}
                </Tag>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {capacityLabel(capable?.cp ?? null)}
                </Typography.Text>
              </Space>
              <Space>
                <Typography.Text>Cpk:</Typography.Text>
                <Tag color={capacityColor(capable?.cpk ?? null)} style={{ fontSize: 14 }}>
                  {capable?.cpk?.toFixed(2) ?? 'N/A'}
                </Tag>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {capacityLabel(capable?.cpk ?? null)}
                </Typography.Text>
              </Space>
              <Space>
                <Typography.Text>Pp:</Typography.Text>
                <Tag color={capacityColor(capable?.pp ?? null)} style={{ fontSize: 14 }}>
                  {capable?.pp?.toFixed(2) ?? 'N/A'}
                </Tag>
              </Space>
              <Space>
                <Typography.Text>Ppk:</Typography.Text>
                <Tag color={capacityColor(capable?.ppk ?? null)} style={{ fontSize: 14 }}>
                  {capable?.ppk?.toFixed(2) ?? 'N/A'}
                </Tag>
              </Space>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                n={capable?.total_observations} obs, {capable?.n_subgroups ?? 0} subgroups
              </Typography.Text>
            </Space>
          </Card>

          <Card title={t('spc.chartType')} size="small">
            <Plot
              data={buildPlotData()}
              layout={plotLayout}
              config={{ responsive: true, displayModeBar: false }}
              style={{ width: '100%' }}
            />
          </Card>

          <Card title={`${t('spc.violations')} (${result.violations?.length ?? 0})`} size="small">
            {(!result.violations || result.violations.length === 0) ? (
              <Alert type="success" message={t('spc.noViolations')} showIcon />
            ) : (
              <Table
                dataSource={result.violations}
                columns={violColumns}
                rowKey={v => `${v.rule}-${v.point_idx}`}
                size="small"
                pagination={{ pageSize: 20 }}
              />
            )}
          </Card>
        </>
      )}

      {!result && importResult && (
        <Alert
          type="info"
          message={t('spc.analyze')}
          description={t('spc.selectColumnHint')}
          showIcon
        />
      )}
      {!importResult && (
        <Alert type="warning" message={t('spc.noDataHint')} description={t('spc.noDataHint')} showIcon />
      )}
    </div>
  )
}
