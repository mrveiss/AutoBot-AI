// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #13617: the dashboard crashed on load for any company with a budget row.
// `/api/llc/cost-events` sent ts/cost_usd/tokens_in/tokens_out while the view
// read created_at/cost/input_tokens/output_tokens, so every field was
// undefined and `ev.created_at.slice(0, 10)` threw inside a computed that the
// template renders unconditionally — taking the whole page down.
//
// These tests feed the payload the endpoint ACTUALLY returns rather than a
// hand-written ideal one. A fixture shaped like the interface would have
// passed against the broken backend, which is exactly how this shipped.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const get = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get, post: vi.fn(), put: vi.fn(), delete: vi.fn() }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { companyId: 'c1' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

import CostDashboard from '../CostDashboard.vue'

/** One agent's budget row, exactly as `list_cost_events` now emits it. */
const SUMMARY_ROW = {
  id: '6f1a0f9a-0000-4000-8000-000000000001',
  agent_id: 'agent-a',
  work_item_id: null,
  model: null,
  provider: null,
  input_tokens: null,
  output_tokens: null,
  tokens_spent: 4321,
  cost: 1.25,
  created_at: null,
  source: 'budget_summary',
}

const BUDGET_ROW = {
  agent_id: 'agent-a',
  budget_mode: 'dollars',
  budget_limit: '100.00',
  budget_spent: '1.25',
  token_limit: null,
  tokens_spent: 4321,
  alert_threshold: 0.8,
}

function respond(events: unknown[]): void {
  get.mockImplementation((url: string) => {
    if (url.includes('/cost-events')) return Promise.resolve(events)
    if (url.includes('/budget')) return Promise.resolve([BUDGET_ROW])
    return Promise.resolve([])
  })
}

async function mountDashboard() {
  const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
  const wrapper = mount(CostDashboard, {
    global: { plugins: [i18n], stubs: { BaseModal: true, BaseButton: true, Icon: true } },
  })
  await flushPromises()
  return wrapper
}

