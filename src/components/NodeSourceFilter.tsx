import { useTranslation } from 'react-i18next'
import { Alert, Button, Form, Input, Select, Space, Tag } from 'antd'
import { ApartmentOutlined } from '@ant-design/icons'

interface NodeSourceFilterProps {
  section: 'spc' | 'monteCarlo' | 'exploration'
  sourcedFromNode: { displayName: string; dataSourceIds?: string[] } | null
  dataLoaded: boolean
  columns: string[]
  filterColumn: string | undefined
  setFilterColumn: (v: string | undefined) => void
  filterValue: string | undefined
  setFilterValue: (v: string | undefined) => void
  clearFilter: () => void
  valuePlaceholder?: string
  filterable?: boolean
}

export default function NodeSourceFilter({
  section,
  sourcedFromNode,
  dataLoaded,
  columns,
  filterColumn,
  setFilterColumn,
  filterValue,
  setFilterValue,
  clearFilter,
  valuePlaceholder,
  filterable = true,
}: NodeSourceFilterProps) {
  const { t } = useTranslation()
  if (!sourcedFromNode) return null

  return (
    <>
      <Space wrap style={{ marginBottom: 12 }}>
        <Tag color="blue" icon={<ApartmentOutlined />}>
          {t(`${section}.sourceFromNode`, { name: sourcedFromNode.displayName })}
        </Tag>
        {dataLoaded && filterable && (
          <>
            <Form.Item label={t(`${section}.filterByNode`)} style={{ margin: 0 }}>
              <Select
                value={filterColumn}
                onChange={val => {
                  setFilterColumn(val)
                  setFilterValue(undefined)
                }}
                options={columns.map(name => ({ value: name, label: name }))}
                allowClear
                placeholder={t(`${section}.filterByNode`)}
                style={{ width: 160 }}
              />
            </Form.Item>
            <Input
              value={filterValue}
              onChange={e => setFilterValue(e.target.value)}
              disabled={!filterColumn}
              placeholder={valuePlaceholder}
              style={{ width: 180 }}
            />
            <Button size="small" onClick={clearFilter}>
              {t(`${section}.nodeFilterCleared`)}
            </Button>
          </>
        )}
      </Space>
      {!dataLoaded && (
        <Alert
          type="warning"
          message={t(`${section}.dataSourceNotLoaded`)}
          showIcon
          style={{ marginBottom: 12 }}
        />
      )}
    </>
  )
}