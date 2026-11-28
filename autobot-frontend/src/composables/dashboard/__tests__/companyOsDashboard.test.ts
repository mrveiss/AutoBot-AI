// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// Company OS layout fitting (#18242): a stored layout always yields the page's widget set.

import { describe, expect, it } from 'vitest'
import {
  COMPANY_OS_DASHBOARD_ID,
  COMPANY_WIDGET_TYPES,
  companyWidgetsOf,
  defaultCompanyOsLayout,
  withCompanyWidgets,
} from '../companyOsDashboard'
import type { DashboardLayout, DashboardWidget } from '../dashboardLayoutModel'

function stored(widgets: DashboardWidget[]): DashboardLayout {
  return { dashboards: [{ id: COMPANY_OS_DASHBOARD_ID, name: 'x', widgets, createdAt: 0, updatedAt: 0 }], activeId: COMPANY_OS_DASHBOARD_ID }
}

const w = (type: string, span: DashboardWidget['span'] = 4): DashboardWidget => ({ id: type, type, title: '', span, height: 200, props: {} })

describe('companyOsDashboard', () => {
  it('defaults to every company widget once, in the declared order', () => {
    expect(companyWidgetsOf(defaultCompanyOsLayout()).map((x) => x.type)).toEqual([...COMPANY_WIDGET_TYPES])
  })

  it('keeps the stored order and sizes of known widgets', () => {
    const order = [...COMPANY_WIDGET_TYPES].reverse()
    const out = companyWidgetsOf(stored(order.map((t) => w(t, 4))))
    expect(out.map((x) => x.type)).toEqual(order)
    expect(out.every((x) => x.span === 4)).toBe(true)
  })

  it('drops unknown and repeated types, including prototype keys', () => {
    const out = companyWidgetsOf(stored([w('company-runs'), w('heatmap'), w('toString'), w('company-runs', 8)]))
    expect(out.filter((x) => x.type === 'company-runs')).toHaveLength(1)
    expect(out.find((x) => x.type === 'company-runs')?.span).toBe(4)
    expect(out.map((x) => x.type)).not.toContain('heatmap')
    expect(out.map((x) => x.type)).not.toContain('toString')
  })

  it('appends a widget missing from an older saved layout at its default size', () => {
    const out = companyWidgetsOf(stored([w('company-activity')]))
    expect(out[0].type).toBe('company-activity')
    expect(out).toHaveLength(COMPANY_WIDGET_TYPES.length)
    expect(out.find((x) => x.type === 'company-approvals')?.span).toBe(12)
  })

  it('saves one dashboard carrying the given widgets', () => {
    const widgets = [w('company-budget', 6)]
    const next = withCompanyWidgets(defaultCompanyOsLayout(), widgets)
    expect(next.dashboards).toHaveLength(1)
    expect(next.activeId).toBe(COMPANY_OS_DASHBOARD_ID)
    expect(next.dashboards[0].widgets).toEqual(widgets)
  })
})
