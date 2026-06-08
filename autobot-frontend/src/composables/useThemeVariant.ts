// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * useThemeVariant.ts - Theme Variant Management Composable
 * Issue #9274 / MVA-3096: Ember Theme Integration
 *
 * Provides reactive theme variant switching for Ember theme:
 * - Default/Ember variant modes
 * - LocalStorage persistence
 * - Works alongside existing useTheme composable
 *
 * Usage:
 *   const { themeVariant, setThemeVariant, variantLabels } = useThemeVariant()
 *   setThemeVariant('ember')  // or 'default'
 */

import { ref, readonly, watch, onMounted, getCurrentInstance } from 'vue'

/** Available theme variant options */
export type ThemeVariant = 'default' | 'ember'

/** Storage key for persisting variant preference */
const THEME_VARIANT_STORAGE_KEY = 'autobot-theme-variant'

/** Default variant when no preference is set */
const DEFAULT_VARIANT: ThemeVariant = 'default'

/** Global reactive state (singleton pattern) */
const currentVariant = ref<ThemeVariant>(DEFAULT_VARIANT)

/** Track if initialized */
let isInitialized = false

/**
 * Applies the theme variant to the document root element
 */
function applyThemeVariant(variant: ThemeVariant): void {
  if (variant === 'default') {
    document.documentElement.removeAttribute('data-theme-variant')
  } else {
    document.documentElement.setAttribute('data-theme-variant', variant)
  }
}

/**
 * Saves theme variant preference to localStorage
 */
function saveThemeVariant(variant: ThemeVariant): void {
  try {
    localStorage.setItem(THEME_VARIANT_STORAGE_KEY, variant)
  } catch {
    // localStorage may be unavailable in some contexts
  }
}

/**
 * Loads theme variant preference from localStorage
 */
function loadThemeVariant(): ThemeVariant {
  try {
    const stored = localStorage.getItem(THEME_VARIANT_STORAGE_KEY) as ThemeVariant | null
    const validVariants: ThemeVariant[] = ['default', 'ember']
    if (stored && validVariants.includes(stored)) {
      return stored
    }
  } catch {
    // localStorage may be unavailable
  }
  return DEFAULT_VARIANT
}

/**
 * Theme variant management composable
 *
 * @example
 * ```vue
 * <script setup lang="ts">
 * import { useThemeVariant } from '@/composables/useThemeVariant'
 *
 * const {
 *   themeVariant,
 *   setThemeVariant,
 *   variantLabels,
 *   variantDescriptions
 * } = useThemeVariant()
 * </script>
 *
 * <template>
 *   <select :value="themeVariant" @change="setThemeVariant($event.target.value)">
 *     <option v-for="v in availableVariants" :key="v" :value="v">
 *       {{ variantLabels[v] }}
 *     </option>
 *   </select>
 * </template>
 * ```
 */
export function useThemeVariant() {
  /**
   * Initialize variant on first use
   */
  function initVariant(): void {
    if (isInitialized) return

    const savedVariant = loadThemeVariant()
    currentVariant.value = savedVariant
    applyThemeVariant(savedVariant)

    // Watch for changes and persist
    watch(currentVariant, (variant) => {
      applyThemeVariant(variant)
      saveThemeVariant(variant)
    })

    isInitialized = true
  }

  /**
   * Set the theme variant
   * @param variant - Theme variant to apply ('default' or 'ember')
   */
  function setThemeVariant(variant: ThemeVariant): void {
    currentVariant.value = variant
  }

  /**
   * Available theme variant options
   */
  const availableVariants: ThemeVariant[] = ['default', 'ember']

  /**
   * Theme variant labels for UI display
   */
  const variantLabels: Record<ThemeVariant, string> = {
    default: 'Default',
    ember: 'Ember',
  }

  /**
   * Theme variant descriptions
   */
  const variantDescriptions: Record<ThemeVariant, string> = {
    default: 'Standard AutoBot theme with cool neutrals',
    ember: 'Warm palette with marigold accents and apricot-plum tones',
  }

  // Initialize on mount if in browser context
  if (getCurrentInstance()) {
    onMounted(() => {
      initVariant()
    })
  }

  // Also initialize immediately if document exists (for SSR compatibility)
  if (typeof document !== 'undefined' && !isInitialized) {
    initVariant()
  }

  return {
    /** Current theme variant setting (reactive) */
    themeVariant: readonly(currentVariant),

    /** Set the theme variant */
    setThemeVariant,

    /** Available theme variant options */
    availableVariants,

    /** Theme variant display labels */
    variantLabels,

    /** Theme variant descriptions */
    variantDescriptions,

    /** Initialize variant (call early to prevent flash) */
    initVariant,
  }
}

/**
 * Export a standalone init function for use in main.ts
 * Call this before app mount to prevent theme variant flash
 */
export function initializeThemeVariant(): void {
  if (typeof document === 'undefined') return

  const savedVariant = loadThemeVariant()
  applyThemeVariant(savedVariant)
  currentVariant.value = savedVariant
  isInitialized = true
}

export default useThemeVariant
