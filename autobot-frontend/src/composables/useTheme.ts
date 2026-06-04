/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * useTheme.ts - Theme Management Composable
 * Issue #704: CSS Design System - Centralized Theming & SSOT Styles
 * Issue #8988: User-Selectable Theme System - Custom Accent Colors
 *
 * Provides reactive theme switching capabilities with:
 * - Dark/Light/System theme modes
 * - Custom accent color presets
 * - LocalStorage persistence
 * - System preference detection
 * - Instant theme switching (<100ms)
 *
 * Usage:
 *   const { theme, accentColor, setTheme, setAccentColor, isDark, toggleTheme } = useTheme()
 *   setTheme('dark')  // or 'light', 'system'
 *   setAccentColor('green')  // or 'purple', 'orange', etc.
 */

import { ref, computed, onMounted, getCurrentInstance } from 'vue'

/** Available theme options */
export type Theme = 'dark' | 'light' | 'system'

/** Available accent color options */
export type AccentColor = 'blue' | 'green' | 'purple' | 'orange' | 'pink' | 'teal' | 'indigo' | 'red'

/** Storage keys for persisting preferences */
const THEME_STORAGE_KEY = 'autobot-theme'
const ACCENT_STORAGE_KEY = 'autobot-accent-color'

/** Default values when no preference is set */
const DEFAULT_THEME: Theme = 'dark'
const DEFAULT_ACCENT: AccentColor = 'blue'

/** Global reactive state (singleton pattern) */
const currentTheme = ref<Theme>(DEFAULT_THEME)
const currentAccent = ref<AccentColor>(DEFAULT_ACCENT)

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
 * Theme management composable
 *
 * @example
 * ```vue
 * <script setup lang="ts">
 * import { useTheme } from '@/composables/useTheme'
 *
 * const {
 *   theme, accentColor,
 *   setTheme, setAccentColor,
 *   isDark, toggleTheme,
 *   availableThemes, availableAccents
 * } = useTheme()
 * </script>
 *
 * <template>
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

    // Load saved preferences
    const savedTheme = loadTheme()
    const savedAccent = loadAccentColor()

    currentTheme.value = savedTheme
    currentAccent.value = savedAccent

    // Apply immediately to prevent flash
    applyTheme(savedTheme)
    applyAccentColor(savedAccent)

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
  }

  /**
   * Set the accent color
   * @param accent - Accent color to apply
   */
  function setAccentColor(accent: AccentColor): void {
    currentAccent.value = accent
    saveAccentColor(accent)
    applyAccentColor(accent)
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
    /** Current theme setting (reactive) */
    theme: currentTheme,

    /** Current accent color setting (reactive) */
    accentColor: currentAccent,

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
  }
}

/**
 * Export a standalone init function for use in main.ts
 * Call this before app mount to prevent theme flash
 */
export function initializeTheme(): void {
  if (typeof document === 'undefined') return

  const savedTheme = loadTheme()
  const savedAccent = loadAccentColor()

  applyTheme(savedTheme)
  applyAccentColor(savedAccent)

  currentTheme.value = savedTheme
  currentAccent.value = savedAccent
  isInitialized = true
}

export default useTheme
