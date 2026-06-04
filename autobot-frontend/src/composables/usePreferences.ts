/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * usePreferences.ts - User Preferences Management Composable
 * Issue #753: Additional Customization (Font Size, Accent Colors, Layout Density)
 */

import { ref, watch } from 'vue'
import { setLocale } from '@/i18n'
import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'

const logger = createLogger('usePreferences')

// Preference types
export type FontSize = 'small' | 'medium' | 'large'
export type AccentColor = 'teal' | 'emerald' | 'blue' | 'purple' | 'orange'
export type LayoutDensity = 'compact' | 'comfortable' | 'spacious'
export type VoiceDisplayMode = 'modal' | 'sidepanel'
export type ContextOverflowMode = 'auto' | 'warn' | 'disabled'

export interface UserPreferences {
  fontSize: FontSize
  accentColor: AccentColor
  layoutDensity: LayoutDensity
  voiceDisplayMode: VoiceDisplayMode
  language: string
  contextOverflowMode: ContextOverflowMode
}

// Default preferences (Issue #9040: aligned with design-tokens.css electric blue default)
const DEFAULT_PREFERENCES: UserPreferences = {
  fontSize: 'medium',
  accentColor: 'blue',
  layoutDensity: 'comfortable',
  voiceDisplayMode: 'modal',
  language: 'en',
  contextOverflowMode: 'auto'
}

// Reactive preferences state
const fontSize = ref<FontSize>('medium')
const accentColor = ref<AccentColor>('blue')
const layoutDensity = ref<LayoutDensity>('comfortable')
const voiceDisplayMode = ref<VoiceDisplayMode>('modal')
const language = ref<string>('en')
const contextOverflowMode = ref<ContextOverflowMode>('auto')

// Local storage key
const STORAGE_KEY = 'autobot-preferences'

// Module-level initialization flag (#1502)
let _initialized = false

/**
 * Load preferences from localStorage
 */
function loadPreferences(): void {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      const parsed = JSON.parse(stored) as UserPreferences
      fontSize.value = parsed.fontSize || DEFAULT_PREFERENCES.fontSize
      accentColor.value = parsed.accentColor || DEFAULT_PREFERENCES.accentColor
      layoutDensity.value = parsed.layoutDensity || DEFAULT_PREFERENCES.layoutDensity
      voiceDisplayMode.value = parsed.voiceDisplayMode || DEFAULT_PREFERENCES.voiceDisplayMode
      language.value = parsed.language || localStorage.getItem('autobot-language') || DEFAULT_PREFERENCES.language
      contextOverflowMode.value = parsed.contextOverflowMode || DEFAULT_PREFERENCES.contextOverflowMode

      logger.debug('Preferences loaded from localStorage', {
        fontSize: fontSize.value,
        accentColor: accentColor.value,
        layoutDensity: layoutDensity.value
      })
    } else {
      logger.debug('No stored preferences found, using defaults')
    }
  } catch (error) {
    logger.error('Failed to load preferences from localStorage', error)
  }
}

/**
 * Save preferences to localStorage
 */
function savePreferences(): void {
  try {
    const preferences: UserPreferences = {
      fontSize: fontSize.value,
      accentColor: accentColor.value,
      layoutDensity: layoutDensity.value,
      voiceDisplayMode: voiceDisplayMode.value,
      language: language.value,
      contextOverflowMode: contextOverflowMode.value
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences))
    logger.debug('Preferences saved to localStorage', preferences)
  } catch (error) {
    logger.error('Failed to save preferences to localStorage', error)
  }
}

/**
 * Apply font size preference to document root
 */
function applyFontSize(size: FontSize): void {
  const root = document.documentElement
  root.setAttribute('data-font-size', size)
  logger.debug(`Font size applied: ${size}`)
}

/**
 * Apply accent color preference to document root
 */
function applyAccentColor(color: AccentColor): void {
  const root = document.documentElement
  root.setAttribute('data-accent-color', color)
  logger.debug(`Accent color applied: ${color}`)
}

/**
 * Apply layout density preference to document root
 */
