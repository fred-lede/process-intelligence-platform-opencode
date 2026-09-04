import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Card,
  Button,
  Space,
  Table,
  Typography,
  Steps,
  Select,
  Tag,
  Alert,
  Tooltip,
  message,
} from 'antd'
import {
  FileExcelOutlined,
  ImportOutlined,
  CheckOutlined,
  ReloadOutlined,
  DownloadOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { pickDataFile } from '../../lib/filePicker'
import {
  importDataFile,
  detectFields,
  runQualityChecks,
  type FieldRole,
  type QualityIssue,
} from '../../lib/engine'
import { useDataPipelineStore, type FieldAssignment } from '../../stores/dataPipelineStore'
import { useAssistantContextStore } from '../../stores/assistantContextStore'
import { buildDataImportContext } from '../../lib/assistantData'

interface DataImportProps {
  onDetected?: () => void
  onFinished?: () => void
}

const ROLE_OPTIONS: { value: FieldRole; color: string }[] = [
  { value: 'identifier', color: 'blue' },
  { value: 'input', color: 'geekblue' },
  { value: 'output', color: 'purple' },
  { value: 'quality_label', color: 'magenta' },
  { value: 'category', color: 'cyan' },
  { value: 'timestamp', color: 'green' },
  { value: 'metadata', color: 'default' },
  { value: 'sensitive', color: 'red' },
  { value: 'excluded', color: 'red' },
]

// Build a sample CSV whose columns auto-detect into roles usable by
// distribution / trend / time-series / GRR analysis.
// GRR structure: 3 operators × 5 parts × 3 reps = 45 rows.
function buildTemplateCsv(): string {
  const header = [
    'lot',
    'serial_no',
    'datetime',
    'machine',
    'operator',
    'part',
    'input_temperature',
    'input_voltage',
    'output_thickness',
    'output_pressure',
    'result',
  ]
  const operators = ['O-01', 'O-02', 'O-03']
  const parts = ['P-01', 'P-02', 'P-03', 'P-04', 'P-05']
  const reps = 3
  const lot = 'L240901-A'
  const machines = ['Line-A', 'Line-B', 'Line-A', 'Line-B', 'Line-A']
  const pad = (n: number) => String(n).padStart(4, '0')

  const rows: string[][] = []
  let seq = 0
  operators.forEach((op, oi) => {
    parts.forEach((part, pi) => {
      const machine = machines[pi]
      const baseBias = (oi - 1) * 0.004
      for (let r = 0; r < reps; r++) {
        seq += 1
        const noise = (Math.random() - 0.5) * 0.012
        const inTemp = (85 + (pi - 2) * 1.2 + (Math.random() - 0.5) * 1.6).toFixed(2)
        const inVoltage = (12 + (pi - 2) * 0.3 + (Math.random() - 0.5) * 0.2).toFixed(3)
        const outThickness = (1.62 + baseBias + noise).toFixed(4)
        const outPressure = (3.4 + (Math.random() - 0.5) * 0.12).toFixed(3)
        const fail = seq % 41 === 0
        const day = 1 + Math.floor(seq / 15)
        const hour = 8 + Math.floor(seq / 3)
        const minute = (seq * 7) % 60
        const datetime = `2026-09-0${day} ${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}:00`
        rows.push([
          lot,
          `SNC-${pad(seq)}`,
          datetime,
          machine,
          op,
          part,
          inTemp,
          inVoltage,
          outThickness,
          outPressure,
          fail ? 'NG' : 'OK',
        ])
      }
    })
  })

  return [header, ...rows].map((r) => r.join(',')).join('\n')
}

export default function DataImport({ onDetected, onFinished }: DataImportProps) {
  const { t } = useTranslation()
  const {
    importResult,
    fields,
    spec,
    quality,
    setImportResult,
    setDetectedFields,
    setQuality,
    updateFieldRole,
    confirmField,
    confirmAllFields,
    resetAll,
  } = useDataPipelineStore()
  const { setContext } = useAssistantContextStore()

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setContext(
      'dataImport',
      buildDataImportContext({
        fields,
        spec,
        rowCount: importResult?.row_count ?? null,
        columnCount: importResult?.column_count ?? null,
      }),
    )
  }, [fields, spec, importResult, setContext])

  const handlePickFile = async () => {
    setError(null)
    const path = await pickDataFile()
    if (!path) return
    setLoading(true)
    try {
      const result = await importDataFile(path)
      setImportResult(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  const handleDownloadTemplate = () => {
    const csv = buildTemplateCsv()
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'process-analysis-template.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleDetect = async () => {
    if (!importResult) return
    setLoading(true)
    setError(null)
    try {
      const columns = importResult.columns.map((name) => {
        // Extract preview values for this column (skip header row).
        const idx = importResult.columns.indexOf(name)
        const values = importResult.raw_preview.slice(1).map((row) => row[idx])
        return { name, values }
      })
      const { fields: detected } = await detectFields(columns)
      setDetectedFields(detected)
      onDetected?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  const handleRunQuality = async (finalFields: FieldAssignment[]) => {
    if (!importResult) return
    setLoading(true)
    setError(null)
    try {
      const report = await runQualityChecks({
        dataset_id: importResult.dataset_id,
        categorical_columns: finalFields
          .filter((f) => f.role === 'category')
          .map((f) => f.originalName),
        quality_columns: finalFields
          .filter((f) => f.role === 'quality_label' || f.role === 'output')
          .map((f) => f.originalName),
        datetime_columns: finalFields
          .filter((f) => f.role === 'timestamp')
          .map((f) => f.originalName),
        batch_columns: [],
        input_columns: finalFields
          .filter((f) => f.role === 'input')
          .map((f) => f.originalName),
        output_columns: finalFields
          .filter((f) => f.role === 'output')
          .map((f) => f.originalName),
      })
      setQuality(report)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  const hasOutputField = () => fields.some((f) => f.role === 'output')

  const handleConfirmAll = () => {
    if (!hasOutputField()) {
      message.error(t('dataImport.errNoOutput'))
      return
    }
    const confirmed = fields.map((f) => ({ ...f, confirmed: true }))
    confirmAllFields()
    void handleRunQuality(confirmed)
  }

  const handleFinish = () => {
    if (!hasOutputField()) {
      message.error(t('dataImport.errNoOutput'))
      return
    }
    onFinished?.()
  }

  const qualityColumns: ColumnsType<QualityIssue> = [
    {
      title: t('dataImport.qualityCheck'),
      dataIndex: 'check',
      key: 'check',
      width: 180,
    },
    {
      title: t('dataImport.column'),
      dataIndex: 'column',
      key: 'column',
      width: 160,
      render: (col: string | null) => col ?? '—',
    },
    {
      title: t('dataImport.qualitySeverity'),
      dataIndex: 'severity',
      key: 'severity',
      width: 120,
      render: (sev: QualityIssue['severity']) => (
        <Tag color={sev === 'critical' ? 'red' : sev === 'warning' ? 'orange' : 'blue'}>
          {sev}
        </Tag>
      ),
    },
    { title: t('dataImport.qualityMessage'), dataIndex: 'message', key: 'message' },
  ]

  const roleLabel = (role: FieldRole) => t(`dataImport.role.${role}`)

  const fieldColumns: ColumnsType<(typeof fields)[number]> | undefined = [
    {
      title: t('dataImport.column'),
      dataIndex: 'originalName',
      key: 'name',
      render: (name: string) => <Typography.Text strong>{name}</Typography.Text>,
    },
    {
      title: t('dataImport.dataType'),
      dataIndex: 'dataType',
      key: 'type',
      width: 120,
    },
    {
      title: t('dataImport.aiRole'),
      dataIndex: 'confidence',
      key: 'confidence',
      width: 140,
      render: (_: unknown, record) => (
        <Tooltip title={record.confidence >= 0.5 ? 'high' : 'low'}>
          <span>{Math.round(record.confidence * 100)}%</span>
        </Tooltip>
      ),
    },
    {
      title: t('dataImport.roleLabel'),
      dataIndex: 'role',
      key: 'role',
      width: 220,
      render: (role: FieldRole, record) => (
        <Select
          size="small"
          style={{ width: 180 }}
          value={role}
          onChange={(newRole) => updateFieldRole(record.originalName, newRole)}
          options={ROLE_OPTIONS.map((r) => ({
            value: r.value,
            label: <Tag color={r.color}>{roleLabel(r.value)}</Tag>,
          }))}
        />
      ),
    },
    {
      title: t('dataImport.status'),
      dataIndex: 'confirmed',
      key: 'confirmed',
      width: 100,
      render: (confirmed: boolean, record) => (
        <Space>
          <Tag color={confirmed ? 'green' : 'orange'}>
            {confirmed ? t('common.confirmed') : t('common.pendingConfirm')}
          </Tag>
          {!confirmed && (
            <Button
              size="small"
              icon={<CheckOutlined />}
              onClick={() => confirmField(record.originalName)}
            />
          )}
        </Space>
      ),
    },
  ]

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Steps
        current={importResult ? (fields.length > 0 ? 3 : 1) : 0}
        size="small"
        items={[
          { title: t('dataImport.stepPick') },
          { title: t('dataImport.stepPreview') },
          { title: t('dataImport.stepDetect') },
          { title: t('dataImport.stepConfirm') },
        ]}
      />

      <Card title={t('dataImport.importSource')}>
        {!importResult ? (
          <Space direction="vertical">
            <Typography.Paragraph type="secondary">
              {t('dataImport.importDescription')}
            </Typography.Paragraph>
            <Button
              type="primary"
              icon={<FileExcelOutlined />}
              loading={loading}
              onClick={handlePickFile}
            >
              {t('dataImport.pickFile')}
            </Button>
            <Tooltip title={t('dataImport.downloadTemplateDesc')}>
              <Button icon={<DownloadOutlined />} onClick={handleDownloadTemplate}>
                {t('dataImport.downloadTemplate')}
              </Button>
            </Tooltip>
          </Space>
        ) : (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Alert
              type="info"
              showIcon
              message={importResult.file_path}
              description={t(
                `dataImport.fileInfo.${importResult.format}`,
                {
                  rows: importResult.row_count,
                  cols: importResult.column_count,
                  encoding: importResult.encoding,
                },
              )}
            />
            <Space>
              <Button onClick={handlePickFile} icon={<ReloadOutlined />}>
                {t('dataImport.pickAnother')}
              </Button>
              <Button
                type="primary"
                icon={<ImportOutlined />}
                loading={loading}
                onClick={handleDetect}
              >
                {t('dataImport.detectFields')}
              </Button>
              <Button onClick={resetAll}>{t('common.cancel')}</Button>
            </Space>
          </Space>
        )}
      </Card>

      {error && (
        <Alert type="error" showIcon message={t('common.error')} description={error} />
      )}

      {importResult && (
        <Card
          title={t('dataImport.previewTitle')}
          size="small"
        >
          <Table
            size="small"
            pagination={{ pageSize: 10, showSizeChanger: false }}
            scroll={{ x: 'max-content' }}
            rowKey="__key"
            dataSource={importResult.raw_preview.slice(1).map((row, i) => {
              const record: Record<string, unknown> = { __key: `row-${i}` }
              importResult.columns.forEach((col, colIdx) => {
                record[col] = row[colIdx]
              })
              return record
            })}
            columns={importResult.columns.map((col) => ({
              title: col,
              dataIndex: col,
              key: col,
              width: 120,
            }))}
          />
        </Card>
      )}

      {fields.length > 0 && (
        <Card title={t('dataImport.fieldRolesTitle')} size="small">
          <Space direction="vertical" style={{ width: '100%' }}>
            <Alert
              type="warning"
              showIcon
              message={t('dataImport.fieldRolesHint')}
            />
            <Table
              size="small"
              rowKey={(record) => record.originalName}
              columns={fieldColumns}
              dataSource={fields}
              pagination={false}
            />
            <Space style={{ justifyContent: 'flex-end', width: '100%' }}>
              <Button onClick={handleConfirmAll} type="primary" icon={<CheckOutlined />} loading={loading}>
                {t('dataImport.confirmAll')}
              </Button>
              <Button onClick={handleFinish}>{t('common.next')}</Button>
            </Space>
          </Space>
        </Card>
      )}

      {quality && (
        <Card title={t('dataImport.qualityTitle')} size="small">
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Alert
              type={quality.issues.some((i) => i.severity === 'critical') ? 'warning' : 'success'}
              showIcon
              message={t('dataImport.qualitySummary', {
                rows: quality.row_count,
                cols: quality.column_count,
                issues: quality.issues.length,
              })}
            />
            {quality.issues.length === 0 ? (
              <Alert type="success" showIcon message={t('dataImport.qualityClean')} />
            ) : (
              <Table
                size="small"
                rowKey={(record) => `${record.check}-${record.column}`}
                columns={qualityColumns}
                dataSource={quality.issues}
                pagination={false}
              />
            )}
          </Space>
        </Card>
      )}
    </Space>
  )
}