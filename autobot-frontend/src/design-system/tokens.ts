// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Canonical design-token catalog (#6938).
 *
 * Single source of truth for the *names* of design-system tokens used by
 * AutoBot. The catalog is consumed by:
 *
 *   - `src/stories/DesignTokens.stories.ts` — Storybook visual reference
 *   - any future runtime/lint code that needs to enumerate tokens
 *
 * The actual *values* (color hex / radius px / etc.) live in
 * `src/assets/tailwind.css` (`@theme` block) and Tailwind's default config.
 * This module deliberately does NOT duplicate those values — it lists which
 * names are blessed for the design system, in display order.
 *
 * If you add a new color/scale/utility to `tailwind.css` and want it in
 * the design-tokens story, register it here. If a name disappears from
 * `tailwind.css`, removing it here is the second half of that change.
 */

export type ClassPair = { readonly name: string; readonly cls: string }

/** Brand + status semantic colors backed by CSS variables in @theme. */
export const SEMANTIC_COLORS: readonly ClassPair[] = [
  { name: 'autobot-primary', cls: 'bg-autobot-primary text-white' },
  { name: 'autobot-secondary', cls: 'bg-autobot-secondary text-white' },
  { name: 'autobot-success', cls: 'bg-autobot-success text-black' },
  { name: 'autobot-warning', cls: 'bg-autobot-warning text-black' },
  { name: 'autobot-error', cls: 'bg-autobot-error-solid text-white' },
  { name: 'autobot-info', cls: 'bg-autobot-info-solid text-white' },
] as const

/** Surface backgrounds — layered card / panel / input shells. */
export const SURFACE_COLORS: readonly ClassPair[] = [
  { name: 'bg-primary', cls: 'bg-autobot-bg-primary' },
  { name: 'bg-secondary', cls: 'bg-autobot-bg-secondary' },
  { name: 'bg-tertiary', cls: 'bg-autobot-bg-tertiary' },
  { name: 'bg-elevated', cls: 'bg-autobot-bg-elevated' },
  { name: 'bg-card', cls: 'bg-autobot-bg-card' },
  { name: 'bg-input', cls: 'bg-autobot-bg-input' },
] as const

/** Electric (primary) palette steps — full 50–950 range. */
export const ELECTRIC_SCALE: readonly number[] = [
  50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950,
] as const

/** BlueGray supporting palette — 50–900 range (no 950 by design). */
export const BLUE_GRAY_SCALE: readonly number[] = [
  50, 100, 200, 300, 400, 500, 600, 700, 800, 900,
] as const

export type TypographyEntry = {
  readonly cls: string
  readonly label: string
  readonly sample: string
}

export const TYPOGRAPHY_SCALE: readonly TypographyEntry[] = [
  { cls: 'text-xs', label: 'text-xs', sample: 'The quick brown fox' },
  { cls: 'text-sm', label: 'text-sm', sample: 'The quick brown fox' },
  { cls: 'text-base', label: 'text-base', sample: 'The quick brown fox' },
  { cls: 'text-lg', label: 'text-lg', sample: 'The quick brown fox' },
  { cls: 'text-xl', label: 'text-xl', sample: 'The quick brown fox' },
  { cls: 'text-2xl', label: 'text-2xl', sample: 'The quick brown fox' },
  { cls: 'text-3xl', label: 'text-3xl', sample: 'The quick brown fox' },
  { cls: 'text-4xl', label: 'text-4xl', sample: 'The quick brown fox' },
] as const

export type LabelPair = { readonly cls: string; readonly label: string }

export const FONT_WEIGHTS: readonly LabelPair[] = [
  { cls: 'font-light', label: 'font-light' },
  { cls: 'font-normal', label: 'font-normal' },
  { cls: 'font-medium', label: 'font-medium' },
  { cls: 'font-semibold', label: 'font-semibold' },
  { cls: 'font-bold', label: 'font-bold' },
  { cls: 'font-extrabold', label: 'font-extrabold' },
] as const

export type SpacingEntry = {
  readonly cls: string
  readonly label: string
  readonly size: string
}

export const SPACING_SCALE: readonly SpacingEntry[] = [
  { cls: 'p-1', label: 'p-1', size: '0.25rem' },
  { cls: 'p-2', label: 'p-2', size: '0.5rem' },
  { cls: 'p-3', label: 'p-3', size: '0.75rem' },
  { cls: 'p-4', label: 'p-4', size: '1rem' },
  { cls: 'p-6', label: 'p-6', size: '1.5rem' },
  { cls: 'p-8', label: 'p-8', size: '2rem' },
] as const

