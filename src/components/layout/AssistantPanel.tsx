import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Layout, Card, Empty, Typography, Input, Button, Space } from 'antd'
import { SendOutlined } from '@ant-design/icons'

const { Sider } = Layout

export default function AssistantPanel() {
  const { t } = useTranslation()
  const [message, setMessage] = useState('')

  return (
    <Sider
      width={320}
      theme="light"
      style={{
        borderLeft: '1px solid #e5e7eb',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div style={{ padding: 16, borderBottom: '1px solid #e5e7eb' }}>
        <Typography.Title level={5} style={{ margin: 0 }}>
          {t('assistant.title')}
        </Typography.Title>
      </div>
      <div style={{ flex: 1, padding: 16, overflow: 'auto' }}>
        <Card size="small" style={{ marginBottom: 12 }}>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={t('common.notStarted')}
          />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {t('assistant.placeholder')}
          </Typography.Text>
        </Card>
      </div>
      <div style={{ padding: 12, borderTop: '1px solid #e5e7eb' }}>
        <Space.Compact style={{ width: '100%' }}>
          <Input
            placeholder={t('assistant.placeholder')}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onPressEnter={() => setMessage('')}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            disabled={!message.trim()}
            onClick={() => setMessage('')}
          />
        </Space.Compact>
      </div>
    </Sider>
  )
}
