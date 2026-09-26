// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Shared CSS variable accessor for JavaScript-side color/font values.
 * Issue #704: CSS-to-JS bridge used by charts, Cytoscape, D3, etc.
 * Issue #1602: Extracted from component-local duplicates.
 *
 * @param name - CSS custom property name (e.g., '--chart-blue')
 * @param fallback - Default value for SSR/testing or missing property
 * @returns The resolved CSS variable value or fallback
 */
export function getCssVar(name: string, fallback = ''): string {
  if (typeof document === 'undefined') return fallback
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

/**
 * Map a single severity level to a theme-aware CSS color.
 * Issue #704: Design token colors for severity indicators.
 * Issue #1606: Restored as shared utility (removed in #1587).
 * Issue #1667: Retained for canvas-based rendering contexts (Cytoscape node colors,
 * Chart.js inline dataset colors, D3 inline styles) where CSS class binding is not
 * available. Components that use HTML elements should prefer `:class="'severity-' + level"`
 * with scoped CSS tokens instead.
 */
export function getSeverityColor(severity: string | undefined): string {
  switch (severity?.toLowerCase()) {
    case 'critical': return getCssVar('--color-error-hover', '#dc2626')
    case 'high': return getCssVar('--chart-orange', '#ea580c')
    case 'medium': return getCssVar('--color-warning-hover', '#d97706')
    case 'low': return getCssVar('--color-info', '#3b82f6')
    default: return getCssVar('--color-success-hover', '#059669')
  }
}

/**
 * Map an array of severity labels to theme-aware CSS colors.
 * Issue #704: Batch color resolution for chart datasets.
 * Issue #1606: Extracted from SeverityBarChart.vue.
 */
export function getSeverityColors(severities: string[]): string[] {
  const severityColors: Record<string, string> = {
    critical: getCssVar('--color-error-hover', '#dc2626'),
    high: getCssVar('--color-error', '#ef4444'),
    error: getCssVar('--color-error', '#ef4444'),
    medium: getCssVar('--color-warning', '#f59e0b'),
    warning: getCssVar('--color-warning', '#f59e0b'),
    low: getCssVar('--color-info', '#3b82f6'),
    info: getCssVar('--color-info', '#3b82f6'),
    hint: getCssVar('--color-success', '#10b981'),
    suggestion: getCssVar('--color-success', '#10b981'),
    trivial: getCssVar('--text-tertiary', '#64748b')
  }

  return severities.map((s) => {
    const key = s.toLowerCase()
    return severityColors[key] || getCssVar('--chart-indigo', '#6366f1')
  })
}

// ==================== Notification chrome (#17560) ====================

/** The three colours a notification surface needs. */
export interface NotificationColors {
  /** Surface fill. */
  background: string
  /** 1px border and icon tint. */
  border: string
  /** Foreground text. */
  text: string
}

/** What a notification is telling the user, independent of who is showing it. */
export type NotificationKind = 'info' | 'success' | 'warning' | 'error'

//: name -> [background token, border token, text token]
const _NOTIFICATION_TOKENS: Record<NotificationKind, readonly [string, string, string]> = {
  info: ['--color-info-bg', '--color-info', '--color-info-hover'],
  success: ['--color-success-bg', '--color-success', '--color-success-hover'],
  warning: ['--color-warning-bg', '--color-warning', '--color-warning-hover'],
  error: ['--color-error-bg', '--color-error', '--color-error-hover'],
}

//: The literals each token falls back to when the document cannot be read --
//: SSR, unit tests, or a theme that has not loaded. One palette, so the
//: fallback path is as consistent as the themed one; before #17560 three
//: call sites in `utils/cacheManagement.ts` each carried their own.
const _NOTIFICATION_FALLBACKS: Record<NotificationKind, readonly [string, string, string]> = {
  info: ['#eff6ff', '#3b82f6', '#1d4ed8'],
  success: ['#ecfdf5', '#10b981', '#065f46'],
  warning: ['#fef3cd', '#f59e0b', '#92400e'],
  error: ['#fef2f2', '#ef4444', '#dc2626'],
}

/**
 * Theme-aware colours for a notification surface (#17560).
 *
 * `utils/cacheManagement.ts` held **three** severity-to-colour maps, one per
 * notification function, disagreeing with each other: the same "warning" was
 * `#ff9800` in one and `#f59e0b` in the other two, and "info" was Material
 * `#2196f3` in one and Tailwind `#3b82f6` elsewhere. None of the three could
 * follow the theme, because a literal written in JavaScript cannot change when
 * `[data-theme]` does.
 *
 * Resolved through :func:`getCssVar` rather than restated, so these follow the
 * active theme. Anything drawing a notification surface should call this
 * instead of choosing colours: that is the whole point of it existing.
 */
export function getNotificationColors(kind: NotificationKind): NotificationColors {
  const tokens = _NOTIFICATION_TOKENS[kind] ?? _NOTIFICATION_TOKENS.info
  const fallbacks = _NOTIFICATION_FALLBACKS[kind] ?? _NOTIFICATION_FALLBACKS.info
  return {
    background: getCssVar(tokens[0], fallbacks[0]),
    border: getCssVar(tokens[1], fallbacks[1]),
    text: getCssVar(tokens[2], fallbacks[2]),
  }
}
