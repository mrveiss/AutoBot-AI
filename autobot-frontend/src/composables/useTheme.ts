// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * useTheme.ts - Theme Management Composable
 * Issue #704: CSS Design System - Centralized Theming & SSOT Styles
 * Issue #8988: User-Selectable Theme System - Custom Theme Presets
 *
 * Provides reactive theme switching capabilities with:
 * - Dark/Light/High-contrast/Monochrome/System theme modes (#18223)
 * - Named theme presets (Catppuccin, Solarized, High Contrast, etc.)
 * - Custom accent color presets
 * - LocalStorage persistence
 * - System preference detection
 * - Instant theme switching (<100ms)
 *
 * Usage:
 *   const { preset, setPreset, availablePresets } = useTheme()
 *   setPreset('catppuccin-mocha')  // Apply named preset
 */

import { ref, computed, onMounted, getCurrentInstance } from 'vue'
import { THEME_PRESETS, type ThemePreset } from './themePresets'

/** The built-in themes a `data-theme` attribute can carry (#18223). `contrast`
 * (high contrast) and `mono` (monochrome) are light-based accessibility and
 * corporate themes; `contrast-dark` is the high-contrast theme on a dark base
 * (#18253). css/themes/{contrast,contrast-dark,mono}.css style them. */
export const EFFECTIVE_THEMES = ['light', 'dark', 'contrast', 'contrast-dark', 'mono'] as const
export type EffectiveTheme = (typeof EFFECTIVE_THEMES)[number]

/** Available theme options: the built-ins plus `system`, which follows the OS
 * between `light` and `dark`. */
export const THEMES = [...EFFECTIVE_THEMES, 'system'] as const
export type Theme = (typeof THEMES)[number]

/** The `color-scheme` a theme renders with (native controls, scrollbars). */
export function colorSchemeFor(theme: EffectiveTheme): 'dark' | 'light' {
  return theme === 'dark' || theme === 'contrast-dark' ? 'dark' : 'light'
}

/** Available accent color options */
export type AccentColor = 'theme' | 'blue' | 'green' | 'purple' | 'orange' | 'pink' | 'teal' | 'indigo' | 'red'

/** The accents accents.css defines, at runtime. #18066: this list existed twice
 * in this module (`validAccents` and `availableAccents`), so a ninth accent had
 * to be added in two places or picker and validator would disagree. */
export const ACCENT_COLORS: readonly AccentColor[] = ['theme', 'blue', 'green', 'purple', 'orange', 'pink', 'teal', 'indigo', 'red'] as const

export type { ThemePreset, ThemePresetConfig } from './themePresets'
export { THEME_PRESETS } from './themePresets'

/** Storage keys for persisting preferences */
const THEME_STORAGE_KEY = 'autobot-theme'
const ACCENT_STORAGE_KEY = 'autobot-accent-color'
const PRESET_STORAGE_KEY = 'autobot-theme-preset'

/** Default values when no preference is set */
// The Refined handoff names Light the default (#18223). Nothing there says to follow the
// OS on first run, so a fresh install is light; `system` stays selectable.
const DEFAULT_THEME: Theme = 'light'
// `theme` = no accent preset: the theme's own primary colour stands (#18223).
const DEFAULT_ACCENT: AccentColor = 'theme'
// Stored and sent to the server, 'auto' means "no named preset" (the backend default).
// In memory no preset is null, and the Auto preset is selected only while system theme +
// theme accent is what is applied. So a fresh install (light) selects nothing (#18252).
const NO_NAMED_PRESET: ThemePreset = 'auto'

/** Global reactive state (singleton pattern) */
const currentTheme = ref<Theme>(DEFAULT_THEME)
const currentAccent = ref<AccentColor>(DEFAULT_ACCENT)
const currentPreset = ref<ThemePreset | null>(null)

/** Track if theme has been initialized */
let isInitialized = false

/**
 * Determines the effective theme based on current setting and system preference
 */
function getEffectiveTheme(theme: Theme): EffectiveTheme {
  if (theme === 'system') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return theme
}

/**
 * Applies the theme to the document root element
 */
function applyTheme(theme: Theme): void {
  const effectiveTheme = getEffectiveTheme(theme)
  document.documentElement.setAttribute('data-theme', effectiveTheme)

  // Also update color-scheme for native elements (scrollbars, form controls)
  document.documentElement.style.colorScheme = colorSchemeFor(effectiveTheme)

  syncMetaThemeColor()
}

/**
 * Keeps the mobile browser chrome (<meta name="theme-color">) on the active
 * theme's surface. It reads the resolved token instead of naming a colour, so
 * all four themes and any deployed one are covered. Moved here from
 * useUserStore#applyTheme (#18240): this is the only place the theme is applied.
 */
function syncMetaThemeColor(): void {
  const meta = document.querySelector('meta[name="theme-color"]')
  const surface = getComputedStyle(document.documentElement).getPropertyValue('--bg-secondary').trim()
  if (meta && surface) meta.setAttribute('content', surface)
}

/**
 * Applies the accent color to the document root element
 */
function applyAccentColor(accent: AccentColor): void {
  // `theme` sets no attribute, so no accents.css rule applies and the theme's own
  // primary (css/themes/refined-map.css) stands.
  if (accent === 'theme') {
    document.documentElement.removeAttribute('data-accent')
    return
  }
  document.documentElement.setAttribute('data-accent', accent)
}

/**
 * Saves theme preference to localStorage
 */
function saveTheme(theme: Theme): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme)
  } catch {
    // localStorage may be unavailable in some contexts
  }
}

