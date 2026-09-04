import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Card,
  Typography,
  Button,
  Space,
  Alert,
  Spin,
  Table,
  Tag,
  Input,
  Empty,
  Tooltip,
} from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import {
  getDataAssets,
  detectFields,
  type DataAsset,
  type DetectedField,
} from '../../lib/engine'
import { useAssistantContextStore } from '../../stores/assistantContextStore'

const NOTES_KEY = 'dataAssets.notes.v1'

interface StoredMeta {
  [dataset_id: string]: { notes?: string; tags?: string }
}

function readStored(): StoredMeta {
  try {
    return JSON.parse(localStorage.getItem(NOTES_KEY) ?? '{}') as StoredMeta
  } catch {
    return {}
  }
}

export default function DataAssets() {
  const { t } = useTranslation()
  const { setContext } = useAssistantContextStore()

  const [assets, setAssets] = useState<DataAsset[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [fields, setFields] = useState<DetectedField[]>([])
  const [fieldsLoading, setFieldsLoading] = useState(false)
  const [stored, setStored] = useState<StoredMeta>(readStored)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getDataAssets()
      setAssets(res.datasets)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    setContext('dataAssets', assets.length
      ? `${assets.length} data asset(s); ${assets.map((a) => a.file_path).join('; ')}`
      : 'No data assets registered')
  }, [assets, setContext])

  const persist = (next: StoredMeta) => {
    setStored(next)
    localStorage.setItem(NOTES_KEY, JSON.stringify(next))
  }

  const handleExpand = async (id: string) => {
    if (expanded === id) {
      setExpanded(null)
      setFields([])
      return
    }
    setExpanded(id)
    setFieldsLoading(true)
    try {
      const res = await detectFields([], id)
      setFields(res.fields)
    } catch {
      setFields([])
    } finally {
      setFieldsLoading(false)
    }
  }

  const expression = (asset: DataAsset) => {
    const path = asset.file_path.split(/[\\/]/)
    return path[path.length - 1] || asset.file_path
  }

  return (
    <Card
      title={t('dataAssets.title')}
      extra={
        <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
          {t('dataAssets.refresh')}
        </Button>
      }
    >
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        {t('dataAssets.description')}
      </Typography.Paragraph>

      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}

      {loading ? (
        <Spin />
      ) : assets.length === 0 ? (
        <Empty description={t('dataAssets.empty')} />
      ) : (
        <Table<DataAsset>
          rowKey="dataset_id"
          size="middle"
          loading={loading}
          dataSource={assets}
          pagination={{ pageSize: 10, showSizeChanger: false }}
          expandable={{
            expandedRowKeys: expanded ? [expanded] : [],
            onExpand: (_, record) => handleExpand(record.dataset_id),
            expandedRowRender: (record) => (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Input
                  placeholder={t('dataAssets.notesPlaceholder')}
                  value={stored[record.dataset_id]?.notes ?? ''}
                  onChange={(e) =>
                    persist({
                      ...stored,
                      [record.dataset_id]: {
                        ...stored[record.dataset_id],
                        notes: e.target.value,
                      },
                    })
                  }
                />
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {t('dataAssets.fieldRoles')}
                  </Typography.Text>
                  {fieldsLoading ? (
                    <Spin size="small" />
                  ) : fields.length === 0 ? (
                    <Typography.Text type="secondary">
                      {t('dataAssets.noFields')}
                    </Typography.Text>
                  ) : (
                    <Space wrap size={[4, 4]}>
                      {fields.map((f) => (
                        <Tooltip key={f.name} title={f.reason.join(' · ')}>
                          <Tag color="blue" style={{ cursor: 'help' }}>
                            {f.name}: {f.role}
                          </Tag>
                        </Tooltip>
                      ))}
                    </Space>
                  )}
                </Space>
              </Space>
            ),
          }}
          columns={[
            {
              title: t('dataAssets.col.file'),
              dataIndex: 'file_path',
              key: 'file_path',
              render: (_, r) => <Typography.Text strong>{expression(r)}</Typography.Text>,
            },
            {
              title: t('dataAssets.col.format'),
              dataIndex: 'format',
              key: 'format',
              width: 90,
              render: (v: string) => <Tag>{v}</Tag>,
            },
            {
              title: t('dataAssets.col.encoding'),
              dataIndex: 'encoding',
              key: 'encoding',
              width: 100,
            },
            {
              title: t('dataAssets.col.rows'),
              dataIndex: 'row_count',
              key: 'row_count',
              width: 90,
              align: 'right' as const,
            },
            {
              title: t('dataAssets.col.columns'),
              dataIndex: 'column_count',
              key: 'column_count',
              width: 90,
              align: 'right' as const,
            },
            {
              title: t('dataAssets.col.notes'),
              key: 'notes',
              width: 160,
              render: (_, r) => stored[r.dataset_id]?.notes ?? '—',
            },
            {
              title: t('dataAssets.col.tags'),
              key: 'tags',
              width: 140,
              render: (_, r) =>
                stored[r.dataset_id]?.tags ? (
                  <Tag color="green">{stored[r.dataset_id]?.tags}</Tag>
                ) : (
                  <Typography.Text type="secondary">—</Typography.Text>
                ),
            },
          ]}
        />
      )}
    </Card>
  )
}
