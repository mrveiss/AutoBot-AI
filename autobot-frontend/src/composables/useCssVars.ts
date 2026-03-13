/**
 * Shared CSS variable accessor for JavaScript-side color/font values.
 * Issue #704: CSS-to-JS bridge used by charts, Cytoscape, D3, etc.
 * Issue #1602: Extracted from 23 component-local duplicates.
 *
 * @param name - CSS custom property name (e.g., '--chart-blue')
 * @param fallback - Default value for SSR/testing or missing property
 * @returns The resolved CSS variable value or fallback
 */
export function getCssVar(name: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}