/**
 * Saves accent color preference to localStorage
 */
function saveAccentColor(accent: AccentColor): void {
  try {
    localStorage.setItem(ACCENT_STORAGE_KEY, accent)
  } catch {
    // localStorage may be unavailable in some contexts
  }
}

/**
 * Saves theme preset preference to localStorage
 */
function savePreset(preset: ThemePreset | null): void {
  try {
    localStorage.setItem(PRESET_STORAGE_KEY, preset ?? NO_NAMED_PRESET)
  } catch {
    // localStorage may be unavailable in some contexts
  }
}

/**
 * Loads theme preference from localStorage
 */
function loadTheme(): Theme {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY) as Theme | null
    if (stored && (THEMES as readonly string[]).includes(stored)) {
      return stored
    }
  } catch {
    // localStorage may be unavailable
  }
  return DEFAULT_THEME
}

/**
 * Loads accent color preference from localStorage
 */
function loadAccentColor(): AccentColor {
  try {
    const stored = localStorage.getItem(ACCENT_STORAGE_KEY) as AccentColor | null
    if (stored && ACCENT_COLORS.includes(stored)) {
      return stored
    }
  } catch {
    // localStorage may be unavailable
  }
  return DEFAULT_ACCENT
}

/**
 * Loads theme preset preference from localStorage
 */
function loadPreset(): ThemePreset {
  try {
    const stored = localStorage.getItem(PRESET_STORAGE_KEY) as ThemePreset | null
    if (stored && stored in THEME_PRESETS) {
      return stored
    }
  } catch {
    // localStorage may be unavailable
  }
  return NO_NAMED_PRESET
}

/** The preset a stored value selects, given the theme and accent actually applied */
export function presetFor(stored: ThemePreset, theme: Theme, accent: AccentColor): ThemePreset | null {
  if (stored !== NO_NAMED_PRESET) return stored
  const auto = THEME_PRESETS.auto
  return theme === auto.theme && accent === auto.accentColor ? 'auto' : null
}

/**
 * Applies a theme preset (combination of theme + accent + optional settings)
 */
function applyPreset(preset: ThemePreset): void {
  const config = THEME_PRESETS[preset]

  // Apply the base theme and accent from preset
  currentTheme.value = config.theme
  currentAccent.value = config.accentColor

  applyTheme(config.theme)
  applyAccentColor(config.accentColor)
}

/**
 * Theme management composable
 *
 * @example
 * ```vue
 * <script setup lang="ts">
 * import { useTheme } from '@/composables/useTheme'
 *
 * const {
 *   preset, setPreset,
 *   theme, accentColor,
 *   setTheme, setAccentColor,
 *   isDark, toggleTheme,
 *   availablePresets, availableThemes, availableAccents
 * } = useTheme()
 * </script>
 *
 * <template>
 *   <!-- Use preset picker (recommended) -->
 *   <select v-model="preset" @change="setPreset(preset)">
 *     <option v-for="p in availablePresets" :key="p" :value="p">
 *       {{ t(THEME_PRESETS[p].nameKey) }}
 *     </option>
 *   </select>
 *
 *   <!-- Or use individual controls -->
 *   <select v-model="theme" @change="setTheme(theme)">
 *     <option v-for="t in availableThemes" :key="t" :value="t">{{ t }}</option>
 *   </select>
 *
 *   <select v-model="accentColor" @change="setAccentColor(accentColor)">
 *     <option v-for="c in availableAccents" :key="c" :value="c">{{ c }}</option>
 *   </select>
 *
 *   <button @click="toggleTheme">Toggle Dark/Light</button>
 * </template>
 * ```
 */
