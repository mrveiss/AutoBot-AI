/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * useTheme.ts - Theme Management Composable
 * Issue #704: CSS Design System - Centralized Theming & SSOT Styles
 *
 * Provides reactive theme switching capabilities with:
 * - Dark/Light/System theme modes
 * - LocalStorage persistence
 * - System preference detection
 * - Instant theme switching (<100ms)
 *
 * Usage:
 *   const { theme, setTheme, isDark, toggleTheme } = useTheme()
 *   setTheme('dark')  // or 'light', 'system'
 */

import { ref, computed, watch, onMounted } from 'vue'

/** Available theme options */
export type Theme = 'dark' | 'light' | 'system'

/** Storage key for persisting theme preference */
const STORAGE_KEY = 'autobot-theme'

/** Default theme when no preference is set */
const DEFAULT_THEME: Theme = 'dark'

/** Global reactive theme state (singleton pattern) */
const currentTheme = ref<Theme>(DEFAULT_THEME)

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
 * Saves theme preference to localStorage
 */
function saveTheme(theme: Theme): void {
  try {
    localStorage.setItem(STORAGE_KEY, theme)
  } catch {
    // localStorage may be unavailable in some contexts
  }
}

/**
 * Loads theme preference from localStorage
 */
function loadTheme(): Theme {
  try {
    const stored = localStorage.getItem(STORAGE_KEY) as Theme | null
    if (stored && ['dark', 'light', 'system'].includes(stored)) {
      return stored
    }
  } catch {
    // localStorage may be unavailable
  }
  return DEFAULT_THEME
}

/**
 * Theme management composable
 *
 * @example
 * ```vue
 * <script setup lang="ts">
 * import { useTheme } from '@/composables/useTheme'
 *
 * const { theme, setTheme, isDark, toggleTheme, availableThemes } = useTheme()
 * </script>
 *
 * <template>
 *   <select v-model="theme" @change="setTheme(theme)">
 *     <option v-for="t in availableThemes" :key="t" :value="t">{{ t }}</option>
 *   </select>
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

    // Load saved preference
    const savedTheme = loadTheme()
    currentTheme.value = savedTheme

    // Apply immediately to prevent flash
    applyTheme(savedTheme)

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
   * Theme labels for UI display
   */
  const themeLabels: Record<Theme, string> = {
    dark: 'Dark',
    light: 'Light',
    system: 'System',
  }

  // Initialize on mount if in browser context
  onMounted(() => {
    initTheme()
  })

  // Also initialize immediately if document exists (for SSR compatibility)
  if (typeof document !== 'undefined' && !isInitialized) {
    initTheme()
  }

  return {
    /** Current theme setting (reactive) */
    theme: currentTheme,

    /** Set the theme */
    setTheme,

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

    /** Theme display labels */
    themeLabels,
  }
}

/**
 * Export a standalone init function for use in main.ts
 * Call this before app mount to prevent theme flash
 */
export function initializeTheme(): void {
  if (typeof document === 'undefined') return

  const savedTheme = loadTheme()
  applyTheme(savedTheme)
  currentTheme.value = savedTheme
  isInitialized = true
}

export default useTheme
