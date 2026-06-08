/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * useTheme.ts - Theme Management Composable
 * Issue #704: CSS Design System - Centralized Theming & SSOT Styles
 * Issue #8988: User-Selectable Theme System - Custom Theme Presets
 *
 * Provides reactive theme switching capabilities with:
 * - Dark/Light/System theme modes
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

/** Available theme options */
export type Theme = 'dark' | 'light' | 'system'

/** Available accent color options */
export type AccentColor = 'blue' | 'green' | 'purple' | 'orange' | 'pink' | 'teal' | 'indigo' | 'red'

/** Theme preset options - named combinations of theme + accent + optional density */
export type ThemePreset =
  | 'auto' // System preference
  | 'catppuccin-mocha' // Dark + Purple
  | 'catppuccin-latte' // Light + Purple
  | 'solarized-dark' // Dark + Teal
  | 'solarized-light' // Light + Teal
  | 'high-contrast-dark' // Dark + Blue (high contrast)
  | 'high-contrast-light' // Light + Blue (high contrast)
  | 'brand-dark' // Dark + AutoBot brand color (teal)
  | 'brand-light' // Light + AutoBot brand color (teal)
  | 'midnight' // Dark + Indigo
  | 'sunset' // Light + Orange
  | 'forest' // Dark + Green
  | 'rose' // Light + Pink

/** Configuration for each theme preset */
export interface ThemePresetConfig {
  name: string
  description: string
  theme: Theme
  accentColor: AccentColor
  highContrast?: boolean
}

/** Preset configurations */
export const THEME_PRESETS: Record<ThemePreset, ThemePresetConfig> = {
  auto: {
    name: 'Auto',
    description: 'Follows system preference',
    theme: 'system',
    accentColor: 'blue',
  },
  'catppuccin-mocha': {
    name: 'Catppuccin Mocha',
    description: 'Warm dark theme with purple accents',
    theme: 'dark',
    accentColor: 'purple',
  },
  'catppuccin-latte': {
    name: 'Catppuccin Latte',
    description: 'Soft light theme with purple accents',
    theme: 'light',
    accentColor: 'purple',
  },
  'solarized-dark': {
    name: 'Solarized Dark',
    description: 'Classic dark theme with cyan accents',
    theme: 'dark',
    accentColor: 'teal',
  },
  'solarized-light': {
    name: 'Solarized Light',
    description: 'Classic light theme with cyan accents',
    theme: 'light',
    accentColor: 'teal',
  },
  'high-contrast-dark': {
    name: 'High Contrast Dark',
    description: 'Maximum readability dark theme',
    theme: 'dark',
    accentColor: 'blue',
    highContrast: true,
  },
  'high-contrast-light': {
    name: 'High Contrast Light',
    description: 'Maximum readability light theme',
    theme: 'light',
    accentColor: 'blue',
    highContrast: true,
  },
  'brand-dark': {
    name: 'AutoBot Dark',
    description: 'Official AutoBot dark theme',
    theme: 'dark',
    accentColor: 'teal',
  },
  'brand-light': {
    name: 'AutoBot Light',
    description: 'Official AutoBot light theme',
    theme: 'light',
    accentColor: 'teal',
  },
  midnight: {
    name: 'Midnight',
    description: 'Deep blue night theme',
    theme: 'dark',
    accentColor: 'indigo',
  },
  sunset: {
    name: 'Sunset',
    description: 'Warm orange light theme',
    theme: 'light',
    accentColor: 'orange',
  },
  forest: {
    name: 'Forest',
    description: 'Natural green dark theme',
    theme: 'dark',
    accentColor: 'green',
  },
  rose: {
    name: 'Rose',
    description: 'Elegant pink light theme',
    theme: 'light',
    accentColor: 'pink',
  },
}

/** Storage keys for persisting preferences */
const THEME_STORAGE_KEY = 'autobot-theme'
const ACCENT_STORAGE_KEY = 'autobot-accent-color'
const PRESET_STORAGE_KEY = 'autobot-theme-preset'

/** Default values when no preference is set */
const DEFAULT_THEME: Theme = 'dark'
const DEFAULT_ACCENT: AccentColor = 'blue'
const DEFAULT_PRESET: ThemePreset = 'auto'

