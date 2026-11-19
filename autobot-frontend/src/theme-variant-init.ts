// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * theme-variant-init.ts - No-flash theme-variant bootstrap (Issue #9274 / MVA-3096)
 *
 * Applies the persisted theme variant to <html> as early as possible so the
 * correct Ember/default palette is present before the Vue bundle mounts,
 * avoiding a flash of the wrong theme.
 *
 * This was previously an inline <script> in index.html. It is now a bundled
 * module referenced via `<script type="module" src>` so the co-located strict
 * Content-Security-Policy (`script-src 'self'`, no `unsafe-inline`) passes
 * without weakening the policy (Issue #9966).
 *
 * Storage key mirrors THEME_VARIANT_STORAGE_KEY in composables/useThemeVariant.ts.
 */

const THEME_VARIANT_STORAGE_KEY = 'autobot-theme-variant'
const VALID_VARIANTS = ['default', 'ember']

/**
 * Default variant for the user GUI: `default`, the Refined palette (#18161). Ember was
 * the default from #10461 / #9274 until the Refined redesign (#18223): it re-declares
 * the surface, text and border tokens, so as a default it would hide every theme.
 * Ember stays selectable, and a deployment can pin it at build time with
 * `VITE_DEFAULT_THEME_VARIANT=ember` (Vite inlines this).
 * Mirrors resolveDefaultVariant() in composables/useThemeVariant.ts.
 */
function defaultVariant(): string {
  const fromEnv = import.meta.env?.VITE_DEFAULT_THEME_VARIANT as string | undefined
  return fromEnv && VALID_VARIANTS.includes(fromEnv) ? fromEnv : 'default'
}

try {
  const stored = localStorage.getItem(THEME_VARIANT_STORAGE_KEY)
  const variant = stored && VALID_VARIANTS.includes(stored) ? stored : defaultVariant()
  // 'default' = base theme = no attribute; any other known variant sets it (no-flash).
  if (variant !== 'default') {
    document.documentElement.setAttribute('data-theme-variant', variant)
  }
} catch {
  // localStorage unavailable (private mode / sandboxed): still apply the env default.
  const fallback = defaultVariant()
  if (fallback !== 'default') {
    document.documentElement.setAttribute('data-theme-variant', fallback)
  }
}

/**
 * Minimal/Full interface mode (#18240): the pre-mount copy of `data-ui`, the
 * one sanctioned writer besides composables/useUiMode.ts (which owns it after
 * mount). Keys and the default mirror UI_MODE_STORAGE_KEY / DEFAULT_MODE there.
 */
try {
  const mode = localStorage.getItem('autobot-ui-mode')
  document.documentElement.setAttribute('data-ui', mode === 'minimal' ? 'minimal' : 'full')
} catch {
  document.documentElement.setAttribute('data-ui', 'full')
}
