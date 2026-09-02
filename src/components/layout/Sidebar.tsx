import { useTranslation } from 'react-i18next'
import { Layout, Menu, Select, Typography } from 'antd'
import {
  DashboardOutlined,
  ImportOutlined,
  CheckCircleOutlined,
  ApartmentOutlined,
  BarChartOutlined,
  ExperimentOutlined,
  ThunderboltOutlined,
  RobotOutlined,
  SlidersOutlined,
  FileTextOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import type { AppTab } from '../../types'

const { Sider } = Layout

interface SidebarProps {
  activeTab: AppTab
  onTabChange: (tab: AppTab) => void
}

const tabItems = [
  { key: 'project', icon: <DashboardOutlined /> },
  { key: 'dataImport', icon: <ImportOutlined /> },
  { key: 'dataCheck', icon: <CheckCircleOutlined /> },
  { key: 'processDefine', icon: <ApartmentOutlined /> },
  { key: 'exploration', icon: <BarChartOutlined /> },
  { key: 'modelCenter', icon: <ExperimentOutlined /> },
  { key: 'validation', icon: <ThunderboltOutlined /> },
  { key: 'monteCarlo', icon: <RobotOutlined /> },
  { key: 'prediction', icon: <SlidersOutlined /> },
  { key: 'reports', icon: <FileTextOutlined /> },
]

const settingsItem = { key: 'settings', icon: <SettingOutlined /> }

export default function Sidebar({ activeTab, onTabChange }: SidebarProps) {
  const { t, i18n } = useTranslation()

  const menuItems = [
    ...tabItems.map((item) => ({
      key: item.key,
      icon: item.icon,
      label: t(`nav.${item.key}`),
    })),
    { type: 'divider' as const },
    {
      key: settingsItem.key,
      icon: settingsItem.icon,
      label: t('nav.settings'),
    },
  ]

  const handleLanguageChange = (lng: string) => {
    i18n.changeLanguage(lng)
    localStorage.setItem('i18nextLng', lng)
  }

  return (
    <Sider
      width={240}
      theme="light"
      style={{
        borderRight: '1px solid #e5e7eb',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div style={{ padding: '16px 16px 0' }}>
        <Typography.Title level={5} style={{ margin: 0 }}>
          {t('app.name')}
        </Typography.Title>
      </div>
      <Menu
        mode="inline"
        selectedKeys={[activeTab]}
        onClick={({ key }) => onTabChange(key as AppTab)}
        items={menuItems}
        style={{ flex: 1, border: 'none', paddingTop: 8 }}
      />
      <div style={{ padding: 12, borderTop: '1px solid #e5e7eb' }}>
        <Select
          size="small"
          style={{ width: '100%' }}
          value={i18n.language}
          onChange={handleLanguageChange}
          options={[
            { value: 'en', label: 'English' },
            { value: 'zh-TW', label: '繁體中文' },
          ]}
        />
      </div>
    </Sider>
  )
}
