import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, Table, Select, Button, Space, Alert, Tag, message, Popconfirm } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { ExperimentOutlined } from '@ant-design/icons'
import { useDataPipelineStore } from '../../stores/dataPipelineStore'
import { useModelStore } from '../../stores/modelStore'
import type { ModelFitDTO, ModelType, ModelStatus } from '../../lib/engine'

const MODEL_TYPES: { value: ModelType; labelKey: string }[] = [
  { value: 'doe_linear', labelKey: 'modelCenter.modelType.doeLinear' },
  { value: 'doe_quadratic', labelKey: 'modelCenter.modelType.doeQuadratic' },
  { value: 'random_forest', labelKey: 'modelCenter.modelType.randomForest' },
  { value: 'residual_hybrid', labelKey: 'modelCenter.modelType.residualHybrid' },
]

const STATUS_TRANSITIONS: Partial<Record<ModelStatus, ModelStatus[]>> = {
  draft: ['pending_validation'],
  pending_validation: ['validated'],
  validated: ['approved'],
  approved: ['retired'],
}

const STATUS_COLORS: Record<ModelStatus, string> = {
  draft: 'default',
  pending_validation: 'processing',
  validated: 'success',
  approved: 'gold',
  retired: 'error',
}

export default function ModelCenter() {
  const { t } = useTranslation()
  const [messageApi, contextHolder] = message.useMessage()
  const { importResult, fields, spec } = useDataPipelineStore()
  const {
    models, fitting, transitioning, error,
    selectedModelId, loadModels, fit, transition,
    selectModel, clearError,
  } = useModelStore()

  const [modelType, setModelType] = useState<ModelType>('doe_linear')
  const [selectedInputs, setSelectedInputs] = useState<string[]>([])
  const [target, setTarget] = useState<string | undefined>(spec?.outputField || undefined)

  const datasetId = importResult?.dataset_id
  const inputOptions = fields
    .filter((f) => f.role === 'input')
    .map((f) => ({ label: f.originalName, value: f.originalName }))
  const outputOptions = fields
    .filter((f) => f.role === 'output')
    .map((f) => ({ label: f.originalName, value: f.originalName }))

  useEffect(() => { loadModels() }, [])

  const handleFit = async () => {
    if (!datasetId || !target || selectedInputs.length === 0) return
    const result = await fit({ dataset_id: datasetId, model_type: modelType, target, inputs: selectedInputs })
    if (result) {
      messageApi.success(t('modelCenter.fitSuccess'))
    }
  }

  const handleTransition = async (modelId: string, newStatus: ModelStatus) => {
    await transition(modelId, newStatus)
    messageApi.success(t('modelCenter.transitionSuccess', { status: newStatus }))
  }

  if (!datasetId) {
    return (
      <Card title={t('modelCenter.title')}>
        <Alert type="info" showIcon message={t('modelCenter.noData')} />
      </Card>
    )
  }

  const columns: ColumnsType<ModelFitDTO> = [
    { title: t('modelCenter.column.type'), dataIndex: 'model_type', key: 'type', width: 150 },
    { title: t('modelCenter.column.version'), dataIndex: 'version', key: 'version', width: 80 },
    {
      title: t('modelCenter.column.status'), dataIndex: 'status', key: 'status', width: 160,
      render: (status: ModelStatus) => <Tag color={STATUS_COLORS[status]}>{status}</Tag>,
    },
    { title: 'R²', dataIndex: ['metrics', 'r2'], key: 'r2', width: 100, render: (v: number) => v?.toFixed(4) },
    { title: 'RMSE', dataIndex: ['metrics', 'rmse'], key: 'rmse', width: 100, render: (v: number) => v?.toFixed(4) },
    { title: 'MAE', dataIndex: ['metrics', 'mae'], key: 'mae', width: 100, render: (v: number) => v?.toFixed(4) },
    { title: 'Adj R²', dataIndex: ['metrics', 'adj_r2'], key: 'adj_r2', width: 100, render: (v: number) => v?.toFixed(4) },
    {
      title: t('modelCenter.column.actions'), key: 'actions', width: 200,
      render: (_, record) => {
        const nextStatuses = STATUS_TRANSITIONS[record.status] || []
        return (
          <Space size="small">
            {nextStatuses.map((s) => (
              <Popconfirm key={s} title={t('modelCenter.confirmTransition', { status: s })} onConfirm={() => handleTransition(record.model_id, s)}>
                <Button size="small" loading={transitioning}>{s}</Button>
              </Popconfirm>
            ))}
          </Space>
        )
      },
    },
  ]

  return (
    <>
      {contextHolder}
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {error && <Alert type="error" showIcon message={error} closable onClose={clearError} />}

        <Card title={t('modelCenter.fitTitle')} extra={<ExperimentOutlined />}>
          <Space direction="vertical" style={{ width: '100%' }}>
            <div>
              <label>{t('modelCenter.modelType.label')}</label>
              <Select
                style={{ width: 240, marginLeft: 8 }}
                value={modelType}
                onChange={setModelType}
                options={MODEL_TYPES.map((m) => ({ value: m.value, label: t(m.labelKey) }))}
              />
            </div>
            <div>
              <label>{t('modelCenter.target.label')}</label>
              <Select
                style={{ width: 240, marginLeft: 8 }}
                value={target}
                onChange={setTarget}
                options={outputOptions}
                placeholder={t('modelCenter.target.placeholder')}
              />
            </div>
            <div>
              <label>{t('modelCenter.inputs.label')}</label>
              <Select
                mode="multiple"
                style={{ width: 400, marginLeft: 8 }}
                value={selectedInputs}
                onChange={setSelectedInputs}
                options={inputOptions}
                placeholder={t('modelCenter.inputs.placeholder')}
              />
            </div>
            <Button type="primary" loading={fitting} onClick={handleFit} disabled={!datasetId || !target || selectedInputs.length === 0}>
              {t('modelCenter.fitButton')}
            </Button>
          </Space>
        </Card>

        <Card title={t('modelCenter.listTitle')} size="small">
          <Table
            size="small"
            rowKey="model_id"
            columns={columns}
            dataSource={models}
            pagination={false}
            rowClassName={(r) => (r.model_id === selectedModelId ? 'ant-table-row-selected' : '')}
            onRow={(record) => ({ onClick: () => selectModel(record.model_id) })}
          />
        </Card>
      </Space>
    </>
  )
}
