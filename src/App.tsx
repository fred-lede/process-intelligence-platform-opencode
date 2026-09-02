import { useState } from 'react'
import { Layout } from 'antd'
import Sidebar from './components/layout/Sidebar'
import AssistantPanel from './components/layout/AssistantPanel'
import ProjectOverview from './features/project/ProjectOverview'
import DataImport from './features/data-import/DataImport'
import ProcessDefine from './features/process-define/ProcessDefine'
import Exploration from './features/exploration/Exploration'
import FeaturePlaceholder from './components/common/FeaturePlaceholder'
import type { AppTab } from './types'

const { Content } = Layout

export default function App() {
  const [activeTab, setActiveTab] = useState<AppTab>('project')

  const renderTab = () => {
    if (activeTab === 'project') return <ProjectOverview />
    if (activeTab === 'dataImport') return <DataImport />
    if (activeTab === 'processDefine') return <ProcessDefine />
    if (activeTab === 'exploration') return <Exploration />
    return <FeaturePlaceholder tabKey={activeTab} />
  }

  return (
    <Layout style={{ height: '100vh' }}>
      <Sidebar activeTab={activeTab} onTabChange={setActiveTab} />
      <Content style={{ padding: 24, overflow: 'auto', background: '#F5F7FA' }}>
        {renderTab()}
      </Content>
      <AssistantPanel />
    </Layout>
  )
}
