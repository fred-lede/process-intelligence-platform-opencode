import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, Select, Space, Button, Alert, Form, Input, InputNumber, Typography, Table, Tag } from 'antd'
import Plot from '../../components/PlotChart'
import NodeSourceFilter from '../../components/NodeSourceFilter'
import { useDataPipelineStore } from '../../stores/dataPipelineStore'
import { useAssistantContextStore } from '../../stores/assistantContextStore'
import { analyzeSPC, analyzeSPCBatch, analyzeSPCMultiDataset, getFlowGraph, getDataAssets, type SPCAnalysisResult, type SPCBatchResult, type MultiDatasetSPCResult } from '../../lib/engine'
import {
  consumeNodeContext,
  dataSourceLoaded,
  findNodeById,
} from '../../lib/processFlowContext'
import { buildSpcContext } from '../../lib/assistantData'

const CHART_TYPES = ['i-mr', 'xbar-r', 'xbar-s', 'ewma', 'cusum'] as const
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
  const { importResult, spec, controlLimits } = useDataPipelineStore()
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
  const [ewmaLambda, setEwmaLambda] = useState(0.2)
  const [ewmaL, setEwmaL] = useState(3)
  const [cusumK, setCusumK] = useState(0.5)
  const [cusumH, setCusumH] = useState(5)
  const [result, setResult] = useState<SPCAnalysisResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [numericColumns, setNumericColumns] = useState<string[]>([])
  const [batchMode, setBatchMode] = useState(false)
  const [multiDatasetMode, setMultiDatasetMode] = useState(false)
  const [selectedColumns, setSelectedColumns] = useState<string[]>([])
  const [batchResult, setBatchResult] = useState<SPCBatchResult | null>(null)
  const [datasetEntries, setDatasetEntries] = useState<Array<{ dataset_id: string; column: string }>>([])
  const [multiResult, setMultiResult] = useState<MultiDatasetSPCResult | null>(null)
  const [datasetAssets, setDatasetAssets] = useState<Array<{ dataset_id: string; file_path: string; row_count: number; column_count: number }>>([])

  useEffect(() => {
    getDataAssets().then(r => setDatasetAssets(r.datasets ?? [])).catch(() => {})
  }, [])

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

  useEffect(() => {
    if (!batchResult) return
    const lines = Object.entries(batchResult.results)
      .map(([, res]) => buildSpcContext(res))
      .filter(Boolean)
    if (lines.length) {
      setContext('spc', lines.join('\n'))
    }
  }, [batchResult, setContext])

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
        ewma_lambda: chartType === 'ewma' ? ewmaLambda : undefined,
        ewma_L: chartType === 'ewma' ? ewmaL : undefined,
        cusum_k: chartType === 'cusum' ? cusumK : undefined,
        cusum_H: chartType === 'cusum' ? cusumH : undefined,
        control_limits: controlLimits[column] ?? undefined,
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

  const handleMultiDatasetAnalyze = async () => {
    if (datasetEntries.length === 0) return
    setLoading(true)
    setError(null)
    try {
      const res = await analyzeSPCMultiDataset({
        entries: datasetEntries,
        chart_type: chartType,
        lsl: spec?.lsl ?? undefined,
        usl: spec?.usl ?? undefined,
      })
      setMultiResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  const handleBatchAnalyze = async () => {
    if (!importResult || selectedColumns.length === 0) return
    setLoading(true)
    setError(null)
    try {
      const res = await analyzeSPCBatch({
        dataset_id: importResult.dataset_id,
        columns: selectedColumns,
        chart_type: chartType,
        subgroup_size: chartType === 'i-mr' ? 1 : subgroupSize,
        lsl: spec?.lsl ?? undefined,
        usl: spec?.usl ?? undefined,
        ewma_lambda: chartType === 'ewma' ? ewmaLambda : undefined,
        ewma_L: chartType === 'ewma' ? ewmaL : undefined,
        cusum_k: chartType === 'cusum' ? cusumK : undefined,
        cusum_H: chartType === 'cusum' ? cusumH : undefined,
      })
      setBatchResult(res)
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

  const buildPlotData = (res: SPCAnalysisResult) => {
    const cl = res.control_limits
    const data: any[] = []

    const addSpecLines = (ref = false) => {
      const xs = (res.chart_type === 'i-mr'
        ? res.x_values?.map((_, i) => i)
        : res.xbar_values?.map((_, i) => i)) ?? []
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

    if (res.chart_type === 'i-mr') {
      const x = res.x_values?.map((_, i) => i) ?? []
      data.push({
        x, y: res.x_values ?? [], mode: 'lines+markers',
        name: 'Individuals', line: { color: '#1677ff' }, marker: { size: 6 },
      })
      if (cl.i_ucl != null && x.length > 0) {
        data.push({ x: [x[0], x[x.length - 1]], y: [cl.i_ucl, cl.i_ucl],
          mode: 'lines', name: 'UCL', line: { color: '#fa8c16', dash: 'dash' } })
      }
      if (cl.i_lcl != null && x.length > 0) {
        data.push({ x: [x[0], x[x.length - 1]], y: [cl.i_lcl, cl.i_lcl],
          mode: 'lines', name: 'LCL', line: { color: '#fa8c16', dash: 'dash' } })
      }
      if (cl.i_center != null && x.length > 0) {
        data.push({ x: [x[0], x[x.length - 1]], y: [cl.i_center, cl.i_center],
          mode: 'lines', name: 'CL', line: { color: '#52c41a', dash: 'dash' } })
      }
      addSpecLines()
      const violX = (res.violations ?? []).map(v => x[v.point_idx] ?? v.point_idx)
      const violY = (res.violations ?? []).map(v => res.x_values?.[v.point_idx] ?? 0)
      if (violX.length > 0) {
        data.push({ x: violX, y: violY, mode: 'markers', name: 'Violations',
          marker: { color: '#ff4d4f', size: 10, symbol: 'x' }, showlegend: false })
      }
      // Outlier markers (blue circles)
      if (res.outlier_indices && res.outlier_indices.length > 0) {
        const ox = res.outlier_indices
        const oy = res.chart_type === 'i-mr'
          ? (res.x_values ?? []).filter((_, i) => ox.includes(i))
          : (res.xbar_values ?? []).filter((_, i) => ox.includes(i))
        data.push({
          x: ox, y: oy, mode: 'markers',
          name: t('spc.outliers'),
          marker: { color: '#1677ff', size: 10, symbol: 'circle' },
          showlegend: true,
        })
      }
      // Change point markers (green triangles)
      if (res.change_points && res.change_points.length > 0) {
        const cx = res.change_points
        const cy = res.chart_type === 'i-mr'
          ? (res.x_values ?? []).filter((_, i) => cx.includes(i))
          : (res.xbar_values ?? []).filter((_, i) => cx.includes(i))
        data.push({
          x: cx, y: cy, mode: 'markers',
          name: t('spc.changePoints'),
          marker: { color: '#52c41a', size: 12, symbol: 'triangle-up' },
          showlegend: true,
        })
      }
      if (res.mr_values) {
        const mrX = res.mr_values.map((_, i) => i + 1)
        data.push({
          x: mrX, y: res.mr_values, mode: 'lines+markers', name: 'MR',
          line: { color: '#722ed1' }, marker: { size: 6 },
          yaxis: 'y2',
        })
        if (cl.mr_ucl != null && mrX.length > 0) {
          data.push({ x: [mrX[0], mrX[mrX.length - 1]], y: [cl.mr_ucl, cl.mr_ucl],
            mode: 'lines', yaxis: 'y2', line: { color: '#fa8c16', dash: 'dash' } })
        }
        if (cl.mr_center != null && mrX.length > 0) {
          data.push({ x: [mrX[0], mrX[mrX.length - 1]], y: [cl.mr_center, cl.mr_center],
            mode: 'lines', yaxis: 'y2', line: { color: '#52c41a', dash: 'dash' } })
        }
      }
    } else if (res.chart_type === 'ewma') {
      const z = res.z_values ?? []
      const x = res.x_values?.map((_, i) => i) ?? []
      data.push({
        x, y: z, mode: 'lines+markers',
        name: t('spc.ewmaZValue'), line: { color: '#1677ff' }, marker: { size: 4 },
      })
      if (res.ucl != null && x.length > 0) {
        data.push({
          x: [x[0], x[x.length - 1]], y: [res.ucl, res.ucl],
          mode: 'lines', name: 'UCL',
          line: { color: '#fa8c16', dash: 'dash' }, showlegend: false,
        })
      }
      if (res.lcl != null && x.length > 0) {
        data.push({
          x: [x[0], x[x.length - 1]], y: [res.lcl, res.lcl],
          mode: 'lines', name: 'LCL',
          line: { color: '#fa8c16', dash: 'dash' }, showlegend: false,
        })
      }
      if (res.cl != null && x.length > 0) {
        data.push({
          x: [x[0], x[x.length - 1]], y: [res.cl, res.cl],
          mode: 'lines', name: 'CL',
          line: { color: '#52c41a', dash: 'dash' }, showlegend: false,
        })
      }
      const violZ = (res.violations ?? []).map(v => z[v.point_idx] ?? 0)
      const violX = (res.violations ?? []).map(v => x[v.point_idx] ?? v.point_idx)
      if (violZ.length > 0) {
        data.push({
          x: violX, y: violZ, mode: 'markers', name: t('spc.ewmaViolations'),
          marker: { color: '#ff4d4f', size: 8, symbol: 'x' }, showlegend: false,
        })
      }
    } else if (res.chart_type === 'cusum') {
      const c_plus = res.c_plus ?? []
      const c_minus = res.c_minus ?? []
      const x = res.x_values?.map((_, i) => i) ?? []
      data.push({
        x, y: c_plus, mode: 'lines+markers',
        name: t('spc.cusumCP'), line: { color: '#1677ff' }, marker: { size: 4 },
      })
      data.push({
        x, y: c_minus, mode: 'lines+markers',
        name: t('spc.cusumCM'), line: { color: '#722ed1' }, marker: { size: 4 },
      })
      if (res.cusum_H != null && x.length > 0) {
        data.push({
          x: [x[0], x[x.length - 1]], y: [res.cusum_H, res.cusum_H],
          mode: 'lines', name: 'H (limit)',
          line: { color: '#fa8c16', dash: 'dash' }, showlegend: false,
        })
      }
      const violX_cusum = (res.violations ?? []).map(v => x[v.point_idx] ?? v.point_idx)
      if (violX_cusum.length > 0) {
        data.push({
          x: violX_cusum, y: violX_cusum.map(() => res.cusum_H ?? 5),
          mode: 'markers', name: t('spc.cusumViolations'),
          marker: { color: '#ff4d4f', size: 8, symbol: 'x' }, showlegend: false,
        })
      }
    } else {
      const x = res.xbar_values?.map((_, i) => i) ?? []
      data.push({
        x, y: res.xbar_values ?? [], mode: 'lines+markers',
        name: 'X-bar', line: { color: '#1677ff' }, marker: { size: 6 },
      })
      if (cl.x_ucl != null && x.length > 0) {
        data.push({ x: [x[0], x[x.length - 1]], y: [cl.x_ucl, cl.x_ucl],
          mode: 'lines', name: 'UCL', line: { color: '#fa8c16', dash: 'dash' } })
      }
      if (cl.x_lcl != null && x.length > 0) {
        data.push({ x: [x[0], x[x.length - 1]], y: [cl.x_lcl, cl.x_lcl],
          mode: 'lines', name: 'LCL', line: { color: '#fa8c16', dash: 'dash' } })
      }
      if (cl.x_center != null && x.length > 0) {
        data.push({ x: [x[0], x[x.length - 1]], y: [cl.x_center, cl.x_center],
          mode: 'lines', name: 'CL', line: { color: '#52c41a', dash: 'dash' } })
      }
      addSpecLines(true)
      const violX = (res.violations ?? []).map(v => x[v.point_idx] ?? v.point_idx)
      const violY = (res.violations ?? []).map(v => res.xbar_values?.[v.point_idx] ?? 0)
      if (violX.length > 0) {
        data.push({ x: violX, y: violY, mode: 'markers', name: 'Violations',
          marker: { color: '#ff4d4f', size: 10, symbol: 'x' }, showlegend: false })
      }
      // Outlier markers (blue circles)
      if (res.outlier_indices && res.outlier_indices.length > 0) {
        const ox = res.outlier_indices
        const oy = res.chart_type === 'i-mr'
          ? (res.x_values ?? []).filter((_, i) => ox.includes(i))
          : (res.xbar_values ?? []).filter((_, i) => ox.includes(i))
        data.push({
          x: ox, y: oy, mode: 'markers',
          name: t('spc.outliers'),
          marker: { color: '#1677ff', size: 10, symbol: 'circle' },
          showlegend: true,
        })
      }
      // Change point markers (green triangles)
      if (res.change_points && res.change_points.length > 0) {
        const cx = res.change_points
        const cy = res.chart_type === 'i-mr'
          ? (res.x_values ?? []).filter((_, i) => cx.includes(i))
          : (res.xbar_values ?? []).filter((_, i) => cx.includes(i))
        data.push({
          x: cx, y: cy, mode: 'markers',
          name: t('spc.changePoints'),
          marker: { color: '#52c41a', size: 12, symbol: 'triangle-up' },
          showlegend: true,
        })
      }
      if (res.chart_type === 'xbar-r' && res.r_values) {
        const rX = res.r_values.map((_, i) => i)
        data.push({
          x: rX, y: res.r_values, mode: 'lines+markers', name: 'R',
          line: { color: '#722ed1' }, marker: { size: 6 },
          yaxis: 'y2',
        })
        if (cl.r_ucl != null && rX.length > 0) {
          data.push({ x: [rX[0], rX[rX.length - 1]], y: [cl.r_ucl, cl.r_ucl],
            mode: 'lines', yaxis: 'y2', line: { color: '#fa8c16', dash: 'dash' } })
        }
        if (cl.r_center != null && rX.length > 0) {
          data.push({ x: [rX[0], rX[rX.length - 1]], y: [cl.r_center, cl.r_center],
            mode: 'lines', yaxis: 'y2', line: { color: '#52c41a', dash: 'dash' } })
        }
      }
      if (res.chart_type === 'xbar-s' && res.s_values) {
        const sX = res.s_values.map((_, i) => i)
        data.push({
          x: sX, y: res.s_values, mode: 'lines+markers', name: 'S',
          line: { color: '#722ed1' }, marker: { size: 6 },
          yaxis: 'y2',
        })
        if (cl.s_ucl != null && sX.length > 0) {
          data.push({ x: [sX[0], sX[sX.length - 1]], y: [cl.s_ucl, cl.s_ucl],
            mode: 'lines', yaxis: 'y2', line: { color: '#fa8c16', dash: 'dash' } })
        }
        if (cl.s_center != null && sX.length > 0) {
          data.push({ x: [sX[0], sX[sX.length - 1]], y: [cl.s_center, cl.s_center],
            mode: 'lines', yaxis: 'y2', line: { color: '#52c41a', dash: 'dash' } })
        }
      }
    }
    return data
  }

  const buildPlotLayout = (chartType: string): any => ({
    margin: { t: 30, b: 40, l: 50, r: 30 },
    height: 350,
    showlegend: true,
    legend: { orientation: 'h', y: -0.15 },
    xaxis: { title: { text: 'Point Index' } },
    yaxis: { title: { text: chartType === 'i-mr' ? 'Value' : chartType === 'ewma' ? 'Z(t)' : chartType === 'cusum' ? 'CUSUM' : 'X-bar' } },
    yaxis2: { overlaying: 'y', side: 'right', showgrid: false },
  })

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
                { value: 'ewma', label: t('spc.ewma') },
                { value: 'cusum', label: t('spc.cusum') },
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
          {chartType === 'ewma' && (
            <>
              <Form.Item label={t('spc.ewmaLambda')} style={{ margin: 0 }}>
                <InputNumber
                  min={0.05} max={0.5} step={0.05}
                  value={ewmaLambda}
                  onChange={(v) => setEwmaLambda(v || 0.2)}
                  style={{ width: 80 }}
                />
              </Form.Item>
              <Form.Item label={t('spc.ewmaL')} style={{ margin: 0 }}>
                <InputNumber
                  min={2} max={4} step={0.5}
                  value={ewmaL}
                  onChange={(v) => setEwmaL(v || 3)}
                  style={{ width: 80 }}
                />
              </Form.Item>
            </>
          )}
          {chartType === 'cusum' && (
            <>
              <Form.Item label={t('spc.cusumK')} style={{ margin: 0 }}>
                <InputNumber
                  min={0.1} max={1} step={0.1}
                  value={cusumK}
                  onChange={(v) => setCusumK(v || 0.5)}
                  style={{ width: 80 }}
                />
              </Form.Item>
              <Form.Item label={t('spc.cusumH')} style={{ margin: 0 }}>
                <InputNumber
                  min={3} max={6} step={0.5}
                  value={cusumH}
                  onChange={(v) => setCusumH(v || 5)}
                  style={{ width: 80 }}
                />
              </Form.Item>
            </>
          )}
          <Button type="primary" onClick={handleAnalyze} loading={loading} disabled={!hasData || !column}>
            {t('spc.analyze')}
          </Button>
          <Button onClick={() => setBatchMode(!batchMode)}>
            {batchMode ? t('spc.singleAnalysis') : t('spc.batchAnalyze')}
          </Button>
          <Button onClick={() => setMultiDatasetMode(!multiDatasetMode)}>
            {t('spc.multiDatasetCompare')}
          </Button>
        </Space>
        {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 12 }} />}
        {batchMode && (
          <Card title={t('spc.compareColumns')} size="small">
            <Select
              mode="multiple"
              style={{ width: '100%', marginBottom: 12 }}
              value={selectedColumns}
              onChange={setSelectedColumns}
              options={numericColumns.map(name => ({ value: name, label: name }))}
              placeholder={t('spc.selectColumns')}
            />
            <Button type="primary" onClick={handleBatchAnalyze} loading={loading} disabled={selectedColumns.length === 0}>
              {t('spc.analyze')}
            </Button>
          </Card>
        )}
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
              data={buildPlotData(result)}
              layout={buildPlotLayout(result.chart_type)}
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

          {result.suggestions && result.suggestions.length > 0 && (
            <Card title={t('spc.suggestions')} size="small">
              {result.suggestions.map((s, i) => (
                <Alert
                  key={i}
                  type={s.severity === 'error' ? 'error' : 'warning'}
                  message={s.message}
                  showIcon
                  style={{ marginBottom: 8 }}
                />
              ))}
            </Card>
          )}
          {result && (!result.suggestions || result.suggestions.length === 0) && (
            <Alert type="success" message={t('spc.noSuggestions')} showIcon />
          )}
        </>
      )}

      {batchResult && (
        <>
          <Card title={t('spc.compareColumns')} size="small">
            <Table
              dataSource={Object.entries(batchResult.results).map(([col, res]) => ({
                key: col,
                column: col,
                cp: res.capability?.cp,
                cpk: res.capability?.cpk,
                pp: res.capability?.pp,
                ppk: res.capability?.ppk,
                violations: res.violations?.length ?? 0,
              }))}
              columns={[
                { title: t('spc.column'), dataIndex: 'column', key: 'column' },
                { title: 'Cp', dataIndex: 'cp', key: 'cp',
                  render: (v: number) => <Tag color={capacityColor(v)}>{v?.toFixed(2) ?? 'N/A'}</Tag> },
                { title: 'Cpk', dataIndex: 'cpk', key: 'cpk',
                  render: (v: number) => <Tag color={capacityColor(v)}>{v?.toFixed(2) ?? 'N/A'}</Tag> },
                { title: 'Pp', dataIndex: 'pp', key: 'pp',
                  render: (v: number) => <Tag color={capacityColor(v)}>{v?.toFixed(2) ?? 'N/A'}</Tag> },
                { title: 'Ppk', dataIndex: 'ppk', key: 'ppk',
                  render: (v: number) => <Tag color={capacityColor(v)}>{v?.toFixed(2) ?? 'N/A'}</Tag> },
                { title: t('spc.violations'), dataIndex: 'violations', key: 'violations' },
              ]}
              pagination={false}
            />
          </Card>
          {Object.entries(batchResult.results).map(([col, res]) => (
            <Card key={col} title={col} size="small">
              <Plot
                data={buildPlotData(res)}
                layout={buildPlotLayout(res.chart_type)}
                config={{ responsive: true, displayModeBar: false }}
                style={{ width: '100%' }}
              />
            </Card>
          ))}
        </>
      )}

      {multiDatasetMode && (
        <Card title={t('spc.multiDatasetCompare')} size="small">
          <Alert type="info" showIcon message={t('spc.multiDatasetCompareHint')} style={{ marginBottom: 12 }} />
          <Space direction="vertical" style={{ width: '100%' }} size="small">
            {datasetAssets.map(asset => (
              <Space key={asset.dataset_id} style={{ width: '100%' }} wrap>
                <Typography.Text style={{ width: 200, overflow: 'hidden', textOverflow: 'ellipsis' }} title={asset.file_path}>
                  {asset.file_path.split('/').pop() ?? asset.dataset_id.slice(0, 8)}
                </Typography.Text>
                <Select
                  style={{ width: 200 }}
                  value={datasetEntries.find(e => e.dataset_id === asset.dataset_id)?.column}
                  onChange={(col) => {
                    const existing = datasetEntries.find(e => e.dataset_id === asset.dataset_id)
                    if (existing) {
                      setDatasetEntries(datasetEntries.map(e => e.dataset_id === asset.dataset_id ? { ...e, column: col } : e))
                    } else if (col) {
                      setDatasetEntries([...datasetEntries, { dataset_id: asset.dataset_id, column: col }])
                    }
                  }}
                  options={numericColumns.map(name => ({ value: name, label: name }))}
                  placeholder={t('spc.outputColumn')}
                  allowClear
                />
              </Space>
            ))}
            <Button type="primary" onClick={handleMultiDatasetAnalyze} loading={loading} disabled={datasetEntries.length === 0}>
              {t('spc.analyze')}
            </Button>
          </Space>
          {multiResult && multiResult.results.length > 0 && (
            <>
              <Card title={t('spc.compareColumns')} size="small" style={{ marginTop: 12 }}>
                <Table
                  dataSource={multiResult.results.map(r => ({
                    key: r.dataset_id,
                    dataset: r.source_file?.split('/').pop() ?? r.dataset_id.slice(0, 8),
                    column: r.column,
                    n_points: r.n_points,
                    cp: r.result.capability?.cp,
                    cpk: r.result.capability?.cpk,
                    pp: r.result.capability?.pp,
                    ppk: r.result.capability?.ppk,
                    violations: r.result.violations?.length ?? 0,
                  }))}
                  columns={[
                    { title: t('spc.datasetColumn'), dataIndex: 'dataset', key: 'dataset' },
                    { title: t('spc.column'), dataIndex: 'column', key: 'column' },
                    { title: t('spc.nPoints'), dataIndex: 'n_points', key: 'n_points' },
                    { title: 'Cp', dataIndex: 'cp', key: 'cp',
                      render: (v: number) => <Tag color={capacityColor(v)}>{v?.toFixed(2) ?? 'N/A'}</Tag> },
                    { title: 'Cpk', dataIndex: 'cpk', key: 'cpk',
                      render: (v: number) => <Tag color={capacityColor(v)}>{v?.toFixed(2) ?? 'N/A'}</Tag> },
                    { title: 'Pp', dataIndex: 'pp', key: 'pp',
                      render: (v: number) => <Tag color={capacityColor(v)}>{v?.toFixed(2) ?? 'N/A'}</Tag> },
                    { title: 'Ppk', dataIndex: 'ppk', key: 'ppk',
                      render: (v: number) => <Tag color={capacityColor(v)}>{v?.toFixed(2) ?? 'N/A'}</Tag> },
                    { title: t('spc.violations'), dataIndex: 'violations', key: 'violations' },
                  ]}
                  pagination={false}
                />
              </Card>
              {multiResult.results.map(r => (
                <Card key={r.dataset_id} title={`${r.source_file?.split('/').pop() ?? r.dataset_id} — ${r.column}`} size="small">
                  <Plot
                    data={buildPlotData(r.result)}
                    layout={buildPlotLayout(r.result.chart_type)}
                    config={{ responsive: true, displayModeBar: false }}
                    style={{ width: '100%' }}
                  />
                </Card>
              ))}
            </>
          )}
        </Card>
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
