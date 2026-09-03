import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import en from './en.json'
import zhTW from './zh-TW.json'
import esMX from './es-MX.json'

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      'zh-TW': { translation: zhTW },
      'es-MX': { translation: esMX },
    },
    fallbackLng: 'en',
    supportedLngs: ['en', 'zh-TW', 'es-MX'],
    interpolation: {
      escapeValue: false,
    },
  })

export default i18n
