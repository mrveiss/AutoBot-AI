// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * useSlmTheme.ts - SLM theme switching (#18239).
 *
 * The four Refined themes (light, dark, contrast, mono) whose palettes live in
 * assets/styles/slm-scheme.css. Same names, storage key and `data-theme` application
 * as the user frontend: all of that is the shared kit's themeScheme, not a copy.
 * Replaces the former dark-mode toggle and the legacy `high-contrast` palette
 * (useAccessibility.ts, #754 / #3305), which is folded into `contrast`.
 */

import { computed, ref } from 'vue'
import {
  THEME_STORAGE_KEY, applyThemeToDocument, createLogger, readStoredTheme, writeStoredTheme,
  type Theme,
} from '@autobot/ui'

const logger = createLogger('Theme')

/** The themes the SLM ships a palette for (`contrast-dark` and `system` are user-app only). */
export const SLM_THEMES = ['light', 'dark', 'contrast', 'mono'] as const satisfies readonly Theme[]
export type SlmTheme = (typeof SLM_THEMES)[number]

const DEFAULT_THEME: SlmTheme = 'light'

/** i18n keys for the theme names, same wording as the user app's picker. */
export const SLM_THEME_LABEL_KEYS: Record<SlmTheme, string> = {
  light: 'settings.generalSettings.themeLight',
  dark: 'settings.generalSettings.themeDark',
  contrast: 'settings.generalSettings.themeContrast',
  mono: 'settings.generalSettings.themeMono',
}

// Keys written by the toggles this composable replaces. They are read once to carry the
// choice over, then removed.
const LEGACY_HIGH_CONTRAST_KEY = 'autobot-high-contrast'
const LEGACY_DARK_MODE_KEY = 'autobot-dark-mode'

/** Shared reactive state for the theme across all consumers. */
const currentTheme = ref<SlmTheme>(DEFAULT_THEME)

/**
 * The single legacy-theme migration. Carries a choice saved by the legacy toggles over to
 * the theme key: the old high-contrast palette becomes `contrast`, dark mode becomes `dark`
 * (high contrast won, as it did before), and a stored `high-contrast` theme value is read
 * as `contrast`. An already stored theme is never overwritten by the legacy toggles.
 * Returns the migrated theme, if any.
 */
export function migrateLegacyTheme(): SlmTheme | null {
  try {
    if (localStorage.getItem(THEME_STORAGE_KEY) === 'high-contrast') {
      writeStoredTheme('contrast')
    }
    const highContrast = localStorage.getItem(LEGACY_HIGH_CONTRAST_KEY) === 'true'
    const dark = localStorage.getItem(LEGACY_DARK_MODE_KEY) === 'true'
    const hadLegacy = localStorage.getItem(LEGACY_HIGH_CONTRAST_KEY) !== null
      || localStorage.getItem(LEGACY_DARK_MODE_KEY) !== null
    if (!hadLegacy) return null
    localStorage.removeItem(LEGACY_HIGH_CONTRAST_KEY)
    localStorage.removeItem(LEGACY_DARK_MODE_KEY)
    if (localStorage.getItem(THEME_STORAGE_KEY) !== null) return null
    const migrated: SlmTheme | null = highContrast ? 'contrast' : dark ? 'dark' : null
    if (migrated) writeStoredTheme(migrated)
    return migrated
  } catch {
    return null
  }
}

/** The stored theme, after the legacy migration. */
function loadTheme(): SlmTheme {
  migrateLegacyTheme()
  return (readStoredTheme(SLM_THEMES) as SlmTheme | null) ?? DEFAULT_THEME
}

/**
 * SLM theme composable with localStorage persistence.
 */
export function useSlmTheme() {
  function set(theme: SlmTheme): void {
    currentTheme.value = theme
    writeStoredTheme(theme)
    applyThemeToDocument(theme)
    logger.info('Theme:', theme)
  }

  /** Quick switch for the sidebar: High contrast on, or back to Light. */
  function toggleContrast(): void {
    set(currentTheme.value === 'contrast' ? DEFAULT_THEME : 'contrast')
  }

  function init(): void {
    currentTheme.value = loadTheme()
    applyThemeToDocument(currentTheme.value)
  }

  return {
    theme: currentTheme,
    isContrast: computed(() => currentTheme.value === 'contrast'),
    availableThemes: SLM_THEMES,
    set,
    toggleContrast,
    init,
  }
}
