// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Company OS dashboard layout (#18242). Pure data, no Vue.
 * The page shows one fixed set of widgets: the user moves and resizes them, never adds or
 * removes them. A stored layout is therefore fitted to that set on load: an unknown type is
 * dropped, and a widget added after the layout was saved is appended with its default size.
 */
import { i18nRef, type DashboardLayout, type DashboardWidget, type WidgetSpan } from './dashboardLayoutModel'

export const COMPANY_OS_DASHBOARD_ID = 'company-os'

export const COMPANY_WIDGET_TYPES = [
  'company-approvals',
  'company-budget',
  'company-agents',
  'company-runs',
  'company-activity',
] as const
export type CompanyWidgetType = (typeof COMPANY_WIDGET_TYPES)[number]

const SPEC: Record<CompanyWidgetType, { titleKey: string; span: WidgetSpan; height: number }> = {
  'company-approvals': { titleKey: 'llc.dashboard.pendingApprovals', span: 12, height: 240 },
  'company-budget': { titleKey: 'llc.dashboard.budget', span: 12, height: 240 },
  'company-agents': { titleKey: 'llc.dashboard.agents', span: 12, height: 320 },
  'company-runs': { titleKey: 'llc.dashboard.recentRuns', span: 6, height: 400 },
  'company-activity': { titleKey: 'llc.dashboard.liveActivity', span: 6, height: 400 },
}

/** A widget of this page: its type is one the page renders. */
export type CompanyWidget = DashboardWidget & { type: CompanyWidgetType }

const KNOWN_TYPES: ReadonlySet<string> = new Set(COMPANY_WIDGET_TYPES)
const isCompanyWidget = (w: DashboardWidget): w is CompanyWidget => KNOWN_TYPES.has(w.type)

function defaultWidget(type: CompanyWidgetType): CompanyWidget {
  const { titleKey, span, height } = SPEC[type]
  return { id: type, type, title: i18nRef(titleKey), span, height, props: {} }
}

export function defaultCompanyOsWidgets(): CompanyWidget[] {
  return COMPANY_WIDGET_TYPES.map(defaultWidget)
}

export function defaultCompanyOsLayout(): DashboardLayout {
  const now = Date.now()
  return {
    dashboards: [
      { id: COMPANY_OS_DASHBOARD_ID, name: i18nRef('llc.dashboard.title'), widgets: defaultCompanyOsWidgets(), createdAt: now, updatedAt: now },
    ],
    activeId: COMPANY_OS_DASHBOARD_ID,
  }
}

/** The stored widgets fitted to the page's set: known types once each, missing ones appended. */
export function companyWidgetsOf(layout: DashboardLayout): CompanyWidget[] {
  const stored = layout.dashboards[0]?.widgets ?? []
  const seen = new Set<string>()
  const kept = stored.filter(isCompanyWidget).filter((w) => !seen.has(w.type) && !!seen.add(w.type))
  const missing = COMPANY_WIDGET_TYPES.filter((type) => !seen.has(type)).map(defaultWidget)
  return [...kept, ...missing].map((w) => ({ ...w, props: { ...w.props } }))
}

/** The layout to save: the page's one dashboard carrying `widgets`. */
export function withCompanyWidgets(layout: DashboardLayout, widgets: DashboardWidget[]): DashboardLayout {
  const base = layout.dashboards[0] ?? defaultCompanyOsLayout().dashboards[0]
  return {
    dashboards: [{ ...base, widgets, updatedAt: Date.now() }],
    activeId: base.id,
  }
}
