// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** The widget config form's draft and write-back (#18242 review). */
import { describe, it, expect } from 'vitest'
import { HEIGHT_MAX, MAX_TEXT, displayText, i18nRef, type DashboardWidget } from '../dashboardLayoutModel'
import { applyConfig, configDraft, hasHeightProp, renderProps } from '../widgetConfig'

const tr = (s: string) => displayText(s, (key) => `T(${key})`)
const KEY = i18nRef('views.customDashboard.widgetAgents')
const agents = (over: Partial<DashboardWidget> = {}): DashboardWidget => ({
  id: 'w', type: 'agents', title: KEY, span: 8, height: 400, props: { height: 400 }, ...over,
})

describe('widgetConfig', () => {
  it('renders a height-prop widget at its grid height, whatever props.height says', () => {
    // fails if the grid resizes the card but the chart keeps its stored props.height
    expect(renderProps(agents({ height: 560 })).height).toBe(560)
    // Contrast: a kind without a height prop renders its props untouched.
    expect(hasHeightProp('system')).toBe(false)
    expect(renderProps(agents({ type: 'system', props: { a: 1 } }))).toEqual({ a: 1 })
  })

  it('shows the translated title in the form, never the raw i18n key', () => {
    // fails if the title field shows "i18n:views.customDashboard.widgetAgents"
    expect(configDraft(agents(), tr).title).toBe('T(views.customDashboard.widgetAgents)')
    expect(configDraft(agents({ title: 'Mine' }), tr).title).toBe('Mine')
  })

  it('keeps the i18n key when the displayed title is saved unchanged, and stores an edit as typed', () => {
    const original = agents()
    expect(applyConfig(original, configDraft(original, tr), tr).title).toBe(KEY)
    // Contrast: an edited title replaces the key, fit to the server limit.
    const edited = { ...configDraft(original, tr), title: 'x'.repeat(MAX_TEXT + 30) }
    expect(applyConfig(original, edited, tr).title).toHaveLength(MAX_TEXT)
  })

  it('writes one height back: clamped, and mirrored into props.height', () => {
    // fails if the form height and props.height disagree after a save, or leave the server range
    const saved = applyConfig(agents(), { ...configDraft(agents(), tr), height: HEIGHT_MAX + 500 }, tr)
    expect([saved.height, saved.props.height]).toEqual([HEIGHT_MAX, HEIGHT_MAX])
  })

  it('a cleared refresh interval saves as null, not the blank string', () => {
    // fails if v-model.number's '' reaches the server's int | None field
    const blank = { ...configDraft(agents(), tr), refreshInterval: '' as unknown as number }
    expect(applyConfig(agents(), blank, tr).refreshInterval).toBeNull()
    expect(applyConfig(agents(), { ...blank, refreshInterval: 5000 }, tr).refreshInterval).toBe(5000)
  })
})
