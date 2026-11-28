// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #19938: the Workflow Planner panel — list states (loading, empty, not available, error) and
// the main path: list a plan, open it, measure a step, see the server's source on the pill.

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const post = vi.fn()
const put = vi.fn()
const patch = vi.fn()
const del = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get, post, put, patch, delete: del }),
}))

let routeQuery: Record<string, unknown> = {}
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: routeQuery, params: { companyId: 'co-1' } }),
  useRouter: () => ({ push: vi.fn() }),
}))

import WorkflowPlannerPanel from '../WorkflowPlannerPanel.vue'

const BASE = '/api/llc/company-os/workflow-plans'
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

const SUMMARY = { plan_key: 'quote', revision: 1, name: 'Quote the same day', status: 'draft', updated_at: 't' }

function plan(over: Record<string, unknown> = {}) {
  return {
    schema_version: '1',
    key: 'quote',
    revision: 1,
    name: 'Quote the same day',
    entry_point: 'org_chart',
    starts_at: 'Customer calls',
    ends_at: 'Invoice paid',
    status: 'draft',
    lanes: [{ key: 'lane-1', name: 'Owner', holder_kind: 'user', position: 0 }],
    steps: [{ key: 'step-1', lane_key: 'lane-1', label: 'Owner writes quote', position: 0 }],
    edges: [],
    handoffs: [],
    step_metrics: [],
    sub_steps: [],
    edge_cases: [],
    ...over,
  }
}

const GATE = { status: 'draft', next_status: 'measured', missing: [{ gate: 'G2', message: 'Measure every step', step: null }] }

function mountPanel() {
  return mount(WorkflowPlannerPanel, { global: { plugins: [i18n] } })
}

beforeEach(() => {
  vi.clearAllMocks()
  routeQuery = {}
})

describe('WorkflowPlannerPanel list states', () => {
  it('shows a loading status while the list is in flight', async () => {
    get.mockReturnValue(new Promise(() => {}))
    const w = mountPanel()
    expect(w.find('[data-testid="planner-loading"]').exists()).toBe(true)
  })

  it('shows the empty state when the company has no plans', async () => {
    get.mockResolvedValue([])
    const w = mountPanel()
    await flushPromises()
    expect(w.text()).toContain(en.llc.workflowPlanner.emptyTitle)
    expect(w.find('[data-testid="planner-unavailable"]').exists()).toBe(false)
  })

  it('shows an honest not-available state on a 404, not an error and not an empty list', async () => {
    get.mockRejectedValue(new Error('HTTP 404: Not Found'))
    const w = mountPanel()
    await flushPromises()
    expect(w.find('[data-testid="planner-unavailable"]').exists()).toBe(true)
    expect(w.text()).toContain(en.llc.workflowPlanner.unavailableTitle)
    expect(w.find('[data-testid="planner-error"]').exists()).toBe(false)
    expect(w.find('[data-testid="new-plan"]').exists()).toBe(false)
  })

  it('shows the error and a retry that reloads on a server failure', async () => {
    get.mockRejectedValueOnce(new Error('HTTP 500: boom')).mockResolvedValueOnce([SUMMARY])
    const w = mountPanel()
    await flushPromises()
    expect(w.find('[data-testid="planner-error"]').text()).toContain('HTTP 500: boom')
    await w.find('[data-testid="planner-retry"]').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Quote the same day')
  })
})