export const RADII: readonly LabelPair[] = [
  { cls: 'rounded-none', label: 'rounded-none' },
  { cls: 'rounded-sm', label: 'rounded-sm' },
  { cls: 'rounded', label: 'rounded' },
  { cls: 'rounded-md', label: 'rounded-md' },
  { cls: 'rounded-lg', label: 'rounded-lg' },
  { cls: 'rounded-xl', label: 'rounded-xl' },
  { cls: 'rounded-full', label: 'rounded-full' },
] as const

export const SHADOWS: readonly LabelPair[] = [
  { cls: 'shadow-sm', label: 'shadow-sm' },
  { cls: 'shadow', label: 'shadow' },
  { cls: 'shadow-md', label: 'shadow-md' },
  { cls: 'shadow-lg', label: 'shadow-lg' },
  { cls: 'shadow-xl', label: 'shadow-xl' },
  { cls: 'shadow-2xl', label: 'shadow-2xl' },
] as const

/** Canvas cell ownership tokens (MVA-360). */
export const CANVAS_TOKENS: readonly ClassPair[] = [
  { name: 'agent-draft-border', cls: 'border-[var(--color-agent-draft-border)]' },
  { name: 'agent-draft-bg', cls: 'bg-[var(--color-agent-draft-bg)]' },
  { name: 'user-edit-cursor', cls: 'text-[var(--color-user-edit-cursor)]' },
]

/**
 * Refined UI colour tokens (#18223): CSS custom properties declared per theme
 * (light in css/design-tokens.css; dark, contrast, mono in css/themes/). The
 * existing --bg-*, --text-*, --border-* names derive from these through
 * css/themes/refined-map.css. Names only; see
 * docs/design/REFINED_TOKEN_MAPPING.md for the name-by-name mapping.
 */
export const REFINED_COLOR_TOKENS: readonly string[] = [
  // Surfaces and borders
  '--bg', '--surface', '--surface2', '--border', '--line', '--bw',
  // Text and links
  '--text', '--text2', '--muted', '--link', '--link-h',
  // Brand, accent and focus
  '--primary', '--primary-h', '--on-primary', '--accent', '--focus', '--brand-bg', '--brand-fg', '--nav-on-bw',
  // Illustration
  '--tile', '--tile-b', '--stroke', '--i1', '--i2', '--i3', '--i1t', '--i2t', '--i3t',
  // Bars and alert text
  '--bar', '--bar-alert', '--bar-track', '--alert-text',
  // Status pills
  '--ok-bg', '--ok-fg', '--warn-bg', '--warn-fg', '--bad-bg', '--bad-fg', '--idle-bg', '--idle-fg', '--info-bg', '--info-fg', '--pill-b',
  // Status dots
  '--dot-ok', '--dot-idle', '--dot-warn', '--dot-bad',
  // Danger tile
  '--danger-tile', '--danger-tile-b',
] as const

/** Refined UI theme-independent size tokens (grid, table, form, tooltip). */
export const REFINED_SIZE_TOKENS: readonly string[] = [
  '--bp-sm', '--bp-md', '--bp-lg', '--bp-xl', '--bp-2xl', '--grid-cols', '--grid-gutter',
  '--page-margin', '--topbar-h', '--subnav-w', '--subnav-rail', '--panel-w', '--content-max',
  '--reading-max', '--space-section', '--stack', '--widget-s', '--widget-m', '--widget-l',
  '--widget-full', '--kpi-span', '--tbl-font-size', '--tbl-row-h', '--tbl-cell-px',
  '--tbl-cell-py', '--tbl-head-h', '--tbl-head-bg', '--tbl-head-fg', '--tbl-head-font',
  '--tbl-head-case', '--tbl-head-ls', '--tbl-head-border', '--tbl-border', '--tbl-row-hover',
  '--tbl-row-selected', '--tbl-selected-edge', '--tbl-zebra', '--tbl-zebra-bg',
  '--tbl-check-col-w', '--tbl-actions-col-w', '--tbl-min-col', '--tbl-cell-max', '--tbl-num',
  '--tbl-sticky-top', '--field-h-sm', '--field-h-md', '--field-h-lg', '--field-px',
  '--field-radius', '--field-font-size', '--field-border', '--field-border-hover', '--field-bg',
  '--field-bg-disabled', '--field-fg', '--field-focus-ring', '--field-focus-offset',
  '--label-size', '--label-weight', '--label-gap', '--help-size', '--help-fg', '--error-fg',
  '--error-border', '--error-bw', '--field-gap', '--inline-gap', '--form-section-gap',
  '--form-label-col', '--form-max', '--action-gap', '--check-gap', '--control-size',
  '--switch-w', '--switch-h', '--switch-knob', '--tooltip-delay', '--tooltip-hide-delay',
  '--tooltip-offset', '--tooltip-max',
] as const

/** Built-in themes, as the `data-theme` attribute values useTheme.ts applies. */
export const BUILTIN_THEMES: readonly string[] = ['light', 'dark', 'contrast', 'mono'] as const
