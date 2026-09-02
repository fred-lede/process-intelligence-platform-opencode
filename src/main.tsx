import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider, theme } from 'antd'
import enUS from 'antd/locale/en_US'
import zhTW from 'antd/locale/zh_TW'
import App from './App'
import './i18n'
import './styles/global.css'

const localeMap: Record<string, typeof enUS> = {
  en: enUS,
  'zh-TW': zhTW,
}

function renderLocale(lng: string) {
  return localeMap[lng] || enUS
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={renderLocale(getInitialLanguage())}
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: '#2563EB',
          colorSuccess: '#16A34A',
          colorWarning: '#D97706',
          colorError: '#DC2626',
          colorInfo: '#6366F1',
          colorBgLayout: '#F5F7FA',
          colorText: '#1F2937',
        },
      }}
    >
      <App />
    </ConfigProvider>
  </React.StrictMode>,
)

function getInitialLanguage(): string {
  // In Phase 0, default to browser language if supported, else 'en'
  const stored = localStorage.getItem('i18nextLng')
  if (stored === 'en' || stored === 'zh-TW') return stored
  return navigator.language.startsWith('zh') ? 'zh-TW' : 'en'
}