/** Global reactive state (singleton pattern) */
const currentTheme = ref<Theme>(DEFAULT_THEME)
const currentAccent = ref<AccentColor>(DEFAULT_ACCENT)
const currentPreset = ref<ThemePreset>(DEFAULT_PRESET)

/** Track if theme has been initialized */
let isInitialized = false

/**
 * Determines the effective theme based on current setting and system preference
 */
function getEffectiveTheme(theme: Theme): 'dark' | 'light' {
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
  document.documentElement.style.colorScheme = effectiveTheme
}

/**
 * Applies the accent color to the document root element
 */
function applyAccentColor(accent: AccentColor): void {
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
function savePreset(preset: ThemePreset): void {
  try {
    localStorage.setItem(PRESET_STORAGE_KEY, preset)
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
    if (stored && ['dark', 'light', 'system'].includes(stored)) {
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
    const validAccents: AccentColor[] = ['blue', 'green', 'purple', 'orange', 'pink', 'teal', 'indigo', 'red']
    if (stored && validAccents.includes(stored)) {
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
  return DEFAULT_PRESET
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

  // Apply high contrast mode if specified
  if (config.highContrast) {
    document.documentElement.setAttribute('data-high-contrast', 'true')
  } else {
    document.documentElement.removeAttribute('data-high-contrast')
  }
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
 *       {{ THEME_PRESETS[p].name }}
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
    if (savedPreset !== DEFAULT_PRESET) {
      currentPreset.value = savedPreset
      applyPreset(savedPreset)
    } else {
      // Otherwise apply individual theme + accent
      currentTheme.value = savedTheme
      currentAccent.value = savedAccent
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
    // Clear preset when manually changing theme
    currentPreset.value = 'auto'
    savePreset('auto')
  }

  /**
   * Set the accent color
   * @param accent - Accent color to apply
   */
  function setAccentColor(accent: AccentColor): void {
    currentAccent.value = accent
    saveAccentColor(accent)
    applyAccentColor(accent)
    // Clear preset when manually changing accent
    currentPreset.value = 'auto'
    savePreset('auto')
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
   * Computed: Whether the effective theme is light
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
  const availableThemes: Theme[] = ['dark', 'light', 'system']

  /**
   * Available accent color options for UI dropdowns
   */
  const availableAccents: AccentColor[] = [
    'blue',
    'green',
    'purple',
    'orange',
    'pink',
    'teal',
    'indigo',
    'red',
  ]

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
    system: 'System',
  }

  /**
   * Accent color labels for UI display
   */
  const accentLabels: Record<AccentColor, string> = {
    blue: 'Blue',
    green: 'Green',
    purple: 'Purple',
    orange: 'Orange',
    pink: 'Pink',
    teal: 'Teal',
    indigo: 'Indigo',
    red: 'Red',
  }

  /**
   * Accent color descriptions
   */
  const accentDescriptions: Record<AccentColor, string> = {
    blue: 'Electric Blue — Technical Precision',
    green: 'Emerald — Growth & Success',
    purple: 'Violet — Creative & Premium',
    orange: 'Amber — Energy & Innovation',
    pink: 'Rose — Friendly & Approachable',
    teal: 'Cyan — Modern & Professional',
    indigo: 'Deep Blue — Trust & Stability',
    red: 'Crimson — Bold & Urgent',
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

    /** Accent color display labels */
    accentLabels,

    /** Accent color descriptions */
    accentDescriptions,

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

  if (savedPreset !== DEFAULT_PRESET && savedPreset in THEME_PRESETS) {
    // Apply preset
    const config = THEME_PRESETS[savedPreset]
    currentPreset.value = savedPreset
    currentTheme.value = config.theme
    currentAccent.value = config.accentColor
    applyTheme(config.theme)
    applyAccentColor(config.accentColor)
    if (config.highContrast) {
      document.documentElement.setAttribute('data-high-contrast', 'true')
    }
  } else {
    // Fallback to individual settings
    const savedTheme = loadTheme()
    const savedAccent = loadAccentColor()
    applyTheme(savedTheme)
    applyAccentColor(savedAccent)
    currentTheme.value = savedTheme
    currentAccent.value = savedAccent
  }

  isInitialized = true
}

export default useTheme
