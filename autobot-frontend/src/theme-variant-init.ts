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

try {
  const variant = localStorage.getItem(THEME_VARIANT_STORAGE_KEY)
  if (variant && variant !== 'default') {
    document.documentElement.setAttribute('data-theme-variant', variant)
  }
} catch {
  // localStorage may be unavailable (private mode / sandboxed) — fall back to default.
}