describe('WorkflowPlannerPanel main path', () => {
  it('lists plans with their translated status and opens one', async () => {
    get.mockImplementation((url: string) => {
      if (url === BASE) return Promise.resolve([SUMMARY])
      if (url === `${BASE}/quote`) return Promise.resolve(plan())
      if (url === `${BASE}/quote/gate`) return Promise.resolve(GATE)
      return Promise.reject(new Error(`unexpected ${url}`))
    })
    const w = mountPanel()
    await flushPromises()
    expect(w.text()).toContain(en.llc.workflowPlanner.status.draft)
    await w.find('[data-testid="open-quote"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="plan-detail"]').exists()).toBe(true)
    expect(w.find('[data-testid="gate-missing"]').text()).toContain('Measure every step')
  })

  it('creates a plan from the form with the entry point and opens it', async () => {
    get.mockImplementation((url: string) => {
      if (url === BASE) return Promise.resolve([])
      if (url === `${BASE}/new`) return Promise.resolve(plan({ key: 'new' }))
      if (url === `${BASE}/new/gate`) return Promise.resolve(GATE)
      return Promise.reject(new Error(`unexpected ${url}`))
    })
    post.mockResolvedValue(plan({ key: 'new' }))
    routeQuery = { entry_point: 'workflow_area' }
    const w = mountPanel()
    await flushPromises()
    await w.find('[data-testid="new-plan"]').trigger('click')
    const inputs = w.find('[data-testid="plan-form"]').findAll('input')
    await inputs[0].setValue('Quote it')
    await inputs[1].setValue('Customer calls')
    await inputs[2].setValue('Invoice paid')
    await w.find('[data-testid="plan-form"]').trigger('submit')
    await flushPromises()
    const body = post.mock.calls[0][1]
    expect(post.mock.calls[0][0]).toBe(BASE)
    expect(body).toMatchObject({ name: 'Quote it', entry_point: 'workflow_area', starts_at: 'Customer calls' })
    expect(body.key).toMatch(/^quote-it-/)
    expect(w.find('[data-testid="plan-detail"]').exists()).toBe(true)
  })

  it('measures a step and shows the source the server stored, not a checked mark for an estimate', async () => {
    const measured = plan({
      status: 'measured',
      step_metrics: [
        {
          step_key: 'step-1',
          frequency: { value: 8, unit: 'per_week', source: 'self_reported', recorded_at: 't' },
          duration: { value: 2, unit: 'days', source: 'self_reported', recorded_at: 't' },
          duration_definition: 'd',
          verified: false,
        },
      ],
    })
    get.mockImplementation((url: string) => {
      if (url === BASE) return Promise.resolve([SUMMARY])
      if (url === `${BASE}/quote`) return Promise.resolve(plan())
      return Promise.resolve(GATE)
    })
    put.mockResolvedValue(measured)
    const w = mountPanel()
    await flushPromises()
    await w.find('[data-testid="open-quote"]').trigger('click')
    await flushPromises()
    await w.find('[data-testid="step-measure"]').trigger('click')
    const row = w.find('[data-testid="measure-row-step-1"]')
    const inputs = row.findAll('input')
    await inputs[0].setValue('8')
    await inputs[1].setValue('2')
    await row.find('[data-testid="measure-save"]').trigger('click')
    await flushPromises()
    expect(put).toHaveBeenCalledWith(`${BASE}/quote/steps/step-1/metric`, {
      frequency: { value: 8, unit: 'per_week' },
      duration: { value: 2, unit: 'days' },
    })
    expect(w.find('[data-testid="source-pill-self_reported"]').text()).toBe(en.llc.workflowPlanner.source.self_reported)
    expect(w.find('[data-testid="source-pill-email"]').exists()).toBe(false)
  })

  it('shows an approved plan read-only in steps 1 to 4 and opens the create step', async () => {
    get.mockImplementation((url: string) => {
      if (url === BASE) return Promise.resolve([{ ...SUMMARY, status: 'approved' }])
      if (url === `${BASE}/quote`) return Promise.resolve(plan({ status: 'approved' }))
      return Promise.resolve({ ...GATE, status: 'approved', next_status: null, missing: [] })
    })
    const w = mountPanel()
    await flushPromises()
    await w.find('[data-testid="open-quote"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="status-read-only"]').exists()).toBe(true)
    expect(w.find('fieldset').attributes('disabled')).toBeDefined()
    expect(w.find('[data-testid="step-convert"]').attributes('disabled')).toBeUndefined()
    await w.find('[data-testid="step-convert"]').trigger('click')
    expect(w.find('[data-testid="convert-step"]').attributes('data-phase')).toBe('approved')
  })

  it('reports a failed write as an error and keeps the page', async () => {
    get.mockImplementation((url: string) => {
      if (url === BASE) return Promise.resolve([SUMMARY])
      if (url === `${BASE}/quote`) return Promise.resolve(plan())
      return Promise.resolve(GATE)
    })
    put.mockRejectedValue(new Error('HTTP 403: not allowed'))
    const w = mountPanel()
    await flushPromises()
    await w.find('[data-testid="open-quote"]').trigger('click')
    await flushPromises()
    await w.find('[data-testid="step-measure"]').trigger('click')
    const row = w.find('[data-testid="measure-row-step-1"]')
    const inputs = row.findAll('input')
    await inputs[0].setValue('8')
    await inputs[1].setValue('2')
    await row.find('[data-testid="measure-save"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="plan-detail"]').exists()).toBe(true)
    expect(w.find('[data-testid="measure-row-step-1"]').exists()).toBe(true)
  })
})
