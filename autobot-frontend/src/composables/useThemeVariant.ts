// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * useThemeVariant.ts - Theme Variant Management Composable
 * Issue #9274 / MVA-3096: Ember Theme Integration
 * Issue #10472: Runtime installed-theme delivery
 *
 * Provides reactive theme variant switching:
 * - Built-in Default/Ember variant modes (build-time)
 * - Admin-installed theme packages, delivered at runtime via fetch +
 *   adoptedStyleSheets (CSP-safe: no inline <style>, no cross-origin <link>)
 * - LocalStorage persistence
 * - Works alongside existing useTheme composable
 *
 * Usage:
 *   const { themeVariant, setThemeVariant, variantLabels } = useThemeVariant()
 *   setThemeVariant('ember')  // or 'default', or an installed theme id
 */

import { ref, readonly, computed, watch, onMounted, getCurrentInstance } from 'vue'
import { getBackendUrl } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'
import { fetchInstalledThemes, type InstalledTheme } from './useThemeRegistry'

const log = createLogger('ThemeVariant')

/** Built-in theme variant options */
export type BuiltinThemeVariant = 'default' | 'ember'

/** A theme variant id — a built-in or an installed theme's id. */
export type ThemeVariant = string

/** Storage key for persisting variant preference */
const THEME_VARIANT_STORAGE_KEY = 'autobot-theme-variant'

/** All built-in variants — single source of truth for validation. */
const VALID_VARIANTS: readonly BuiltinThemeVariant[] = ['default', 'ember']

/**
 * Default variant when the user has no saved preference.
 *
 * The user GUI ships the warm "ember" palette by default (Issue #10461 / #9274).
 * Build-time overridable via `VITE_DEFAULT_THEME_VARIANT` so a deployment that
 * shares this build with the /slm control plane can pin `default` and keep the
 * current look. An unset or unrecognised value falls back to `ember`.
 */
function resolveDefaultVariant(): BuiltinThemeVariant {
  const fromEnv = import.meta.env?.VITE_DEFAULT_THEME_VARIANT as string | undefined
  if (fromEnv && (VALID_VARIANTS as readonly string[]).includes(fromEnv)) {
    return fromEnv as BuiltinThemeVariant
  }
  return 'ember'
}

/** Default variant when no preference is set */
const DEFAULT_VARIANT: BuiltinThemeVariant = resolveDefaultVariant()

/** Global reactive state (singleton pattern) */
const currentVariant = ref<ThemeVariant>(DEFAULT_VARIANT)

/** Installed theme descriptors fetched from the backend registry (#10472) */
const installedThemes = ref<InstalledTheme[]>([])

/** Installed theme ids, merged into availableVariants at runtime (#10472) */
const runtimeVariantIds = ref<string[]>([])

/** Constructed stylesheets already adopted, keyed by theme id (idempotent). */
const adopted = new Set<string>()

/** Track if initialized */
let isInitialized = false

function isBuiltin(variant: ThemeVariant): boolean {
  return (VALID_VARIANTS as readonly string[]).includes(variant)
}

/**
 * Fetch an installed theme's CSS and adopt it as a constructed stylesheet.
 *
 * CSP-safe: the CSS text is fetched same-credentials from the backend and
 * adopted via `document.adoptedStyleSheets` — never injected as an inline
 * `<style>` or a cross-origin `<link>`. `apiClient.get` always parses JSON, so
 * a raw `fetch` is used here to retrieve the CSS as text.
 */
async function ensureThemeStylesheet(id: string): Promise<void> {
  if (adopted.has(id)) return
  const response = await fetch(`${getBackendUrl()}/api/themes/${id}/theme.css`, {
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error(`Failed to fetch theme CSS for '${id}': HTTP ${response.status}`)
  }
  const css = await response.text()
  const sheet = new CSSStyleSheet()
  await sheet.replace(css)
  document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet]
  adopted.add(id)
}

