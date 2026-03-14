// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { createI18n } from 'vue-i18n'
import en from './locales/en.json'

export type MessageSchema = typeof en

// Locales that use right-to-left text direction (#1337)
const RTL_LOCALES = new Set(['ar', 'he', 'fa', 'ur'])

// All locales with available translation files (#1336, #1508)
export const SUPPORTED_LOCALES = [
  'ar', 'de', 'en', 'es', 'fa', 'fr', 'he', 'lv', 'pl', 'pt', 'ur',
] as const

/**
 * Detect the user's preferred locale from browser settings.
 * Matches navigator.languages against SUPPORTED_LOCALES.
 * Returns the first match or 'en' as fallback. (#1336, #1508)
 */
export function detectBrowserLocale(): string {
  const browserLocales = navigator.languages ?? [navigator.language]
  for (const browserLocale of browserLocales) {
    const exact = browserLocale.toLowerCase()
    if ((SUPPORTED_LOCALES as readonly string[]).includes(exact)) {
      return exact
    }
    const base = exact.split('-')[0]
    if ((SUPPORTED_LOCALES as readonly string[]).includes(base)) {
      return base
    }
  }
  return 'en'
}

const i18n = createI18n<[MessageSchema], 'en'>({
  legacy: false,
  locale: localStorage.getItem('autobot-language') || detectBrowserLocale(),
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
 * Also updates the html[dir] attribute for RTL languages (#1337).
 */
export async function setLocale(locale: string): Promise<void> {
  await loadLocaleMessages(locale)
  i18n.global.locale.value = locale
  localStorage.setItem('autobot-language', locale)
  document.documentElement.setAttribute('lang', locale)
  document.documentElement.setAttribute('dir', RTL_LOCALES.has(locale) ? 'rtl' : 'ltr')
}

export default i18n
