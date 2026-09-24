// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * i18n for the SLM console — all 11 locales, no hardcoded language (#14781).
 *
 * This module used to import `en.json` alone and pass `locale: 'en'`, so the
 * app shipped one language whatever the user's browser or preference said. The
 * shape below is the main console's (`autobot-frontend/src/i18n/index.ts`),
 * deliberately: the two apps share a locale vocabulary and a language
 * preference key, and two different bootstraps would drift the moment either
 * changed.
 *
 * Differences from the main console's version, both on purpose:
 *
 * - messages are loaded EAGERLY. The main app defers them because its English
 *   bundle is ~366KB and reached the initial chunk of every page (#12342);
 *   this app's is a third of that and its shell is not on a hot path, so
 *   eager loading keeps the bootstrap synchronous and avoids an await before
 *   mount.
 * - direction comes from the locale's own `_meta.dir`, same as the main app
 *   (#1812), so an app can never disagree with its own locale file about
 *   which way its text runs.
 */

import { createI18n } from 'vue-i18n'

/** Every locale on disk — derived, never a hand-kept list (#1675). */
const localeModules = import.meta.glob<Record<string, unknown>>('../locales/*.json', { eager: true })

type LocaleBundle = Record<string, unknown> & { _meta?: { dir?: string } }

/** `{ en: {...}, de: {...} }`, keyed by the locale code in the filename. */
const messages: Record<string, LocaleBundle> = Object.fromEntries(
  Object.entries(localeModules).map(([path, module]) => [
    path.replace('../locales/', '').replace('.json', ''),
    ((module as { default?: LocaleBundle }).default ?? module) as LocaleBundle,
  ]),
)

export const SUPPORTED_LOCALES = Object.keys(messages).sort()

/** The key both consoles read, so a language chosen in one is honoured in the other. */
export const LANGUAGE_STORAGE_KEY = 'autobot-language'

/**
 * The user's preferred locale from browser settings, or 'en'.
 *
 * Matches `navigator.languages` against what is on disk, exact match first and
 * then the base tag, so `de-AT` resolves to `de` (#1336, #1508).
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

/** The stored preference when it is a locale we actually have, else detection. */
export function resolveInitialLocale(): string {
  let stored: string | null = null
  try {
    stored = localStorage.getItem(LANGUAGE_STORAGE_KEY)
  } catch {
    // A private window or blocked site data makes storage throw rather than
    // return null; detection is the correct answer there, not a crash.
    stored = null
  }
  return stored && SUPPORTED_LOCALES.includes(stored) ? stored : detectBrowserLocale()
}

/** `'rtl'` or `'ltr'`, read from the locale file's own `_meta.dir` (#1812). */
export function getLocaleDir(locale: string): 'rtl' | 'ltr' {
  return messages[locale]?._meta?.dir === 'rtl' ? 'rtl' : 'ltr'
}

const i18n = createI18n({
  legacy: true,
  locale: resolveInitialLocale(),
  fallbackLocale: 'en',
  messages,
})

/**
 * Switch language, persist it, and set `html[lang]` / `html[dir]`.
 *
 * The `dir` attribute is what makes an RTL locale actually render
 * right-to-left; without it the strings are Arabic and the layout is not.
 */
export function setLocale(locale: string): void {
  if (!SUPPORTED_LOCALES.includes(locale)) {
    return
  }
  i18n.global.locale = locale as typeof i18n.global.locale
  try {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, locale)
  } catch {
    // Not persisting a preference is a smaller failure than refusing to switch.
  }
  document.documentElement.setAttribute('lang', locale)
  document.documentElement.setAttribute('dir', getLocaleDir(locale))
}

/** Apply the resolved locale's `lang`/`dir` once, before the app mounts. */
export function initI18n(): void {
  const locale = resolveInitialLocale()
  document.documentElement.setAttribute('lang', locale)
  document.documentElement.setAttribute('dir', getLocaleDir(locale))
}

export default i18n