describe('CostDashboard against the real cost-events payload (#13617)', () => {
  beforeEach(() => {
    get.mockReset()
  })

  it('renders a budget-summary row without throwing', async () => {
    respond([SUMMARY_ROW])
    const wrapper = await mountDashboard()

    // The crash took the whole view down, so a rendered table is the assertion.
    expect(wrapper.find('.cost-table').exists()).toBe(true)
    expect(wrapper.text()).toContain('agent-a')
  })

  it('states that spend is undated instead of drawing an empty 30-day chart', async () => {
    respond([SUMMARY_ROW])
    const wrapper = await mountDashboard()

    expect(wrapper.find('[data-testid="cost-no-dated-events"]').exists()).toBe(true)
    // The bar chart previously rendered thirty zero-height bars, which reads as
    // "no spend for thirty days" — a claim the data does not support.
    expect(wrapper.find('[data-testid="cost-bar-chart"]').exists()).toBe(false)
  })

  it('hides the date filters when nothing is dated', async () => {
    respond([SUMMARY_ROW])
    const wrapper = await mountDashboard()

    expect(wrapper.find('[data-testid="cost-date-from"]').exists()).toBe(false)
    // Positive companion: the agent filter is still there, so their absence is
    // the gate working rather than the filter bar failing to render.
    expect(wrapper.find('.filter-select').exists()).toBe(true)
  })

  it('sums cost rather than producing NaN', async () => {
    respond([SUMMARY_ROW, { ...SUMMARY_ROW, id: 'x2', agent_id: 'agent-b', cost: 2.5 }])
    const wrapper = await mountDashboard()

    // 1.25 + 2.50 — the old code read `ev.cost` off a payload that only had
    // `cost_usd`, so every total was NaN and rendered as "$NaN".
    expect(wrapper.text()).toContain('3.75')
    expect(wrapper.text()).not.toContain('NaN')
  })

  it('survives a mix of dated and undated rows', async () => {
    // The case that keeps the per-row guard honest. With nothing dated the
    // chart is gated off and `dailyBars` never runs, so the guard inside it is
    // unreachable; a mixed payload -- which is what a real cost-event store
    // alongside legacy budget summaries produces -- opens the gate AND feeds
    // the loop an undated row. Without the guard this is the original crash.
    const today = new Date().toISOString().slice(0, 10)
    respond([SUMMARY_ROW, { ...SUMMARY_ROW, id: 'x3', created_at: `${today}T09:00:00Z`, cost: 2 }])
    const wrapper = await mountDashboard()

    expect(wrapper.find('[data-testid="cost-bar-chart"]').exists()).toBe(true)
    expect(wrapper.find('.cost-table').exists()).toBe(true)
    // Both rows still counted in the company total: 1.25 + 2.00
    expect(wrapper.text()).toContain('3.25')
  })

  it('degrades an old-shaped payload to zero rather than NaN', async () => {
    // During a rolling update the frontend can be new while the backend still
    // serves the pre-#13617 shape: `cost_usd` as a string, no `cost` at all.
    // That must render a zero, not "$NaN" across every total on the page.
    respond([
      {
        agent_id: 'agent-a',
        event_type: 'budget_summary',
        tokens_in: 0,
        tokens_out: 0,
        cost_usd: '1.250000',
        model: 'unknown',
        ts: null,
      },
    ])
    const wrapper = await mountDashboard()

    expect(wrapper.find('.cost-table').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('NaN')
  })

  it('exports a CSV of undated rows without throwing', async () => {
    // The export button read `ev.cost.toFixed(6)` and `String(ev.input_tokens)`
    // straight off the payload, so it threw on exactly the rows that crashed
    // the page. Nothing in the view guarded it.
    // Two rows: the new shape with nulls, and an old-shaped row with no
    // `cost` at all. The second is what a backend that has not been updated
    // yet still serves, and it is the one `ev.cost.toFixed(6)` threw on.
    respond([
      SUMMARY_ROW,
      { agent_id: 'agent-old', cost_usd: '2.500000', model: 'unknown', ts: null },
    ])
    const createObjectURL = vi.fn(() => 'blob:stub')
    const revokeObjectURL = vi.fn()
    Object.assign(URL, { createObjectURL, revokeObjectURL })
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined)
    try {
      const wrapper = await mountDashboard()
      await wrapper.find('.btn-export').trigger('click')

      expect(createObjectURL).toHaveBeenCalledTimes(1)
      const blob = createObjectURL.mock.calls[0][0] as unknown as Blob
      const text = await blob.text()
      // The row is present, and the fields with no source are empty cells
      // rather than the string "undefined".
      expect(text).toContain('agent-a')
      expect(text).toContain('agent-old')
      expect(text).not.toContain('undefined')
      expect(text).toContain('1.250000')
      // The row with no cost at all exports a zero, not a crash or "NaN".
      expect(text).toContain('0.000000')
      expect(text).not.toContain('NaN')
    } finally {
      click.mockRestore()
    }
  })

  it('applies the date filters to dated rows', async () => {
    const rows = [
      { ...SUMMARY_ROW, id: 'jan', agent_id: 'agent-jan', created_at: '2026-01-15T09:00:00Z' },
      { ...SUMMARY_ROW, id: 'jun', agent_id: 'agent-jun', created_at: '2026-06-15T09:00:00Z' },
    ]
    respond(rows)
    const wrapper = await mountDashboard()
    // Both visible before filtering, so the assertion after it means the
    // filter acted rather than the table having been empty all along.
    expect(wrapper.text()).toContain('agent-jan')
    expect(wrapper.text()).toContain('agent-jun')

    await wrapper.find('[data-testid="cost-date-from"]').setValue('2026-06-01')
    await wrapper.find('[data-testid="cost-date-to"]').setValue('2026-06-30')
    await flushPromises()

    // Scoped to the table: both ids also appear in the agent dropdown and the
    // top-agent cards, which the date filter does not (and should not) touch.
    const table = wrapper.find('.cost-table').text()
    expect(table).toContain('agent-jun')
    expect(table).not.toContain('agent-jan')
  })

  it('ignores a malformed date instead of counting it as this month', async () => {
    // `new Date('nonsense')` is an Invalid Date, and every comparison against
    // it is false — so without the explicit check the row silently vanishes
    // from one total while still counting in another.
    respond([{ ...SUMMARY_ROW, created_at: 'not-a-date' }])
    const wrapper = await mountDashboard()

    expect(wrapper.find('.cost-table').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('NaN')
    expect(wrapper.text()).not.toContain('Invalid Date')
    // Excluded from the month total rather than counted at an arbitrary date.
    expect(wrapper.text()).toContain('$0.0000')
  })

  it('shows the daily chart when rows really are dated', async () => {
    // Proves the gate is driven by the data and not simply switched off: the
    // same view with dated rows must still draw the chart.
    const today = new Date().toISOString().slice(0, 10)
    respond([{ ...SUMMARY_ROW, created_at: `${today}T09:00:00Z`, source: 'cost_event' }])
    const wrapper = await mountDashboard()

    expect(wrapper.find('[data-testid="cost-bar-chart"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="cost-no-dated-events"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="cost-date-from"]').exists()).toBe(true)
  })
})
