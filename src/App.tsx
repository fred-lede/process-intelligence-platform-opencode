import { useEffect, useState } from 'react'
import { useProcessFlowNavStore } from './stores/processFlowNavStore'
import { Layout, Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import Sidebar from './components/layout/Sidebar'
import AssistantPanel from './components/layout/AssistantPanel'
import ProjectOverview from './features/project/ProjectOverview'
import DataImport from './features/data-import/DataImport'
import ProcessDefine from './features/process-define/ProcessDefine'
import Exploration from './features/exploration/Exploration'
import ModelCenter from './features/model-center/ModelCenter'
import Report from './features/report/Report'
import Approval from './features/approval/Approval'
import FeaturePlaceholder from './components/common/FeaturePlaceholder'
import Settings from './features/settings/Settings'
import SPC from './features/spc/SPC'
import MonteCarlo from './features/monte-carlo/MonteCarlo'
import Copula from './features/copula/Copula'
import Prediction from './features/prediction/Prediction'
import ValidationLab from './features/validation/ValidationLab'
import ProcessFlow from './features/process-flow/ProcessFlow'
import DataAssets from './features/data-assets/DataAssets'
import type { AppTab } from './types'

const { Content } = Layout

interface ActiveProject {
  name: string
  root: string
}

export default function App() {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState<AppTab>('project')
  const [activeProject, setActiveProject] = useState<ActiveProject | null>(null)

  const pendingTarget = useProcessFlowNavStore((s) => s.pending?.targetTab)

  useEffect(() => {
    if (pendingTarget && pendingTarget !== activeTab) {
      setActiveTab(pendingTarget)
    }
  }, [pendingTarget, activeTab])

  const renderTab = () => {
    if (activeTab === 'project') return <ProjectOverview onProjectChanged={setActiveProject} />
    if (activeTab === 'dataImport') return <DataImport onFinished={() => setActiveTab('processDefine')} />
    if (activeTab === 'processDefine') return <ProcessDefine />
    if (activeTab === 'exploration') return <Exploration />
    if (activeTab === 'modelCenter') return <ModelCenter />
    if (activeTab === 'reports') return <Report />
    if (activeTab === 'approval') return <Approval />
    if (activeTab === 'spc') return <SPC />
    if (activeTab === 'monteCarlo') return <MonteCarlo />
    if (activeTab === 'copula') return <Copula />
    if (activeTab === 'prediction') return <Prediction />
    if (activeTab === 'validation') return <ValidationLab />
    if (activeTab === 'processFlow') return <ProcessFlow />
    if (activeTab === 'dataAssets') return <DataAssets />
    if (activeTab === 'settings') return <Settings />
    return <FeaturePlaceholder tabKey={activeTab} />
  }

  return (
    <Layout style={{ height: '100vh' }}>
      <Sidebar activeTab={activeTab} onTabChange={setActiveTab} />
      <Layout style={{ minWidth: 0 }}>
        <div style={{ height: 52, padding: '0 24px', display: 'flex', alignItems: 'center', gap: 8, borderBottom: '1px solid #e5e7eb', background: '#fff' }}>
          <Typography.Text type="secondary">{t('project.projectName')}:</Typography.Text>
          <Typography.Text strong ellipsis={{ tooltip: activeProject?.root }}>
            {activeProject?.name ?? t('project.noActiveProject')}
          </Typography.Text>
        </div>
        <Content style={{ padding: 24, overflow: 'auto', background: '#F5F7FA' }}>
          {renderTab()}
        </Content>
      </Layout>
      <AssistantPanel activeTab={activeTab} />
    </Layout>
  )
}
