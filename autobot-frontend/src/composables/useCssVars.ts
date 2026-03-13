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
