// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import enUS from './en-US.json'
import frFR from './fr-FR.json'
import esES from './es-ES.json'

export const SUPPORTED_LANGUAGES = [
  { code: 'en-US', label: 'English' },
  { code: 'fr-FR', label: 'Français' },
  { code: 'es-ES', label: 'Español' },
] as const

export type LanguageCode = (typeof SUPPORTED_LANGUAGES)[number]['code']

const savedLanguage = localStorage.getItem('pangia-language') ?? 'en-US'

i18n.use(initReactI18next).init({
  resources: {
    'en-US': { translation: enUS },
    'fr-FR': { translation: frFR },
    'es-ES': { translation: esES },
  },
  lng: savedLanguage,
  fallbackLng: 'en-US',
  interpolation: {
    escapeValue: false,
  },
})

export default i18n
