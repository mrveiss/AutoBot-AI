// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
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
import { useTheme, type Theme, type ThemePreset, type AccentColor as ThemeAccentColor } from '@/composables/useTheme'

const logger = createLogger('usePreferences')

/** Shape of the prefs persisted per user account (#8988, #9460/#9471). */
interface AccountAppearance {
  reasoning_effort: ReasoningEffort
  theme: Theme
  accent_color: ThemeAccentColor
  layout_density: LayoutDensity
  font_size: FontSize
  theme_preset: ThemePreset
}

// Preference types
export type FontSize = 'small' | 'medium' | 'large'
export type AccentColor = 'teal' | 'emerald' | 'blue' | 'purple' | 'orange'
export type LayoutDensity = 'compact' | 'comfortable' | 'spacious'
export type VoiceDisplayMode = 'modal' | 'sidepanel'
export type ContextOverflowMode = 'auto' | 'warn' | 'disabled'
// Reasoning effort default (#9460/#9471) — matches backend UserPreferences pattern.
export type ReasoningEffort = 'auto' | 'low' | 'medium' | 'high'

export interface UserPreferences {
  fontSize: FontSize
  accentColor: AccentColor
  layoutDensity: LayoutDensity
  voiceDisplayMode: VoiceDisplayMode
  language: string
  contextOverflowMode: ContextOverflowMode
  reasoningEffort: ReasoningEffort
}

// Default preferences (Issue #9040: aligned with design-tokens.css electric blue default)
const DEFAULT_PREFERENCES: UserPreferences = {
  fontSize: 'medium',
  accentColor: 'blue',
  layoutDensity: 'comfortable',
  voiceDisplayMode: 'modal',
  language: 'en',
  contextOverflowMode: 'auto',
  reasoningEffort: 'auto'
}

// Reactive preferences state
const fontSize = ref<FontSize>('medium')
const accentColor = ref<AccentColor>('blue')
const layoutDensity = ref<LayoutDensity>('comfortable')
const voiceDisplayMode = ref<VoiceDisplayMode>('modal')
const language = ref<string>('en')
const contextOverflowMode = ref<ContextOverflowMode>('auto')
const reasoningEffort = ref<ReasoningEffort>('auto')

// Local storage key
const STORAGE_KEY = 'autobot-preferences'

// Debounce window for coalescing appearance changes into one account-sync request (#8988)
const APPEARANCE_SYNC_DEBOUNCE_MS = 600

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
      reasoningEffort.value = parsed.reasoningEffort || DEFAULT_PREFERENCES.reasoningEffort

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
      contextOverflowMode: contextOverflowMode.value,
      reasoningEffort: reasoningEffort.value
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
 * Main composable function
 */
export function usePreferences() {
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

  // Theme owns base mode / accent / preset; usePreferences owns density / fontSize.
  // Both are persisted together to the account so choices follow the user (#8988).
  const theme = useTheme()

  /**
   * Persist all appearance prefs to the user account (source of truth across devices).
   * localStorage stays a write-through cache (already updated by each setter).
   */
  async function saveAppearanceToBackend(): Promise<void> {
    try {
      const payload: AccountAppearance = {
        reasoning_effort: reasoningEffort.value,
        theme: theme.theme.value,
        accent_color: theme.accentColor.value,
        layout_density: layoutDensity.value,
        font_size: fontSize.value,
        theme_preset: theme.preset.value,
      }
      await apiClient.patch(`${getApiBase()}/users/me/preferences`, payload)
      logger.debug('Appearance prefs saved to account', payload)
    } catch (error) {
      logger.warn('Could not save appearance prefs to account', error)
    }
  }

  /**
   * Load appearance prefs from the user account and apply them. Called after login
   * so a fresh device inherits the user's stored theme/accent/density.
   */
  async function loadAppearanceFromBackend(): Promise<void> {
    try {
      const res = await apiClient.get<{ data?: { preferences?: AccountAppearance } }>(
        `${getApiBase()}/users/me/preferences`
      )
      const prefs = res.data?.preferences
      if (!prefs) return

      if (prefs.theme_preset && prefs.theme_preset !== 'auto') {
        theme.setPreset(prefs.theme_preset)
      } else {
        if (prefs.theme) theme.setTheme(prefs.theme)
        if (prefs.accent_color) theme.setAccentColor(prefs.accent_color)
      }
      if (prefs.layout_density) setLayoutDensity(prefs.layout_density)
      if (prefs.font_size) setFontSize(prefs.font_size)
      if (prefs.reasoning_effort) setReasoningEffort(prefs.reasoning_effort)
      logger.debug('Appearance prefs loaded from account', prefs)
    } catch (error) {
      logger.warn('Could not load appearance prefs from account', error)
    }
  }

  // Initialize once: load preferences, apply to DOM, register watchers (#1502)
  if (!_initialized) {
    _initialized = true

    loadPreferences()

    // Apply current preferences (#1331, #1547: always call setLocale for html[lang]; #1337: setLocale also sets html[dir] for RTL)
    applyFontSize(fontSize.value)
    applyAccentColor(accentColor.value)
    applyLayoutDensity(layoutDensity.value)
    setLocale(language.value)

    // Debounced account sync so rapid changes coalesce into one request (#8988)
    let _appearanceSyncTimer: ReturnType<typeof setTimeout> | null = null
    const _scheduleAppearanceSync = (): void => {
      if (_appearanceSyncTimer) clearTimeout(_appearanceSyncTimer)
      _appearanceSyncTimer = setTimeout(() => {
        void saveAppearanceToBackend()
      }, APPEARANCE_SYNC_DEBOUNCE_MS)
    }

    // Watch for changes and persist (localStorage write-through + account sync)
    watch(fontSize, (newSize) => {
      applyFontSize(newSize)
      savePreferences()
      _scheduleAppearanceSync()
    })

    watch(accentColor, (newColor) => {
      applyAccentColor(newColor)
      savePreferences()
    })

    watch(layoutDensity, (newDensity) => {
      applyLayoutDensity(newDensity)
      savePreferences()
      _scheduleAppearanceSync()
    })

    // Theme owns base mode / accent / preset — sync those to the account too
    watch([theme.theme, theme.accentColor, theme.preset], () => {
      _scheduleAppearanceSync()
    })

    watch(voiceDisplayMode, () => {
      savePreferences()
    })

    watch(contextOverflowMode, () => {
      savePreferences()
    })

    // Reasoning effort default follows the user across devices (#9460/#9471)
    watch(reasoningEffort, () => {
      savePreferences()
      _scheduleAppearanceSync()
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

  function setReasoningEffort(effort: ReasoningEffort): void {
    reasoningEffort.value = effort
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
    reasoningEffort.value = DEFAULT_PREFERENCES.reasoningEffort
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
    reasoningEffort,

    // Actions
    setFontSize,
    setAccentColor,
    setLayoutDensity,
    setVoiceDisplayMode,
    setLanguage,
    setContextOverflowMode,
    setReasoningEffort,
    loadLanguageFromBackend,
    loadAppearanceFromBackend,
    saveAppearanceToBackend,
    resetPreferences
  }
}
