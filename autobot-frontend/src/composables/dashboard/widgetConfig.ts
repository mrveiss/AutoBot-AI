// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The widget config form's draft and its write-back (#18242 review). Pure, no Vue.
 * `widget.height` is the one height: the grid resizes it, and a visualisation that takes a
 * `height` prop renders with it, so the card and its chart never disagree.
 */
import { clampHeight, fitRefreshInterval, fitText, type DashboardWidget } from './dashboardLayoutModel'
import { WIDGET_DEFINITIONS } from './defaultDashboards'

const HEIGHT_PROP_TYPES = new Set(WIDGET_DEFINITIONS.filter((d) => 'height' in d.defaultProps).map((d) => d.type))

/** Whether this widget kind's visualisation takes a `height` prop. */
export const hasHeightProp = (type: string): boolean => HEIGHT_PROP_TYPES.has(type)

/** The props a widget renders with: its grid height overrides any stored `props.height`. */
export function renderProps(w: DashboardWidget): Record<string, unknown> {
  return hasHeightProp(w.type) ? { ...w.props, height: w.height } : w.props
}

/** The form's copy: the title as the reader sees it, never a raw `i18n:` key. */
export function configDraft<T extends DashboardWidget>(w: T, tr: (stored: string) => string): T {
  return { ...w, title: tr(w.title), props: { ...w.props } }
}

/** The edited copy fit to the server limits; a title left as displayed keeps its i18n key. */
export function applyConfig<T extends DashboardWidget>(original: T, draft: T, tr: (stored: string) => string): T {
  const title = draft.title === tr(original.title) ? original.title : fitText(draft.title)
  const height = clampHeight(Number.isFinite(draft.height) ? draft.height : original.height)
  const props = hasHeightProp(draft.type) ? { ...draft.props, height } : draft.props
  return { ...draft, title, height, props, refreshInterval: fitRefreshInterval(draft.refreshInterval) }
}