export function useTheme() {
  /**
   * Initialize theme on first use
   * - Load from storage
   * - Apply to document
   * - Set up system preference listener
   */
  function initTheme(): void {
    if (isInitialized) return

    // Load saved preferences (preset takes precedence)
    const savedPreset = loadPreset()
    const savedTheme = loadTheme()
    const savedAccent = loadAccentColor()

    // If preset is saved, apply it (overrides individual theme/accent)
    if (savedPreset !== NO_NAMED_PRESET) {
      currentPreset.value = savedPreset
      applyPreset(savedPreset)
    } else {
      // Otherwise apply individual theme + accent
      currentTheme.value = savedTheme
      currentAccent.value = savedAccent
      currentPreset.value = presetFor(savedPreset, savedTheme, savedAccent)
      applyTheme(savedTheme)
      applyAccentColor(savedAccent)
    }

    // Listen for system preference changes
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    mediaQuery.addEventListener('change', () => {
      if (currentTheme.value === 'system') {
        applyTheme('system')
      }
    })

    isInitialized = true
  }

  /**
   * Set the theme
   * @param theme - Theme to apply ('dark', 'light', or 'system')
   */
  function setTheme(theme: Theme): void {
    currentTheme.value = theme
    saveTheme(theme)
    applyTheme(theme)
    clearNamedPreset()
  }

  /**
   * Set the accent color
   * @param accent - Accent color to apply
   */
  function setAccentColor(accent: AccentColor): void {
    currentAccent.value = accent
    saveAccentColor(accent)
    applyAccentColor(accent)
    clearNamedPreset()
  }

  /** A manual theme or accent change leaves no named preset */
  function clearNamedPreset(): void {
    currentPreset.value = presetFor(NO_NAMED_PRESET, currentTheme.value, currentAccent.value)
    savePreset(null)
  }

  /**
   * Set the theme preset
   * @param preset - Theme preset to apply
   */
  function setPreset(preset: ThemePreset): void {
    currentPreset.value = preset
    savePreset(preset)
    applyPreset(preset)
    // Also save individual theme + accent for fallback
    saveTheme(currentTheme.value)
    saveAccentColor(currentAccent.value)
  }

  /**
   * Toggle between dark and light themes
   * If currently on 'system', switch to opposite of current effective theme
   */
  function toggleTheme(): void {
    const effective = getEffectiveTheme(currentTheme.value)
    setTheme(effective === 'dark' ? 'light' : 'dark')
  }

  /**
   * Computed: Whether the effective theme is dark
   */
  const isDark = computed(() => {
    return getEffectiveTheme(currentTheme.value) === 'dark'
  })

  /**
   * Computed: Whether the effective theme is the plain light theme
   * (contrast and mono are light-based but are not this theme)
   */
  const isLight = computed(() => {
    return getEffectiveTheme(currentTheme.value) === 'light'
  })

  /**
   * Computed: The effective theme being displayed
   */
  const effectiveTheme = computed(() => {
    return getEffectiveTheme(currentTheme.value)
  })

  /**
   * Available theme options for UI dropdowns
   */
  const availableThemes: readonly Theme[] = THEMES

  /**
   * Available accent color options for UI dropdowns
   */
  const availableAccents: readonly AccentColor[] = ACCENT_COLORS

  /**
   * Available theme presets for UI dropdowns
   */
  const availablePresets: ThemePreset[] = [
    'auto',
    'brand-dark',
    'brand-light',
    'catppuccin-mocha',
    'catppuccin-latte',
    'solarized-dark',
    'solarized-light',
    'high-contrast-dark',
    'high-contrast-light',
    'midnight',
    'sunset',
    'forest',
    'rose',
  ]

  /**
   * Theme labels for UI display
   */
  const themeLabels: Record<Theme, string> = {
    dark: 'Dark',
    light: 'Light',
    contrast: 'High contrast',
    'contrast-dark': 'High contrast dark',
    mono: 'Monochrome',
    system: 'System',
  }

  /**
   * i18n keys for the theme labels; render sites translate with t() (#14785).
   * `themeLabels` stays as the untranslated default for non-Vue consumers.
   */
  const themeLabelKeys: Record<Theme, string> = {
    dark: 'ui.themeToggle.dark',
    light: 'ui.themeToggle.light',
    contrast: 'ui.themeToggle.highContrast',
    // The preset's own name (already translated in every locale), so the
    // picker needs no new key (#18253).
    'contrast-dark': 'ui.themePresets.names.high-contrast-dark',
    mono: 'ui.themeToggle.monochrome',
    system: 'ui.themeToggle.system',
  }

  /**
   * i18n keys for the accent labels (shared with the preferences panel)
   */
  const accentLabelKeys: Record<AccentColor, string> = {
    theme: 'ui.preferences.accentTheme',
    blue: 'ui.preferences.blue',
    green: 'ui.preferences.green',
    purple: 'ui.preferences.purple',
    orange: 'ui.preferences.orange',
    pink: 'ui.preferences.pink',
    teal: 'ui.preferences.teal',
    indigo: 'ui.preferences.indigo',
    red: 'ui.preferences.red',
  }

  /**
   * i18n keys for the accent descriptions (#18255)
   */
  const accentDescriptionKeys: Record<AccentColor, string> = {
    theme: 'ui.themeToggle.accentThemeDescription',
    blue: 'ui.themeToggle.accentBlueDescription',
    green: 'ui.themeToggle.accentGreenDescription',
    purple: 'ui.themeToggle.accentPurpleDescription',
    orange: 'ui.themeToggle.accentOrangeDescription',
    pink: 'ui.themeToggle.accentPinkDescription',
    teal: 'ui.themeToggle.accentTealDescription',
    indigo: 'ui.themeToggle.accentIndigoDescription',
    red: 'ui.themeToggle.accentRedDescription',
  }

  /**
   * Accent color labels for UI display
   */
  const accentLabels: Record<AccentColor, string> = {
    theme: 'Theme',
    blue: 'Blue',
    green: 'Green',
    purple: 'Purple',
    orange: 'Orange',
    pink: 'Pink',
    teal: 'Teal',
    indigo: 'Indigo',
    red: 'Red',
  }

  // Initialize on mount if in browser context
  if (getCurrentInstance()) {
    onMounted(() => {
      initTheme()
    })
  }

  // Also initialize immediately if document exists (for SSR compatibility)
  if (typeof document !== 'undefined' && !isInitialized) {
    initTheme()
  }

  return {
    /** Current theme preset (reactive) */
    preset: currentPreset,

    /** Current theme setting (reactive) */
    theme: currentTheme,

    /** Current accent color setting (reactive) */
    accentColor: currentAccent,

    /** Set the theme preset */
    setPreset,

    /** Set the theme */
    setTheme,

    /** Set the accent color */
    setAccentColor,

    /** Toggle between dark and light */
    toggleTheme,

    /** Initialize theme (call early to prevent flash) */
    initTheme,

    /** Whether effective theme is dark */
    isDark,

    /** Whether effective theme is light */
    isLight,

    /** The effective theme being displayed */
    effectiveTheme,

    /** Available theme preset options */
    availablePresets,

    /** Available theme options */
    availableThemes,

    /** Available accent color options */
    availableAccents,

    /** Theme display labels */
    themeLabels,
    themeLabelKeys,
    accentLabelKeys,
    accentDescriptionKeys,

    /** Accent color display labels */
    accentLabels,

    /** Preset configurations (for metadata access) */
    THEME_PRESETS,
  }
}

/**
 * Export a standalone init function for use in main.ts
 * Call this before app mount to prevent theme flash
 */
export function initializeTheme(): void {
  if (typeof document === 'undefined') return

  // Load saved preset first
  const savedPreset = loadPreset()

  if (savedPreset !== NO_NAMED_PRESET && savedPreset in THEME_PRESETS) {
    // Apply preset
    const config = THEME_PRESETS[savedPreset]
    currentPreset.value = savedPreset
    currentTheme.value = config.theme
    currentAccent.value = config.accentColor
    applyTheme(config.theme)
    applyAccentColor(config.accentColor)
  } else {
    // Fallback to individual settings
    const savedTheme = loadTheme()
    const savedAccent = loadAccentColor()
    applyTheme(savedTheme)
    applyAccentColor(savedAccent)
    currentTheme.value = savedTheme
    currentAccent.value = savedAccent
    currentPreset.value = presetFor(savedPreset, savedTheme, savedAccent)
  }

  isInitialized = true
}

export default useTheme
