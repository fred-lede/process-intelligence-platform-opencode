import { useTranslation } from 'react-i18next'
import { Layout, Menu, Select, Typography, Button, Modal, Tooltip } from 'antd'
import { getVersion } from '@tauri-apps/api/app'
import { isTauri } from '@tauri-apps/api/core'
import {
  DashboardOutlined,
  ImportOutlined,
  ApartmentOutlined,
  BarChartOutlined,
  ExperimentOutlined,
  ThunderboltOutlined,
  RobotOutlined,
  SlidersOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  SettingOutlined,
  InfoCircleOutlined,
  LineChartOutlined,
  DatabaseOutlined,
  DotChartOutlined,
  AuditOutlined,
} from '@ant-design/icons'
import type { AppTab } from '../../types'
import { useEffect, useState } from 'react'
import GuideModal from '../guide/GuideModal'
import { useGuideContextStore } from '../../stores/guideContextStore'

const { Sider } = Layout

interface SidebarProps {
  activeTab: AppTab
  activeProject: { name: string; root: string } | null
  onTabChange: (tab: AppTab) => void
}

const tabItems = [
  { key: 'project', icon: <DashboardOutlined /> },
  { key: 'dataImport', icon: <ImportOutlined /> },
  { key: 'processDefine', icon: <ApartmentOutlined /> },
  { key: 'exploration', icon: <BarChartOutlined /> },
  { key: 'modelCenter', icon: <ExperimentOutlined /> },
  { key: 'processFlow', icon: <ApartmentOutlined /> },
  { key: 'validation', icon: <ThunderboltOutlined /> },
  { key: 'monteCarlo', icon: <RobotOutlined /> },
  { key: 'copula', icon: <DotChartOutlined /> },
  { key: 'prediction', icon: <SlidersOutlined /> },
  { key: 'reports', icon: <FileTextOutlined /> },
  { key: 'approval', icon: <AuditOutlined /> },
  { key: 'spc', icon: <LineChartOutlined /> },
  { key: 'dataAssets', icon: <DatabaseOutlined /> },
]

const settingsItem = { key: 'settings', icon: <SettingOutlined /> }

export default function Sidebar({ activeTab, activeProject, onTabChange }: SidebarProps) {
  const { t, i18n } = useTranslation()
  const [aboutOpen, setAboutOpen] = useState(false)
  const [guideOpen, setGuideOpen] = useState(false)
  const guideSubtab = useGuideContextStore((s) => s.subtab)
  const [appVersion, setAppVersion] = useState<string | null>(null)

  useEffect(() => {
    if (!isTauri()) return
    void getVersion().then(setAppVersion).catch(() => setAppVersion(null))
  }, [])

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
        <Tooltip title={activeProject?.root}>
          <Button
            block
            icon={<FolderOpenOutlined />}
            style={{ display: 'flex', marginTop: 12, textAlign: 'left' }}
            type="default"
          >
            <Typography.Text ellipsis style={{ minWidth: 0 }}>
              {activeProject?.name ?? t('project.noActiveProject')}
            </Typography.Text>
          </Button>
        </Tooltip>
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
          style={{ width: '100%', marginBottom: 8 }}
          value={i18n.language}
          onChange={handleLanguageChange}
          options={[
            { value: 'en', label: 'English' },
            { value: 'zh-TW', label: '繁體中文' },
            { value: 'es-MX', label: 'Español (México)' },
          ]}
        />
        <Button
          type="text"
          size="small"
          icon={<InfoCircleOutlined />}
          style={{ width: '100%', textAlign: 'left' }}
          onClick={() => setAboutOpen(true)}
        >
          {t('nav.about')}
        </Button>
        <Button type="text" size="small" icon={<InfoCircleOutlined />} style={{ width: '100%', textAlign: 'left' }} onClick={() => setGuideOpen(true)}>
          {t('nav.userGuide')}
        </Button>
      </div>

      <GuideModal open={guideOpen} tab={activeTab} subtab={guideSubtab} onClose={() => setGuideOpen(false)} />

      <Modal
        open={aboutOpen}
        title={t('about.title')}
        footer={[
          <Button key="close" type="primary" onClick={() => setAboutOpen(false)}>
            {t('about.close')}
          </Button>,
        ]}
        onCancel={() => setAboutOpen(false)}
      >
        <Typography.Paragraph>
          <strong>{t('about.appName')}</strong>
        </Typography.Paragraph>
        <Typography.Paragraph>
          {t('about.description')}
        </Typography.Paragraph>
        <Typography.Paragraph>
          <strong>{t('about.author')}:</strong> Fred Wang
        </Typography.Paragraph>
        <Typography.Paragraph>
          <strong>{t('about.version')}:</strong> {appVersion ?? '—'}
        </Typography.Paragraph>
        <Typography.Paragraph>
          <strong>{t('about.license')}:</strong> MIT License
        </Typography.Paragraph>
        <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
          {t('about.github')}
        </Typography.Paragraph>
      </Modal>
    </Sider>
  )
}