/**
 * Applies the theme variant to the document root element.
 *
 * Built-in variants apply synchronously (no-flash parity preserved). Installed
 * variants first fetch + adopt their stylesheet; on failure the previous
 * variant is restored and the error surfaced to the caller.
 */
async function applyThemeVariant(variant: ThemeVariant, previous: ThemeVariant): Promise<void> {
  if (variant === 'default') {
    document.documentElement.removeAttribute('data-theme-variant')
    return
  }
  if (!isBuiltin(variant)) {
    try {
      await ensureThemeStylesheet(variant)
    } catch (err) {
      log.error(`Failed to apply installed theme '${variant}'; reverting`, err)
      currentVariant.value = previous
      throw err
    }
  }
  document.documentElement.setAttribute('data-theme-variant', variant)
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
 * Loads theme variant preference from localStorage. Accepts built-in variants
 * and any currently-known installed theme id.
 */
function loadThemeVariant(): ThemeVariant {
  try {
    const stored = localStorage.getItem(THEME_VARIANT_STORAGE_KEY)
    if (stored && (isBuiltin(stored) || runtimeVariantIds.value.includes(stored))) {
      return stored
    }
  } catch {
    // localStorage may be unavailable
  }
  return DEFAULT_VARIANT
}

/**
 * Fetch installed themes and merge their ids into the available variants.
 * Safe to call repeatedly; degrades to built-ins only on failure.
 */
async function loadInstalledThemes(): Promise<void> {
  try {
    const themes = await fetchInstalledThemes()
    installedThemes.value = Array.isArray(themes) ? themes : []
    runtimeVariantIds.value = installedThemes.value.map((t) => t.id)
  } catch (err) {
    log.warn('Failed to load installed themes; using built-ins only', err)
    installedThemes.value = []
    runtimeVariantIds.value = []
  }
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
    void applyThemeVariant(savedVariant, savedVariant)

    // Watch for changes and persist
    watch(currentVariant, (variant) => {
      saveThemeVariant(variant)
    })

    isInitialized = true

    // Fire-and-forget: installed themes appear once the registry loads.
    void loadInstalledThemes()
  }

  /**
   * Set the theme variant.
   * @param variant - Theme variant to apply ('default', 'ember', or an installed id)
   * @returns a Promise that resolves once the variant (incl. any installed
   *   stylesheet) has been applied. Rejects — and reverts — on apply failure.
   */
  async function setThemeVariant(variant: ThemeVariant): Promise<void> {
    const previous = currentVariant.value
    currentVariant.value = variant
    await applyThemeVariant(variant, previous)
  }

  /**
   * Available theme variant options — built-ins plus installed theme ids.
   */
  const availableVariants = computed<ThemeVariant[]>(() => [...VALID_VARIANTS, ...runtimeVariantIds.value])

  /**
   * Theme variant labels for UI display (built-ins + installed theme names).
   */
  const variantLabels = computed<Record<string, string>>(() => {
    const labels: Record<string, string> = {
      default: 'Default',
      ember: 'Ember',
    }
    for (const theme of installedThemes.value) {
      labels[theme.id] = theme.name
    }
    return labels
  })

  /**
   * Theme variant descriptions (built-ins + installed author/version).
   */
  const variantDescriptions = computed<Record<string, string>>(() => {
    const descriptions: Record<string, string> = {
      default: 'Standard AutoBot theme with cool neutrals',
      ember: 'Warm palette with marigold accents and apricot-plum tones',
    }
    for (const theme of installedThemes.value) {
      descriptions[theme.id] = `v${theme.version} — ${theme.author}`
    }
    return descriptions
  })

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

    /** Set the theme variant (async — awaits installed-theme stylesheet adopt) */
    setThemeVariant,

    /** Available theme variant options (built-ins + installed, reactive) */
    availableVariants,

    /** Installed theme descriptors from the backend registry */
    installedThemes: readonly(installedThemes),

    /** Fetch + merge installed themes into availableVariants */
    loadInstalledThemes,

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
  void applyThemeVariant(savedVariant, savedVariant)
  currentVariant.value = savedVariant
  isInitialized = true
}

export default useThemeVariant
