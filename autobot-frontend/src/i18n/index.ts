// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import { createI18n } from 'vue-i18n'
import en from './locales/en.json'

export type MessageSchema = typeof en

// Derive supported locales from locale files on disk — no manual sync needed (#1675)
const localeModules = import.meta.glob('./locales/*.json')
export const SUPPORTED_LOCALES = Object.keys(localeModules)
  .map(path => path.replace('./locales/', '').replace('.json', ''))
  .sort()

/**
 * Detect the user's preferred locale from browser settings.
 * Matches navigator.languages against SUPPORTED_LOCALES.
 * Returns the first match or 'en' as fallback. (#1336, #1508)
 */
export function detectBrowserLocale(): string {
  const browserLocales = navigator.languages ?? [navigator.language]
  for (const browserLocale of browserLocales) {
    const exact = browserLocale.toLowerCase()
    if (SUPPORTED_LOCALES.includes(exact)) {
      return exact
    }
    const base = exact.split('-')[0]
    if (SUPPORTED_LOCALES.includes(base)) {
      return base
    }
  }
  return 'en'
}

const i18n = createI18n<[MessageSchema], string>({
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
 * Read the text direction from a locale's _meta.dir field.
 * Returns 'rtl' or 'ltr'. Falls back to 'ltr' if _meta.dir is absent. (#1812)
 */
export function getLocaleDir(locale: string): 'rtl' | 'ltr' {
  const messages = i18n.global.getLocaleMessage(locale)
  const meta = (messages as Record<string, unknown>)._meta as Record<string, string> | undefined
  return meta?.dir === 'rtl' ? 'rtl' : 'ltr'
}

/**
 * Set the active locale. Loads the locale file if not yet loaded.
 * Also updates the html[dir] attribute for RTL languages (#1337, #1812).
 */
export async function setLocale(locale: string): Promise<void> {
  await loadLocaleMessages(locale)
  ;(i18n.global.locale as unknown as { value: string }).value = locale
  localStorage.setItem('autobot-language', locale)
  document.documentElement.setAttribute('lang', locale)
  document.documentElement.setAttribute('dir', getLocaleDir(locale))
}

export default i18n
