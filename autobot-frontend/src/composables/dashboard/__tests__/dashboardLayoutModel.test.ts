// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** Pure dashboard layout transforms (#18242). */
import { describe, it, expect } from 'vitest'
import {
  HEIGHT_MAX,
  HEIGHT_MIN,
  MAX_DASHBOARDS,
  MAX_WIDGETS,
  REFRESH_INTERVAL_MAX,
  clampHeight,
  fitRefreshInterval,
  displayText,
  i18nRef,
  fitId,
  fromLegacyDashboards,
  moveWidget,
  spanFromLegacyWidth,
  stepSpan,
  fromStoredLayout,
  type DashboardWidget,
} from '../dashboardLayoutModel'

const w = (id: string): DashboardWidget => ({ id, type: 'system', title: id, span: 6, height: 320, props: {} })

describe('dashboardLayoutModel', () => {
  it.each([
    [1, 4],
    [2, 8],
    [3, 12],
    [0, 4],
    [9, 12],
  ])('maps a legacy 3-column width %i to span %i', (width, span) => {
    expect(spanFromLegacyWidth(width)).toBe(span)
  })

  it('steps the span through 4/6/8/12 and stops at either end', () => {
    expect(stepSpan(4, 1)).toBe(6)
    expect(stepSpan(8, 1)).toBe(12)
    expect(stepSpan(12, 1)).toBe(12)
    expect(stepSpan(4, -1)).toBe(4)
  })

  it('clamps the height into its bounds', () => {
    expect(clampHeight(10)).toBe(HEIGHT_MIN)
    expect(clampHeight(5000)).toBe(HEIGHT_MAX)
    expect(clampHeight(333.4)).toBe(333)
  })

  it('moves a widget without mutating the input, and clamps at the ends', () => {
    const list = [w('a'), w('b'), w('c')]
    expect(moveWidget(list, 0, 1).map((x) => x.id)).toEqual(['b', 'a', 'c'])
    expect(moveWidget(list, 2, 5).map((x) => x.id)).toEqual(['a', 'b', 'c'])
    expect(moveWidget(list, 2, -5).map((x) => x.id)).toEqual(['c', 'a', 'b'])
    expect(list.map((x) => x.id)).toEqual(['a', 'b', 'c'])
  })

  it('converts legacy localStorage dashboards, ordering widgets by row then column', () => {
    const layout = fromLegacyDashboards([
      {
        id: 'default',
        name: 'Main',
        widgets: [
          { id: 'w3', type: 'agents', y: 1, x: 0, width: 2, height: 400, props: { height: 400 } },
          { id: 'w2', type: 'heatmap', y: 0, x: 1, width: 2, height: 300 },
          { id: 'w1', type: 'system', y: 0, x: 0, width: 1, height: 50 },
        ],
      },
    ])
    const widgets = layout.dashboards[0].widgets
    expect(widgets.map((x) => x.id)).toEqual(['w1', 'w2', 'w3'])
    expect(widgets.map((x) => x.span)).toEqual([4, 8, 8])
    expect(widgets[0].height).toBe(HEIGHT_MIN)
    expect(widgets[2].props).toEqual({ height: 400 })
    expect(layout.activeId).toBe('default')
  })

  it('fills the contract\'s optional fields with the model defaults', () => {
    // fails if a stored layout without widgets, props or activeId breaks the model's invariants
    const layout = fromStoredLayout({
      dashboards: [
        { id: 'a', name: 'A', createdAt: 1, updatedAt: 1 },
        { id: 'b', name: 'B', createdAt: 1, updatedAt: 1, widgets: [{ id: 'w', type: 'system', title: '', span: 6, height: 320 }] },
      ],
    })
    expect(layout.activeId).toBeNull()
    expect(layout.dashboards[0].widgets).toEqual([])
    expect(layout.dashboards[1].widgets[0].props).toEqual({})
  })

  it('reads an empty stored layout as no dashboards', () => {
    expect(fromStoredLayout({}).dashboards).toEqual([])
  })

  it('fits legacy names, titles and ids to the server limits so a load never 422s', () => {
    const long = 'x'.repeat(200)
    const layout = fromLegacyDashboards([
      { id: 'my dash!', name: '   ', widgets: [{ id: 'a b', type: 'system', title: long }, { id: 'a-b', type: 'system' }] },
      { id: 'my dash!', name: long, widgets: [] },
    ])
    const [first, second] = layout.dashboards
    expect(first.name).toBe('i18n:views.customDashboard.myDashboard')
    expect(second.name).toHaveLength(120)
    expect(first.widgets[0].title).toHaveLength(120)
    expect(first.widgets.map((w) => w.id)).toEqual(['a-b', 'a-b-2'])
    expect([first.id, second.id]).toEqual(['my-dash-', 'my-dash--2'])
  })

  it('fits legacy dashboard and widget counts to the server maxima', () => {
    // fails if a legacy store with too many dashboards or widgets is migrated whole (a 422 on every save)
    const many = (n: number, p: string) => Array.from({ length: n }, (_, i) => ({ id: `${p}${i}`, type: 'system', name: p }))
    const over = fromLegacyDashboards([{ id: 'd', name: 'D', widgets: many(MAX_WIDGETS + 3, 'w') }, ...many(MAX_DASHBOARDS + 2, 'x')])
    expect(over.dashboards).toHaveLength(MAX_DASHBOARDS)
    expect(over.dashboards[0].widgets).toHaveLength(MAX_WIDGETS)
    // Contrast: a store within the limits keeps every dashboard and widget.
    const within = fromLegacyDashboards([{ id: 'd', name: 'D', widgets: many(3, 'w') }, ...many(2, 'x')])
    expect(within.dashboards).toHaveLength(3)
    expect(within.dashboards[0].widgets).toHaveLength(3)
  })

  it.each([
    [-5, 0],
    [1500.6, 1501],
    [REFRESH_INTERVAL_MAX * 2, REFRESH_INTERVAL_MAX],
    ['', null],
    [Number.NaN, null],
    [undefined, null],
    [30000, 30000],
  ])('fits a refresh interval %s to %s', (raw, fitted) => {
    // fails if a negative, fractional, oversized or blank interval reaches the server's int 0..max field
    expect(fitRefreshInterval(raw)).toBe(fitted)
    expect(fromLegacyDashboards([{ id: 'd', name: 'D', widgets: [{ id: 'w', type: 'system', refreshInterval: raw }] }])
      .dashboards[0].widgets[0].refreshInterval).toBe(fitted)
  })

  it('fitId keeps a valid id and falls back when nothing usable is left', () => {
    expect(fitId('widget_1', 'f')).toBe('widget_1')
    expect(fitId('***', 'f')).toBe('f')
    expect(fitId(undefined, 'f')).toBe('f')
  })

  it('translates only prefixed keys; user text that equals a key is shown as typed', () => {
    // fails if a user's own dashboard name gets translated because it matches a key
    const t = (key: string) => `T(${key})`
    expect(displayText(i18nRef('views.customDashboard.mainDashboard'), t)).toBe('T(views.customDashboard.mainDashboard)')
    expect(displayText('views.customDashboard.mainDashboard', t)).toBe('views.customDashboard.mainDashboard')
    expect(displayText('My board', t)).toBe('My board')
  })
})
