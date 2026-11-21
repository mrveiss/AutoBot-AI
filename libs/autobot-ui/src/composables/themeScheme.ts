// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * themeScheme.ts - the theme names, their storage and their `data-theme` application,
 * shared by the user frontend (useTheme) and the SLM frontend (useSlmTheme) so the two
 * apps cannot drift (#18239). One definition of: which themes exist, the localStorage
 * key the choice lives under, and how a choice reaches the document root.
 */

/** The built-in themes a `data-theme` attribute can carry. `contrast` (high contrast)
 * and `mono` (monochrome) are light-based accessibility and corporate themes;
 * `contrast-dark` is high contrast on a dark base. */
export const EFFECTIVE_THEMES = ['light', 'dark', 'contrast', 'contrast-dark', 'mono'] as const
export type EffectiveTheme = (typeof EFFECTIVE_THEMES)[number]

/** Theme options: the built-ins plus `system`, which follows the OS between `light` and `dark`. */
export const THEMES = [...EFFECTIVE_THEMES, 'system'] as const
export type Theme = (typeof THEMES)[number]

/** The localStorage key both apps keep the chosen theme under. */
export const THEME_STORAGE_KEY = 'autobot-theme'

/** The `color-scheme` a theme renders with (native controls, scrollbars). */
export function colorSchemeFor(theme: EffectiveTheme): 'dark' | 'light' {
  return theme === 'dark' || theme === 'contrast-dark' ? 'dark' : 'light'
}

/** The concrete theme a choice renders as; `system` follows the OS. */
export function resolveTheme(theme: Theme): EffectiveTheme {
  if (theme === 'system') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return theme
}

/** Puts a theme on the document root: the `data-theme` attribute and the `color-scheme`. */
export function applyThemeToDocument(theme: Theme): EffectiveTheme {
  const effective = resolveTheme(theme)
  document.documentElement.setAttribute('data-theme', effective)
  document.documentElement.style.colorScheme = colorSchemeFor(effective)
  return effective
}

/** The stored theme when it is one of `allowed`, else null (also when storage is unavailable). */
export function readStoredTheme(allowed: readonly Theme[] = THEMES): Theme | null {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY)
    return stored && (allowed as readonly string[]).includes(stored) ? (stored as Theme) : null
  } catch {
    return null
  }
}

/** Persists the theme choice; storage may be unavailable, in which case the choice is session-only. */
export function writeStoredTheme(theme: Theme): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme)
  } catch {
    // localStorage may be unavailable in some contexts
  }
}
