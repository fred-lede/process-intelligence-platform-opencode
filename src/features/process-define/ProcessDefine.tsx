import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Card,
  Form,
  Input,
  InputNumber,
  Select,
  Alert,
  Button,
  Space,
  Table,
  Typography,
  Tag,
  Tooltip,
  Badge,
  Popconfirm,
} from 'antd'
import {
  CheckOutlined,
  ThunderboltOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useDataPipelineStore, type SpecConfiguration } from '../../stores/dataPipelineStore'
import { detectAnomalies, buildAnalysisPackage, type AnomalyScenario } from '../../lib/engine'
import type { ControlLimits } from '../../lib/engine'

const NUMERIC_TYPES = new Set(['int64', 'float64', 'int', 'float'])

const TYPE_COLOR: Record<string, string> = {
  spec: 'red',
  control: 'orange',
  engineering: 'blue',
}

const DIRECTION_COLOR: Record<string, string> = {
  above: 'volcano',
  below: 'cyan',
  run: 'purple',
  deviation: 'geekblue',
}

export default function ProcessDefine() {
  const { t } = useTranslation()
  const {
    importResult,
    fields,
    spec,
    controlLimits,
    anomalyScenarios,
    analysisPackage,
    setSpec,
    setControlLimit,
    setAnomalyScenarios,
    confirmAnomaly,
    confirmAllAnomalies,
    setAnalysisPackage,
  } = useDataPipelineStore()

  const [outputField, setOutputField] = useState<string | undefined>(spec?.outputField)
  const [unit, setUnit] = useState<string>(spec?.unit ?? '')
  const [lsl, setLsl] = useState<number | null>(spec?.lsl ?? null)
  const [usl, setUsl] = useState<number | null>(spec?.usl ?? null)
  const [target, setTarget] = useState<number | null>(spec?.target ?? null)
  const [inputUnits, setInputUnits] = useState<Record<string, string>>(spec?.inputUnits ?? {})
  const [error, setError] = useState<string | null>(null)

  // Manual control limit overrides per input field.
  const [manualLimits, setManualLimits] = useState<Record<string, ControlLimits>>({})
  // Detecting state.
  const [detecting, setDetecting] = useState(false)
  const [detectError, setDetectError] = useState<string | null>(null)

  const outputCandidates = useMemo(() => {
    if (!importResult) return []
    const stats = importResult.stats.column_stats
    return fields
      .filter((f) => f.role === 'output' || f.role === 'quality_label')
      .map((f) => f.originalName)
      .filter((name) => {
        const s = stats[name]
        return s?.numeric || NUMERIC_TYPES.has(fields.find((f) => f.originalName === name)?.dataType ?? '')
      })
  }, [importResult, fields])

  const inputs = useMemo(
    () => fields.filter((f) => f.role === 'input').map((f) => f.originalName),
    [fields],
  )

  const requiresData = !importResult || fields.length === 0
  const noOutputCandidates = !requiresData && outputCandidates.length === 0

  const validate = () => {
    if (!outputField) return t('processDefine.errNoOutput')
    if (lsl != null && usl != null && lsl >= usl) return t('processDefine.errLSL')
    if (target != null && lsl != null && target < lsl) return t('processDefine.errTargetBelow')
    if (target != null && usl != null && target > usl) return t('processDefine.errTargetAbove')
    return null
  }

  const handleSave = () => {
    const message = validate()
    if (message) {
      setError(message)
      return
    }
    setError(null)
    const cfg: SpecConfiguration = {
      outputField: outputField as string,
      unit: unit || null,
      lsl,
      usl,
      target,
      inputUnits,
    }
    setSpec(cfg)
  }

  /** Run anomaly detection via engine and store results. */
  const handleDetect = async () => {
    if (!importResult || !spec?.outputField) return
    setDetecting(true)
    setDetectError(null)
    try {
      const result = await detectAnomalies({
        dataset_id: importResult.dataset_id,
        spec: {
          output_field: spec.outputField,
          lsl: spec.lsl,
          usl: spec.usl,
          target: spec.target,
        },
        control_limits: Object.fromEntries(
          Object.entries(controlLimits).filter(([, v]) => v !== null),
        ) as Record<string, ControlLimits>,
        runs_length: 5,
      })
      setAnomalyScenarios(result.scenarios)
      // Build analysis package
      const roleMap: Record<string, string> = {}
      for (const f of fields) {
        roleMap[f.originalName] = f.role
      }
      const pkg = await buildAnalysisPackage({
        dataset_id: importResult.dataset_id,
        field_roles: roleMap,
        spec: { output_field: spec.outputField, lsl: spec.lsl, usl: spec.usl, target: spec.target },
        anomalies: result.scenarios,
        confirmed_roles: fields.filter((f) => f.confirmed).map((f) => f.originalName),
      })
      setAnalysisPackage(pkg)
    } catch (err) {
      setDetectError(String(err))
    } finally {
      setDetecting(false)
    }
  }

  /** Save a single field's manual control limits and sync to store. */
  const handleSaveLimit = (fieldName: string) => {
    const lim = manualLimits[fieldName]
    if (lim && lim.lcl == null && lim.ucl == null) {
      setControlLimit(fieldName, null) // fully empty -> treat as auto
    } else {
      setControlLimit(fieldName, lim ?? null)
    }
  }

  const inputColumns: ColumnsType<{ name: string }> = [
    {
      title: t('processDefine.inputName'),
      dataIndex: 'name',
      key: 'name',
      render: (name: string) => <Typography.Text strong>{name}</Typography.Text>,
    },
    {
      title: t('processDefine.unit'),
      dataIndex: 'unit',
      key: 'unit',
      width: 180,
      render: (_: unknown, record) => (
        <Input
          size="small"
          placeholder={t('processDefine.unitPlaceholder')}
          value={inputUnits[record.name] ?? ''}
          onChange={(e) =>
            setInputUnits((prev) => ({ ...prev, [record.name]: e.target.value }))
          }
        />
      ),
    },
  ]

  const limitColumns: ColumnsType<{ name: string }> = [
    {
      title: t('processDefine.inputName'),
      dataIndex: 'name',
      key: 'name',
      render: (name: string) => <Typography.Text strong>{name}</Typography.Text>,
    },
    {
      title: t('processDefine.lcl'),
      dataIndex: 'lcl',
      key: 'lcl',
      width: 130,
      render: (_: unknown, record) => {
        const stored = controlLimits[record.name]
        return (
          <InputNumber
            size="small"
            placeholder={stored?.lcl != null ? String(stored.lcl) : t('processDefine.lclPlaceholder')}
            style={{ width: '100%' }}
            value={manualLimits[record.name]?.lcl ?? stored?.lcl ?? undefined}
            onChange={(v) =>
              setManualLimits((prev) => ({
                ...prev,
                [record.name]: { lcl: v ?? null, ucl: prev[record.name]?.ucl ?? null },
              }))
            }
            onBlur={() => handleSaveLimit(record.name)}
          />
        )
      },
    },
    {
      title: t('processDefine.ucl'),
      dataIndex: 'ucl',
      key: 'ucl',
      width: 130,
      render: (_: unknown, record) => {
        const stored = controlLimits[record.name]
        return (
          <InputNumber
            size="small"
            placeholder={stored?.ucl != null ? String(stored.ucl) : t('processDefine.uclPlaceholder')}
            style={{ width: '100%' }}
            value={manualLimits[record.name]?.ucl ?? stored?.ucl ?? undefined}
            onChange={(v) =>
              setManualLimits((prev) => ({
                ...prev,
                [record.name]: { lcl: prev[record.name]?.lcl ?? null, ucl: v ?? null },
              }))
            }
            onBlur={() => handleSaveLimit(record.name)}
          />
        )
      },
    },
    {
      title: '',
      key: 'auto',
      width: 90,
      render: (_: unknown, __: unknown) => (
        <Tooltip title={t('processDefine.auto3sigma')}>
          <Tag color="default" style={{ cursor: 'pointer' }}>
            <InfoCircleOutlined /> 3σ
          </Tag>
        </Tooltip>
      ),
    },
  ]

  const scenarioColumns: ColumnsType<AnomalyScenario> = [
    {
      title: t('processDefine.anomalyId'),
      dataIndex: 'anomaly_id',
      key: 'id',
      width: 90,
    },
    {
      title: t('processDefine.anomalyName'),
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: t('processDefine.scenarioType'),
      dataIndex: 'type',
      key: 'type',
      width: 100,
      render: (type: string) => (
        <Tag color={TYPE_COLOR[type] ?? 'default'}>{t(`processDefine.type${type.charAt(0).toUpperCase() + type.slice(1)}`) ?? type}</Tag>
      ),
    },
    {
      title: t('processDefine.scenarioDirection'),
      dataIndex: 'direction',
      key: 'direction',
      width: 110,
      render: (dir: string) => (
        <Tag color={DIRECTION_COLOR[dir] ?? 'default'}>{t(`processDefine.direction${dir.charAt(0).toUpperCase() + dir.slice(1)}`) ?? dir}</Tag>
      ),
    },
    {
      title: t('processDefine.scenarioProbability'),
      dataIndex: 'occurrence_probability',
      key: 'probability',
      width: 100,
      render: (p: number) => `${(p * 100).toFixed(1)}%`,
    },
    {
      title: t('processDefine.scenarioConfidence'),
      dataIndex: 'confidence',
      key: 'confidence',
      width: 90,
      render: (c: number) => `${(c * 100).toFixed(0)}%`,
    },
    {
      title: t('processDefine.scenarioSource'),
      dataIndex: 'source',
      key: 'source',
      width: 160,
      ellipsis: true,
    },
    {
      title: t('processDefine.anomalyAction'),
      key: 'action',
      width: 110,
      render: (_: unknown, record) =>
        record.user_confirmed ? (
          <Tag color="green">{t('processDefine.statusConfirmed')}</Tag>
        ) : (
          <Button size="small" type="link" onClick={() => confirmAnomaly(record.anomaly_id)}>
            {t('common.confirm')}
          </Button>
        ),
    },
  ]

  const unconfirmedCount = anomalyScenarios.filter((s) => !s.user_confirmed).length

  if (requiresData) {
    return (
      <Card title={t('processDefine.title')}>
        <Alert type="info" showIcon message={t('processDefine.noData')} />
      </Card>
    )
  }

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      {/* Output & Spec Limits */}
      <Card title={t('processDefine.outputTitle')} extra={<Tag color="purple">{t('processDefine.output')}</Tag>}>
        <Form layout="vertical" style={{ maxWidth: 720 }}>
          <Form.Item label={t('processDefine.outputField')} required>
            <Select
              placeholder={t('processDefine.outputPlaceholder')}
              value={outputField}
              onChange={setOutputField}
              options={outputCandidates.map((name) => ({ value: name, label: name }))}
            />
            {noOutputCandidates && (
              <Typography.Text type="warning" style={{ display: 'block', marginTop: 8 }}>
                {t('processDefine.noOutputHint')}
              </Typography.Text>
            )}
          </Form.Item>
          <Form.Item label={t('processDefine.unit')}>
            <Input
              placeholder={t('processDefine.unitPlaceholder')}
              value={unit}
              onChange={(e) => setUnit(e.target.value)}
            />
          </Form.Item>
          <Space size="middle" align="start">
            <Form.Item label={t('processDefine.lsl')}>
              <InputNumber value={lsl} onChange={(v) => setLsl(v)} />
            </Form.Item>
            <Form.Item label={t('processDefine.target')}>
              <InputNumber value={target} onChange={(v) => setTarget(v)} />
            </Form.Item>
            <Form.Item label={t('processDefine.usl')}>
              <InputNumber value={usl} onChange={(v) => setUsl(v)} />
            </Form.Item>
          </Space>
          <Alert type="info" showIcon message={t('processDefine.specConstraintHint')} />
        </Form>
      </Card>

      {/* Input Parameters */}
      <Card title={t('processDefine.inputsTitle')} extra={<Tag color="geekblue">{t('processDefine.input')}</Tag>}>
        {inputs.length === 0 ? (
          <Alert type="info" showIcon message={t('processDefine.nothing')} />
        ) : (
          <Table size="small" rowKey="name" columns={inputColumns} dataSource={inputs.map((name) => ({ name }))} pagination={false} />
        )}
      </Card>

      {/* Control Limits */}
      {spec && inputs.length > 0 && (
        <Card title={t('processDefine.controlLimitsTitle')} extra={<Tag color="volcano">{t('processDefine.input')}</Tag>}>
          <Alert
            type="info"
            showIcon
            message={t('processDefine.controlLimitsHint')}
            style={{ marginBottom: 16 }}
          />
          <Table
            size="small"
            rowKey="name"
            columns={limitColumns}
            dataSource={inputs.map((name) => ({ name }))}
            pagination={false}
          />
        </Card>
      )}

      {/* Error display */}
      {error && <Alert type="error" showIcon message={error} />}

      {spec && !error && (
        <Alert
          type="success"
          showIcon
          message={t('processDefine.statusSummary', {
            output: spec.outputField,
            lsl: spec.lsl ?? '—',
            usl: spec.usl ?? '—',
          })}
        />
      )}

      <Space>
        <Button type="primary" icon={<CheckOutlined />} onClick={handleSave}>
          {t('processDefine.saveSpec')}
        </Button>
      </Space>

      {/* Anomaly Detection (available once spec is saved) */}
      {spec && (
        <Card
          title={
            <Space>
              {t('processDefine.anomalyTitle')}
              {unconfirmedCount > 0 && <Badge count={unconfirmedCount} />}
            </Space>
          }
        >
          <Alert type="info" showIcon message={t('processDefine.anomalyHint')} style={{ marginBottom: 16 }} />
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            loading={detecting}
            onClick={handleDetect}
            style={{ marginBottom: 16 }}
          >
            {t('processDefine.runDetection')}
          </Button>

          {detectError && <Alert type="error" showIcon message={detectError} style={{ marginBottom: 16 }} />}

          {anomalyScenarios.length > 0 && (
            <>
              <Table<AnomalyScenario>
                size="small"
                rowKey="anomaly_id"
                columns={scenarioColumns}
                dataSource={anomalyScenarios}
                pagination={false}
                rowClassName={(record) => (record.user_confirmed ? '' : 'ant-table-row-warning')}
              />
              <div style={{ marginTop: 12 }}>
                <Popconfirm
                  title={t('processDefine.confirmAll')}
                  onConfirm={confirmAllAnomalies}
                  disabled={unconfirmedCount === 0}
                >
                  <Button disabled={unconfirmedCount === 0}>
                    {t('processDefine.confirmAll')} ({unconfirmedCount})
                  </Button>
                </Popconfirm>
              </div>
            </>
          )}
        </Card>
      )}

      {/* Analysis Package Summary Card */}
      {analysisPackage && (
        <Card
          title={t('processDefine.analysisPkgTitle')}
          extra={
            analysisPackage.complete ? (
              <Tag color="green">{t('common.confirmed')}</Tag>
            ) : (
              <Tag color="orange">{t('common.pendingConfirm')}</Tag>
            )
          }
        >
          {analysisPackage.complete ? (
            <Alert type="success" showIcon message={t('processDefine.analysisPkgComplete')} />
          ) : (
            <Alert
              type="warning"
              showIcon
              message={t('processDefine.analysisPkgIncomplete', {
                missing: analysisPackage.missing_requirements.join(', '),
              })}
            />
          )}
          <Space direction="vertical" size={8} style={{ marginTop: 12, width: '100%' }}>
            <Typography.Text>
              {t('processDefine.analysisPkgRowCol', {
                rows: analysisPackage.data.row_count,
                columns: analysisPackage.data.column_count,
              })}
            </Typography.Text>
            <Typography.Text>
              {t('processDefine.analysisPkgFields', {
                count: analysisPackage.data.confirmed_field_count,
              })}
            </Typography.Text>
            <Typography.Text>
              {t('processDefine.analysisPkgSpec')}:{' '}
              {analysisPackage.spec.output_field
                ? `${analysisPackage.spec.output_field} [${analysisPackage.spec.lsl ?? '—'} ~ ${analysisPackage.spec.usl ?? '—'}]`
                : '—'}
            </Typography.Text>
            <Typography.Text>
              {t('processDefine.analysisPkgAnomalies', {
                count: analysisPackage.anomalies.length,
              })}
            </Typography.Text>
          </Space>
        </Card>
      )}
    </Space>
  )
}
