// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { createI18n } from 'vue-i18n'
import en from './locales/en.json'

export type MessageSchema = typeof en

const i18n = createI18n<[MessageSchema], 'en'>({
  legacy: false,
  locale: localStorage.getItem('autobot-language') || 'en',
  fallbackLocale: 'en',
  messages: {
    en,
  },
})

/**
 * Dynamically load a locale's messages at runtime.
 * Returns true if the locale was loaded successfully.
 */
export async function loadLocaleMessages(locale: string): Promise<boolean> {
  if (i18n.global.availableLocales.includes(locale)) {
    return true
  }

  try {
    const messages = await import(`./locales/${locale}.json`)
    i18n.global.setLocaleMessage(locale, messages.default)
    return true
  } catch {
    return false
  }
}

/**
 * Set the active locale. Loads the locale file if not yet loaded.
 */
export async function setLocale(locale: string): Promise<void> {
  await loadLocaleMessages(locale)
  i18n.global.locale.value = locale
  localStorage.setItem('autobot-language', locale)
  document.documentElement.setAttribute('lang', locale)
}

export default i18n
