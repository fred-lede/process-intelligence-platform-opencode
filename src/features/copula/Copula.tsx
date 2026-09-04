import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Card,
  Typography,
  Space,
  Button,
  Alert,
  Select,
  InputNumber,
  Table,
  Tag,
  Empty,
} from 'antd'
import { ThunderboltOutlined } from '@ant-design/icons'
import { computeCopula, type CopulaResult } from '../../lib/engine'
import { useDataPipelineStore } from '../../stores/dataPipelineStore'
import { useAssistantContextStore } from '../../stores/assistantContextStore'

type Mode = 'independent' | 'gaussian_copula' | 'direct'

export default function Copula() {
  const { t } = useTranslation()
  const { setContext } = useAssistantContextStore()
  const anomalyScenarios = useDataPipelineStore((s) => s.anomalyScenarios)

  const [selected, setSelected] = useState<string[]>([])
  const [mode, setMode] = useState<Mode>('independent')
  const [nSamples, setNSamples] = useState(100000)
  const [seed, setSeed] = useState<number | null>(42)
  const [corr, setCorr] = useState<number[][]>([])
  const [directs, setDirects] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<CopulaResult | null>(null)
  const [warning, setWarning] = useState<string | null>(null)

  const options = useMemo(
    () =>
      anomalyScenarios.map((s) => ({
        value: s.anomaly_id,
        label: `${s.name || s.anomaly_id} (${(s.occurrence_probability * 100).toFixed(1)}%)`,
      })),
    [anomalyScenarios],
  )

  useEffect(() => {
    const n = selected.length
    if (n < 2) {
      setCorr([])
      return
    }
    setCorr((prev) => {
      const next: number[][] = Array.from({ length: n }, (_, i) =>
        Array.from({ length: n }, (_, j) => (i === j ? 1 : prev?.[i]?.[j] ?? 0)),
      )
      return next
    })
  }, [selected.length])

  useEffect(() => {
    setContext(
      'copula',
      selected.length >= 2
        ? `${selected.length} anomaly(-ies); mode=${mode}. ${JSON.stringify(result?.joint_probabilities ?? {})}`
        : `Select anomalies (${anomalyScenarios.length} available)`,
    )
  }, [selected, mode, result, setContext, anomalyScenarios.length])

  const setCorrCell = (i: number, j: number, v: number) => {
    setCorr((prev) => {
      const next = prev.map((row) => row.slice())
      next[i][j] = v
      next[j][i] = v
      return next
    })
  }

  const pairs = useMemo(() => {
    const out: Array<{ i: number; j: number; key: string }> = []
    for (let i = 0; i < selected.length; i++) {
      for (let j = i + 1; j < selected.length; j++) {
        out.push({ i, j, key: `${selected[i]}&${selected[j]}` })
      }
    }
    return out
  }, [selected])

  const handleCompute = async () => {
    if (selected.length < 2) {
      setError(t('copula.noAnomalies'))
      return
    }
    const anomalies = selected.map((id) => {
      const s = anomalyScenarios.find((a) => a.anomaly_id === id)
      return { anomaly_id: id, occurrence_probability: s?.occurrence_probability ?? 0 }
    })
    setLoading(true)
    setError(null)
    setWarning(null)
    try {
      const params: Parameters<typeof computeCopula>[0] = {
        anomalies,
        seed: seed ?? undefined,
        n_samples: nSamples,
      }
      if (mode === 'gaussian_copula') params.correlation_matrix = corr
      if (mode === 'direct') params.direct_joints = directs
      const res = await computeCopula(params)
      setResult(res)
      setWarning(res.warning ?? null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  const jointRows = useMemo(() => {
    if (!result) return []
    return pairs
      .map((p) => ({
        key: p.key,
        anomalyA: selected[p.i],
        anomalyB: selected[p.j],
        jointProbability: result.joint_probabilities?.[p.key],
        independentExpected: result.pair_correlations?.find(
          (pc) => pc.anomaly_a === selected[p.i] && pc.anomaly_b === selected[p.j],
        )?.independent_expected,
        correlation: result.pair_correlations?.find(
          (pc) => pc.anomaly_a === selected[p.i] && pc.anomaly_b === selected[p.j],
        )?.correlation,
      }))
      .filter((r) => r.jointProbability !== undefined || r.independentExpected !== undefined)
  }, [result, pairs, selected])

  const marginals = useMemo(() => {
    if (!result) return []
    return selected
      .filter((id) => result.joint_probabilities?.[id] !== undefined)
      .map((id) => ({ id, prob: result.joint_probabilities![id] }))
  }, [result, selected])

  return (
    <Card title={t('copula.title')}>
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        {t('copula.description')}
      </Typography.Paragraph>

      {options.length === 0 && (
        <Alert
          type="info"
          showIcon
          message={t('copula.noAnomalySource')}
          style={{ marginBottom: 16 }}
        />
      )}

      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Space wrap>
          <Select
            mode="multiple"
            allowClear
            style={{ minWidth: 320 }}
            placeholder={t('copula.selectAnomalies')}
            value={selected}
            onChange={setSelected}
            options={options}
          />
          <Select
            value={mode}
            onChange={(v) => setMode(v as Mode)}
            style={{ minWidth: 200 }}
            options={[
              { value: 'independent', label: t('copula.independent') },
              { value: 'gaussian_copula', label: t('copula.gaussianCopula') },
              { value: 'direct', label: t('copula.direct') },
            ]}
          />
        </Space>

        <Space wrap>
          <span>{t('copula.nSamples')}</span>
          <InputNumber
            min={1000}
            max={500000}
            step={1000}
            value={nSamples}
            onChange={(v) => setNSamples(v ?? 100000)}
          />
          <span>{t('copula.seed')}</span>
          <InputNumber value={seed} onChange={(v) => setSeed(v)} />
          <Button type="primary" icon={<ThunderboltOutlined />} onClick={handleCompute} loading={loading}>
            {t('copula.compute')}
          </Button>
        </Space>

        {error && <Alert type="error" showIcon message={error} />}
        {warning && <Alert type="warning" showIcon message={warning} />}
      </Space>

      {mode === 'gaussian_copula' && selected.length >= 2 && (
        <Space direction="vertical" size={8} style={{ width: '100%', marginTop: 16 }}>
          <Typography.Text strong>{t('copula.correlationMatrix')}</Typography.Text>
          <Table
            size="small"
            rowKey={(_, i) => String(i)}
            pagination={false}
            dataSource={selected.map((id, i) => ({ key: id, id, i }))}
            columns={[
              { title: '', dataIndex: 'id', key: 'id', width: 160 },
              ...selected.map((other, j) => ({
                title: other.slice(0, 12),
                key: `c${j}`,
                width: 110,
                render: (_: unknown, row: { i: number }) => (
                  <InputNumber
                    size="small"
                    disabled={row.i === j}
                    min={-1}
                    max={1}
                    step={0.1}
                    value={corr[row.i]?.[j]}
                    onChange={(v) => setCorrCell(row.i, j, v ?? 0)}
                  />
                ),
              })),
            ]}
          />
        </Space>
      )}

      {mode === 'direct' && selected.length >= 2 && (
        <Space direction="vertical" size={8} style={{ width: '100%', marginTop: 16 }}>
          <Typography.Text strong>{t('copula.directJoints')}</Typography.Text>
          <Space wrap>
            {pairs.map((p) => (
              <Space key={p.key} size={4}>
                <Tag>{selected[p.i]}</Tag>
                <span>&</span>
                <Tag>{selected[p.j]}</Tag>
                <InputNumber
                  size="small"
                  min={0}
                  max={1}
                  step={0.05}
                  value={directs[p.key]}
                  onChange={(v) => setDirects((prev) => ({ ...prev, [p.key]: v ?? 0 }))}
                />
              </Space>
            ))}
          </Space>
        </Space>
      )}

      {result && (
        <Space direction="vertical" size={8} style={{ width: '100%', marginTop: 16 }}>
          <Space wrap>
            <Tag color={result.mode === 'independent' ? 'default' : result.mode === 'gaussian_copula' ? 'purple' : 'gold'}>
              {result.mode === 'gaussian_copula'
                ? t('copula.gaussianCopula')
                : result.mode === 'direct'
                  ? t('copula.direct')
                  : t('copula.independent')}
            </Tag>
            <Typography.Text strong>{t('copula.results')}</Typography.Text>
          </Space>

          {marginals.length > 0 && (
            <Space wrap>
              {marginals.map((m) => (
                <Tag key={m.id} color="blue">
                  P({m.id}) = {(m.prob * 100).toFixed(2)}%
                </Tag>
              ))}
            </Space>
          )}

          {jointRows.length > 0 ? (
            <Table
              size="middle"
              rowKey="key"
              pagination={false}
              dataSource={jointRows}
              columns={[
                {
                  title: t('copula.pair'),
                  key: 'pair',
                  render: (_, r) => (
                    <span>
                      <Tag>{r.anomalyA}</Tag>
                      <span>&</span>
                      <Tag>{r.anomalyB}</Tag>
                    </span>
                  ),
                },
                {
                  title: t('copula.jointProb'),
                  dataIndex: 'jointProbability',
                  key: 'jointProbability',
                  render: (v: number | undefined) =>
                    v === undefined ? '—' : `${(v * 100).toFixed(4)}%`,
                },
                {
                  title: t('copula.independentExpected'),
                  dataIndex: 'independentExpected',
                  key: 'independentExpected',
                  render: (v: number | undefined) =>
                    v === undefined ? '—' : `${(v * 100).toFixed(4)}%`,
                },
                {
                  title: t('copula.correlationIndex'),
                  dataIndex: 'correlation',
                  key: 'correlation',
                  render: (v: number | undefined) => (v === undefined ? '—' : v.toFixed(4)),
                },
              ]}
            />
          ) : (
            <Empty description={t('copula.noResultRows')} />
          )}
        </Space>
      )}
    </Card>
  )
}
