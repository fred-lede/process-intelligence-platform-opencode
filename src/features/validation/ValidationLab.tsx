import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Card, Table, Button, Space, Alert, Tag, Input, Select,
  Form, InputNumber, message, Typography,
  Statistic, Row, Col, Divider,
} from 'antd'
import {
  ExperimentOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ThunderboltOutlined,
  SaveOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  runFullValidation,
  recordExperiment,
  listExperiments,
  getModelInfo,
  type ExperimentRecord,
  type FullValidationResult,
} from '../../lib/engine'
import { useDataPipelineStore } from '../../stores/dataPipelineStore'
import { useModelStore } from '../../stores/modelStore'

const PRIORITY_COLORS: Record<string, string> = {
  high: 'red',
  medium: 'orange',
  low: 'default',
}

export default function ValidationLab() {
  const { t } = useTranslation()
  const { importResult } = useDataPipelineStore()
  const { models, loadModels } = useModelStore()
  const [messageApi, contextHolder] = message.useMessage()

  const [fullValidation, setFullValidation] = useState<FullValidationResult | null>(null)
  const [fullValidationLoading, setFullValidationLoading] = useState(false)
  const [experiments, setExperiments] = useState<ExperimentRecord[]>([])
  const [experimentsLoading, setExperimentsLoading] = useState(false)
  const [selectedModelId, setSelectedModelId] = useState<string | undefined>()
  const [modelInfo, setModelInfo] = useState<{ equation: string; inputs: string[]; model_type: string } | null>(null)

  const [form] = Form.useForm()
  const [submitting, setSubmitting] = useState(false)

  const datasetId = importResult?.dataset_id

  useEffect(() => {
    loadModels()
  }, [loadModels])

  useEffect(() => {
    if (models.length > 0 && !selectedModelId) {
      setSelectedModelId(models[0].model_id)
    }
  }, [models, selectedModelId])

  useEffect(() => {
    if (selectedModelId) {
      loadExperiments(selectedModelId)
      loadModelInfo(selectedModelId)
    }
  }, [selectedModelId])

  const loadExperiments = async (modelId: string) => {
    setExperimentsLoading(true)
    try {
      const result = await listExperiments({ model_id: modelId })
      setExperiments(result.experiments)
    } catch {
      setExperiments([])
    } finally {
      setExperimentsLoading(false)
    }
  }

  const loadModelInfo = async (modelId: string) => {
    try {
      const info = await getModelInfo({ model_id: modelId })
      if (info.success) {
        setModelInfo({ equation: info.equation, inputs: info.inputs, model_type: info.model_type })
      }
    } catch {
      // ignore
    }
  }

  const handleRunFullValidation = async () => {
    if (!datasetId) return
    setFullValidationLoading(true)
    try {
      const result = await runFullValidation({ dataset_id: datasetId })
      setFullValidation(result)
      messageApi.success(t('validationLab.fullValidationSuccess'))
    } catch {
      messageApi.error(t('validationLab.fullValidationError'))
    } finally {
      setFullValidationLoading(false)
    }
  }

  const handleSubmitExperiment = async (values: {
    planned_inputs: Record<string, number>
    actual_inputs: Record<string, number>
    predicted_output: number
    actual_output: number
    result: 'pass' | 'fail' | 'inconclusive' | 'unknown'
    operator: string
    notes: string
  }) => {
    if (!selectedModelId) return
    setSubmitting(true)
    try {
      const result = await recordExperiment({
        model_id: selectedModelId,
        planned_inputs: values.planned_inputs,
        actual_inputs: values.actual_inputs,
        predicted_output: values.predicted_output,
        actual_output: values.actual_output,
        result: values.result,
        operator: values.operator || 'anonymous',
        notes: values.notes,
      })
      messageApi.success(
        t('validationLab.recordSuccess', { error: Math.abs(result.prediction_error).toFixed(4) })
      )
      form.resetFields()
      if (selectedModelId) loadExperiments(selectedModelId)
    } catch {
      messageApi.error(t('validationLab.recordError'))
    } finally {
      setSubmitting(false)
    }
  }

  const experimentColumns: ColumnsType<ExperimentRecord> = [
    {
      title: t('validationLab.column.time'),
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 160,
      render: (v: string) => new Date(v).toLocaleString(),
    },
    {
      title: t('validationLab.column.operator'),
      dataIndex: 'operator',
      key: 'operator',
      width: 100,
    },
    {
      title: t('validationLab.column.result'),
      dataIndex: 'result',
      key: 'result',
      width: 90,
      render: (v: string) => (
        <Tag color={v === 'pass' ? 'success' : v === 'fail' ? 'error' : v === 'inconclusive' ? 'warning' : 'default'}>
          {v === 'pass' ? t('validationLab.result.pass') : v === 'fail' ? t('validationLab.result.fail') : v === 'inconclusive' ? t('validationLab.result.inconclusive') : t('validationLab.result.unknown')}
        </Tag>
      ),
    },
    {
      title: t('validationLab.column.predError'),
      dataIndex: 'prediction_error',
      key: 'prediction_error',
      width: 100,
      render: (v: number) => (
        <span style={{ color: Math.abs(v) < 0.1 ? '#16a34a' : '#dc2626', fontWeight: 600 }}>
          {v >= 0 ? '+' : ''}{v.toFixed(4)}
        </span>
      ),
    },
    {
      title: t('validationLab.column.predicted'),
      dataIndex: 'predicted_output',
      key: 'predicted_output',
      width: 90,
      render: (v: number) => v.toFixed(4),
    },
    {
      title: t('validationLab.column.actual'),
      dataIndex: 'actual_output',
      key: 'actual_output',
      width: 90,
      render: (v: number) => v.toFixed(4),
    },
    {
      title: t('validationLab.column.notes'),
      dataIndex: 'notes',
      key: 'notes',
      ellipsis: true,
    },
  ]

  const passRate = experiments.length > 0
    ? (experiments.filter((e) => e.result === 'pass').length / experiments.length) * 100
    : 0

  const avgError = experiments.length > 0
    ? experiments.reduce((sum, e) => sum + Math.abs(e.prediction_error), 0) / experiments.length
    : 0

  return (
    <Space direction="vertical" style={{ width: '100%' }} size={16}>
      {contextHolder}

      {/* Model selector */}
      <Card size="small" title={t('validationLab.modelSelect')}>
        <Space>
          <Select
            value={selectedModelId}
            onChange={setSelectedModelId}
            options={models.map((m) => ({
              label: `${m.model_type} (v${m.version})`,
              value: m.model_id,
            }))}
            style={{ width: 240 }}
            placeholder={t('validationLab.selectModel')}
            disabled={models.length === 0}
          />
          {modelInfo && (
            <Tag color="blue">{modelInfo.model_type}</Tag>
          )}
          {modelInfo && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {modelInfo.equation}
            </Typography.Text>
          )}
        </Space>
      </Card>

      {/* Full validation */}
      <Card
        size="small"
        title={
          <Space>
            <ThunderboltOutlined />
            {t('validationLab.fullValidationTitle')}
          </Space>
        }
        extra={
          <Button
            type="primary"
            loading={fullValidationLoading}
            icon={<ReloadOutlined />}
            onClick={handleRunFullValidation}
            disabled={models.length === 0 || !datasetId}
          >
            {fullValidationLoading ? t('validationLab.running') : t('validationLab.runFullValidation')}
          </Button>
        }
      >
        {fullValidation ? (
          <Space direction="vertical" style={{ width: '100%' }} size={8}>
            <Row gutter={[16, 16]}>
              <Col span={6}>
                <Statistic
                  title={t('validationLab.bestModel')}
                  value={fullValidation.models.find((m) => m.model_id === fullValidation.best_model_id)?.model_type || '-'}
                  suffix={<Tag color="gold">Score: {fullValidation.models.find((m) => m.model_id === fullValidation.best_model_id)?.score.toFixed(4)}</Tag>}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title={t('validationLab.totalModels')}
                  value={fullValidation.models.length}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title={t('validationLab.residualNormal')}
                  value={fullValidation.residual_analysis.durbin_watson.interpretation}
                  suffix={<Tag color={fullValidation.models.some((m) => m.residual_normal) ? 'success' : 'error'}>{fullValidation.models.some((m) => m.residual_normal) ? 'Yes' : 'No'}</Tag>}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title={t('validationLab.durbinWatson')}
                  value={fullValidation.residual_analysis.durbin_watson.statistic.toFixed(3)}
                />
              </Col>
            </Row>

            <Divider style={{ margin: '8px 0' }} />

            <Table
              size="small"
              pagination={false}
              dataSource={fullValidation.models.map((m, idx) => ({ ...m, key: idx }))}
              columns={[
                { title: t('validationLab.column.type'), dataIndex: 'model_type', key: 'model_type', width: 140 },
                {
                  title: 'R²',
                  dataIndex: ['cv_metrics', 'mean_r2'],
                  key: 'r2',
                  render: (v: number) => v?.toFixed(4),
                },
                {
                  title: 'RMSE',
                  dataIndex: ['cv_metrics', 'mean_rmse'],
                  key: 'rmse',
                  render: (v: number) => v?.toFixed(4),
                },
                {
                  title: t('validationLab.normalityTest'),
                  dataIndex: 'residual_normal',
                  key: 'residual_normal',
                  render: (v: boolean) => (
                    <Tag color={v ? 'success' : 'error'}>
                      {v ? t('validationLab.isNormal') : t('validationLab.notNormal')}
                    </Tag>
                  ),
                },
                {
                  title: 'Score',
                  dataIndex: 'score',
                  key: 'score',
                  render: (v: number) => v?.toFixed(4),
                },
                {
                  title: t('credibility.level'),
                  key: 'credibility_level',
                  width: 120,
                  render: (_: unknown, record: { model_id: string }) => {
                    const cred = fullValidation.credibility?.[record.model_id]
                    if (!cred) return '-'
                    const levelColors: Record<string, string> = {
                      production_ready: 'success',
                      engineering_reference: 'processing',
                      exploratory: 'warning',
                      needs_more_data: 'error',
                      not_recommended: 'default',
                    }
                    return (
                      <Tag color={levelColors[cred.level] || 'default'}>
                        {t(`credibility.${cred.level}`) || cred.level}
                      </Tag>
                    )
                  },
                },
              ]}
            />

            {/* Credibility detail */}
            {Object.entries(fullValidation.credibility || {}).length > 0 && (
              <Card size="small" title={t('credibility.title')} style={{ marginTop: 8 }}>
                <Row gutter={[8, 8]}>
                  {Object.entries(fullValidation.credibility).map(([modelId, cred]) => {
                    const model = fullValidation.models.find(m => m.model_id === modelId)
                    const levelColors: Record<string, string> = {
                      production_ready: '#16a34a',
                      engineering_reference: '#2563eb',
                      exploratory: '#ca8a04',
                      needs_more_data: '#dc2626',
                      not_recommended: '#6b7280',
                    }
                    return (
                      <Col span={12} key={modelId}>
                        <div style={{ marginBottom: 8 }}>
                          <Typography.Text strong style={{ fontSize: 12 }}>{model?.model_type || modelId}</Typography.Text>
                          <div style={{ fontSize: 20, fontWeight: 700, color: levelColors[cred.level] || '#6b7280' }}>
                            {cred.composite.toFixed(3)}
                          </div>
                          <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                            {t(`credibility.${cred.level}`) || cred.level}
                          </Typography.Text>
                        </div>
                        <div style={{ fontSize: 11, color: '#6b7280' }}>
                          <div>{t('credibility.dataCoverage')}: {(cred.data_coverage * 100).toFixed(0)}%</div>
                          <div>{t('credibility.predictiveAcc')}: {(cred.predictive_acc * 100).toFixed(0)}%</div>
                          <div>{t('credibility.extrapolationRisk')}: {(cred.extrapolation_risk * 100).toFixed(0)}%</div>
                        </div>
                      </Col>
                    )
                  })}
                </Row>
              </Card>
            )}

            {/* Interaction analysis */}
            {fullValidation.interaction_analysis.significant_pairs.length > 0 && (
            <Alert
              type="warning"
              showIcon
              message={t('validationLab.strongInteractions')}
              description={
                  <div>
                    {fullValidation.interaction_analysis.significant_pairs.map((p, i) => (
                      <div key={i} style={{ fontSize: 12 }}>
                        {p.i} × {p.j}: strength = {p.strength.toFixed(3)}
                      </div>
                    ))}
                  </div>
                }
              />
            )}

            {/* Experiment recommendations */}
            <div>
              <strong>{t('validationLab.experimentRecommendations')}:</strong>
              {fullValidation.experiment_recommendations.recommendations.map((rec, i) => (
                <Alert
                  key={i}
                  style={{ marginTop: 4 }}
                  type={rec.priority === 'high' ? 'warning' : rec.priority === 'medium' ? 'warning' : 'info'}
                  message={
                    <span>
                      <Tag color={PRIORITY_COLORS[rec.priority]}>{rec.priority}</Tag>
                      {rec.type}: {rec.reason}
                    </span>
                  }
                  showIcon
                />
              ))}
              <div style={{ marginTop: 4, fontSize: 12, color: '#6b7280' }}>
                {fullValidation.experiment_recommendations.summary}
              </div>
            </div>
          </Space>
        ) : (
          <Alert
            type="info"
            showIcon
            message={t('validationLab.fullValidationInfo')}
            description={t('validationLab.fullValidationDesc')}
          />
        )}
      </Card>

      {/* Record experiment */}
      <Card
        size="small"
        title={
          <Space>
            <SaveOutlined />
            {t('validationLab.recordTitle')}
          </Space>
        }
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmitExperiment}
          disabled={!selectedModelId}
        >
          <Row gutter={16}>
            {modelInfo?.inputs.map((inputName) => (
              <>
                <Col span={12} key={`planned_${inputName}`}>
                  <Form.Item
                    name={['planned_inputs', inputName]}
                    label={`${inputName} (planned)`}
                    rules={[{ required: true, message: t('validationLab.required') }]}
                  >
                    <InputNumber style={{ width: '100%' }} precision={4} placeholder="Planned value" />
                  </Form.Item>
                </Col>
                <Col span={12} key={`actual_${inputName}`}>
                  <Form.Item
                    name={['actual_inputs', inputName]}
                    label={`${inputName} (actual)`}
                    rules={[{ required: true, message: t('validationLab.required') }]}
                  >
                    <InputNumber style={{ width: '100%' }} precision={4} placeholder="Actual value" />
                  </Form.Item>
                </Col>
              </>
            ))}
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="predicted_output"
                label={t('validationLab.predictedOutput')}
                rules={[{ required: true, message: t('validationLab.required') }]}
              >
                <InputNumber style={{ width: '100%' }} precision={4} placeholder="Model prediction" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="actual_output"
                label={t('validationLab.actualOutput')}
                rules={[{ required: true, message: t('validationLab.required') }]}
              >
                <InputNumber style={{ width: '100%' }} precision={4} placeholder="Measured output" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item
                name="result"
                label={t('validationLab.resultLabel')}
                rules={[{ required: true, message: t('validationLab.required') }]}
                initialValue="unknown"
              >
                <Select
                  options={[
                    { value: 'pass', label: t('validationLab.result.pass') },
                    { value: 'fail', label: t('validationLab.result.fail') },
                    { value: 'inconclusive', label: t('validationLab.result.inconclusive') },
                    { value: 'unknown', label: t('validationLab.result.unknown') },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="operator"
                label={t('validationLab.operator')}
                initialValue=""
              >
                <Input placeholder="Operator name" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="notes" label={t('validationLab.notes')}>
                <Input placeholder={t('validationLab.notesPlaceholder')} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              loading={submitting}
              icon={<SaveOutlined />}
              disabled={!selectedModelId}
            >
              {t('validationLab.saveExperiment')}
            </Button>
          </Form.Item>
        </Form>
      </Card>

      {/* Experiment results */}
      <Card
        size="small"
        title={
          <Space>
            <ExperimentOutlined />
            {t('validationLab.experimentHistory')}
          </Space>
        }
        extra={
          selectedModelId && (
            <Button
              size="small"
              icon={<ReloadOutlined />}
              loading={experimentsLoading}
              onClick={() => loadExperiments(selectedModelId)}
            >
              {t('validationLab.refresh')}
            </Button>
          )
        }
      >
        {experiments.length > 0 ? (
          <>
            <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
              <Col span={6}>
                <Statistic
                  title={t('validationLab.totalExperiments')}
                  value={experiments.length}
                  prefix={<ExperimentOutlined />}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title={t('validationLab.passRate')}
                  value={passRate.toFixed(1)}
                  suffix="%"
                  valueStyle={{ color: passRate >= 80 ? '#16a34a' : passRate >= 50 ? '#ca8a04' : '#dc2626' }}
                  prefix={passRate >= 80 ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title={t('validationLab.avgAbsError')}
                  value={avgError.toFixed(4)}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title={t('validationLab.passCount')}
                  value={experiments.filter((e) => e.result === 'pass').length}
                  valueStyle={{ color: '#16a34a' }}
                  suffix={` / ${experiments.filter((e) => e.result === 'fail').length} fail`}
                />
              </Col>
            </Row>
            <Table
              size="small"
              loading={experimentsLoading}
              dataSource={experiments}
              columns={experimentColumns}
              rowKey="experiment_id"
              pagination={{ pageSize: 10 }}
            />
          </>
        ) : (
          <Alert
            type="info"
            showIcon
            message={t('validationLab.noExperiments')}
            description={t('validationLab.noExperimentsDesc')}
          />
        )}
      </Card>
    </Space>
  )
}
