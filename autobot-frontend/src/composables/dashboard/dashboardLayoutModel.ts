// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Dashboard layout model and pure transforms (#18242). No Vue, no I/O, so it is unit-testable.
 * The server's shapes come from the generated contract (`@/types/generated/api`).
 */

import type { components } from '@/types/generated/api'

/**
 * Stored names and titles that are i18n keys carry this prefix, set only by the defaults and
 * the legacy mapper. Anything else is text the user typed and is shown as typed, even if it
 * happens to equal a key (#18896 review).
 */
export const I18N_PREFIX = 'i18n:'
export const i18nRef = (key: string): string => `${I18N_PREFIX}${key}`

/** A stored name or title for display: prefixed keys translate, user text stays verbatim. */
export function displayText(stored: string, t: (key: string) => string): string {
  return stored.startsWith(I18N_PREFIX) ? t(stored.slice(I18N_PREFIX.length)) : stored
}

export const GRID_COLUMNS = 12
export const WIDGET_SPANS = [4, 6, 8, 12] as const
export type WidgetSpan = (typeof WIDGET_SPANS)[number]
export const HEIGHT_MIN = 160
export const HEIGHT_MAX = 960
export const HEIGHT_STEP = 80

export interface DashboardWidget {
  id: string
  type: string
  title: string
  span: WidgetSpan
  height: number
  props: Record<string, unknown>
  refreshInterval?: number | null
}

export interface Dashboard {
  id: string
  name: string
  widgets: DashboardWidget[]
  createdAt: number
  updatedAt: number
}

export interface DashboardLayout {
  dashboards: Dashboard[]
  activeId: string | null
}

/** Old 3-column `width` (1..3) → 12-column span. */
export function spanFromLegacyWidth(width: number): WidgetSpan {
  if (width >= 3) return 12
  if (width === 2) return 8
  return 4
}

export function clampHeight(px: number): number {
  return Math.min(HEIGHT_MAX, Math.max(HEIGHT_MIN, Math.round(px)))
}

/** Next/previous allowed span; stays put at either end. */
export function stepSpan(span: WidgetSpan, dir: 1 | -1): WidgetSpan {
  const i = WIDGET_SPANS.indexOf(span) + dir
  return WIDGET_SPANS[Math.min(WIDGET_SPANS.length - 1, Math.max(0, i))]
}

/** Move the widget at `from` by `delta` slots, returning a new array. */
export function moveWidget<T>(widgets: T[], from: number, delta: number): T[] {
  const to = Math.min(widgets.length - 1, Math.max(0, from + delta))
  if (to === from) return widgets
  const next = [...widgets]
  const [w] = next.splice(from, 1)
  next.splice(to, 0, w)
  return next
}

interface LegacyWidget {
  id: string
  type: string
  title?: string
  width?: number
  height?: number
  props?: Record<string, unknown>
  refreshInterval?: unknown // an unvalidated <input type="number">: may be '', negative or fractional
  y?: number
  x?: number
}

interface LegacyDashboard {
  id: string
  name: string
  widgets?: LegacyWidget[]
  createdAt?: number
  updatedAt?: number
}

// The server's limits (schemas_users_dashboard_layouts.py), mirrored here once: the generated
// contract carries the shapes but not the bounds. Legacy localStorage data predates them, so the
// mapper fits it to them, and the view fits user input: one out-of-range value 422s every save.
export const MAX_TEXT = 120
export const MAX_DASHBOARDS = 16
export const MAX_WIDGETS = 48
export const REFRESH_INTERVAL_MAX = 86_400_000
const ID_RE = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/
const DEFAULT_NAME_KEY = i18nRef('views.customDashboard.myDashboard')

export const fitText = (s: unknown): string => String(s ?? '').trim().slice(0, MAX_TEXT)

/** A server-valid refresh interval: a whole number in 0..REFRESH_INTERVAL_MAX, or null when unset. */
export function fitRefreshInterval(v: unknown): number | null {
  if (typeof v !== 'number' || !Number.isFinite(v)) return null
  return Math.min(REFRESH_INTERVAL_MAX, Math.max(0, Math.round(v)))
}

/** A server-valid id: invalid characters become '-', and a fallback is used when nothing is left. */
export function fitId(raw: unknown, fallback: string): string {
  const s = String(raw ?? '').replace(/[^A-Za-z0-9_-]/g, '-').replace(/^[_-]+/, '').slice(0, 64)
  return ID_RE.test(s) ? s : fallback
}

/** Suffixes repeats so the ids in one list stay unique after fitId (a duplicate is a 422). */
function uniqueIds<T extends { id: string }>(items: T[]): T[] {
  const seen = new Set<string>()
  return items.map((item) => {
    let id = item.id
    for (let n = 2; seen.has(id); n++) id = `${item.id.slice(0, 60)}-${n}`
    seen.add(id)
    return id === item.id ? item : { ...item, id }
  })
}

function fromLegacyWidget(w: LegacyWidget, i: number): DashboardWidget {
  return {
    id: fitId(w.id, `widget-${i + 1}`),
    type: fitId(w.type, 'system'),
    title: fitText(w.title),
    span: spanFromLegacyWidth(w.width ?? 1),
    height: clampHeight(w.height ?? 320),
    props: w.props ?? {},
    refreshInterval: fitRefreshInterval(w.refreshInterval),
  }
}

/** Legacy localStorage dashboards → server layout, widgets ordered by (y, x). */
export function fromLegacyDashboards(raw: LegacyDashboard[]): DashboardLayout {
  const dashboards = uniqueIds(
    raw.slice(0, MAX_DASHBOARDS).map((d, i) => ({
      id: fitId(d.id, `dashboard-${i + 1}`),
      name: fitText(d.name) || DEFAULT_NAME_KEY,
      widgets: uniqueIds(
        [...(d.widgets ?? [])]
          .sort((a, b) => (a.y ?? 0) - (b.y ?? 0) || (a.x ?? 0) - (b.x ?? 0))
          .slice(0, MAX_WIDGETS)
          .map((w, i) => fromLegacyWidget(w, i)),
      ),
      createdAt: d.createdAt ?? 0,
      updatedAt: d.updatedAt ?? 0,
    })),
  )
  return { dashboards, activeId: dashboards[0]?.id ?? null }
}

/** The server's layout shape (generated contract); a few fields there are optional. */
export type StoredLayout = components['schemas']['DashboardLayout']

/** The generated contract's layout, with its optional fields given the model's defaults. */
export function fromStoredLayout(stored: StoredLayout): DashboardLayout {
  return {
    dashboards: (stored.dashboards ?? []).map((d) => ({
      ...d,
      widgets: (d.widgets ?? []).map((w) => ({ ...w, props: w.props ?? {} })),
    })),
    activeId: stored.activeId ?? null,
  }
}