function applyLayoutDensity(density: LayoutDensity): void {
  const root = document.documentElement
  root.setAttribute('data-layout-density', density)
  logger.debug(`Layout density applied: ${density}`)
}

/**
 * Sync language preference to backend personality profile
 */
function syncLanguageToBackend(code: string): void {
  apiClient.get<any>(`${getApiBase()}/personality/active`).then((res: any) => {
    if (res.data && res.data.id) {
      apiClient.put(
        `${getApiBase()}/personality/profiles/${res.data.id}`,
        { language_code: code }
      )
    }
  }).catch((error) => {
    logger.warn('Could not sync language to backend', error)
  })
}

/**
 * Fetch language preference from backend personality profile and apply it.
 * Called after login to enable cross-device language sync.
 */
async function loadLanguageFromBackend(): Promise<void> {
  try {
    const res = await apiClient.get<any>(`${getApiBase()}/personality/active`)
    const code: string | undefined = res.data?.language_code
    if (code && code !== language.value) {
      await setLanguage(code)
      logger.debug(`Language loaded from backend: ${code}`)
    }
  } catch (error) {
    logger.warn('Could not load language from backend', error)
  }
}

/**
 * Main composable function
 */
export function usePreferences() {
  // Initialize once: load preferences, apply to DOM, register watchers (#1502)
  if (!_initialized) {
    _initialized = true

    loadPreferences()

    // Apply current preferences (#1331, #1547: always call setLocale for html[lang]; #1337: setLocale also sets html[dir] for RTL)
    applyFontSize(fontSize.value)
    applyAccentColor(accentColor.value)
    applyLayoutDensity(layoutDensity.value)
    setLocale(language.value)

    // Watch for changes and persist
    watch(fontSize, (newSize) => {
      applyFontSize(newSize)
      savePreferences()
    })

    watch(accentColor, (newColor) => {
      applyAccentColor(newColor)
      savePreferences()
    })

    watch(layoutDensity, (newDensity) => {
      applyLayoutDensity(newDensity)
      savePreferences()
    })

    watch(voiceDisplayMode, () => {
      savePreferences()
    })

    watch(contextOverflowMode, () => {
      savePreferences()
    })
  }

  /**
   * Set font size preference
   */
  function setFontSize(size: FontSize): void {
    fontSize.value = size
  }

  /**
   * Set accent color preference
   */
  function setAccentColor(color: AccentColor): void {
    accentColor.value = color
  }

  /**
   * Set layout density preference
   */
  function setLayoutDensity(density: LayoutDensity): void {
    layoutDensity.value = density
  }

  function setVoiceDisplayMode(mode: VoiceDisplayMode): void {
    voiceDisplayMode.value = mode
  }

  function setContextOverflowMode(mode: ContextOverflowMode): void {
    contextOverflowMode.value = mode
  }

  async function setLanguage(code: string): Promise<void> {
    language.value = code
    await setLocale(code)
    savePreferences()
    syncLanguageToBackend(code)
  }

  /**
   * Reset all preferences to defaults
   */
  function resetPreferences(): void {
    fontSize.value = DEFAULT_PREFERENCES.fontSize
    accentColor.value = DEFAULT_PREFERENCES.accentColor
    layoutDensity.value = DEFAULT_PREFERENCES.layoutDensity
    voiceDisplayMode.value = DEFAULT_PREFERENCES.voiceDisplayMode
    language.value = DEFAULT_PREFERENCES.language
    contextOverflowMode.value = DEFAULT_PREFERENCES.contextOverflowMode
    setLocale(DEFAULT_PREFERENCES.language)
    logger.debug('Preferences reset to defaults')
  }

  // #1331 — expose language preference
  return {
    // State
    fontSize,
    accentColor,
    layoutDensity,
    voiceDisplayMode,
    language,
    contextOverflowMode,

    // Actions
    setFontSize,
    setAccentColor,
    setLayoutDensity,
    setVoiceDisplayMode,
    setLanguage,
    setContextOverflowMode,
    loadLanguageFromBackend,
    resetPreferences
  }
}
