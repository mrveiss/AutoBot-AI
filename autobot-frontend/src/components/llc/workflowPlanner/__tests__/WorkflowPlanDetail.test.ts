// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #19938: a plan re-read that fails after a convert-step action must say so, keep a retry, and
// not present the plan on screen as current.

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const post = vi.fn()
vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get, post, put: vi.fn(), patch: vi.fn(), delete: vi.fn() }),
}))
vi.mock('@/composables/useConfirmDialog', () => ({ useConfirmDialog: () => ({ confirm: vi.fn() }) }))
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {}, params: { companyId: 'co-1' } }),
  useRouter: () => ({ push: vi.fn() }),
}))

import WorkflowPlanDetail from '../WorkflowPlanDetail.vue'
import { useWorkflowPlans } from '@/composables/llc/useWorkflowPlans'

const BASE = '/api/llc/company-os/workflow-plans/quote'
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const PLAN = {
  key: 'quote',
  revision: 1,
  name: 'Quote the same day',
  status: 'labeled',
  lanes: [{ key: 'lane-1', name: 'Owner', holder_kind: 'user', position: 0 }],
  steps: [],
  edges: [],
  handoffs: [],
  step_metrics: [],
  sub_steps: [],
  edge_cases: [],
  conversion: null,
}
const GATE = { status: 'labeled', next_status: 'approved', missing: [] }

async function openConvert() {
  get.mockImplementation((url: string) => Promise.resolve(url === `${BASE}/gate` ? GATE : PLAN))
  const w = mount(WorkflowPlanDetail, { props: { planKey: 'quote', api: useWorkflowPlans() }, global: { plugins: [i18n] } })
  await flushPromises()
  await w.find('[data-testid="step-convert"]').trigger('click')
  return w
}

beforeEach(() => vi.clearAllMocks())

describe('WorkflowPlanDetail failed re-read', () => {
  it('marks the plan stale with a retry when the re-read after an action fails', async () => {
    const w = await openConvert()
    expect(w.find('[data-testid="plan-stale"]').exists()).toBe(false)
    post.mockRejectedValue(new Error('HTTP 500: boom'))
    get.mockRejectedValue(new Error('HTTP 503: down'))
    await w.find('[data-testid="convert-preview"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="plan-stale"]').text()).toContain('HTTP 503: down')
    expect(w.find('[data-testid="convert-preview"]').attributes('disabled')).toBeDefined()

    get.mockImplementation((url: string) => Promise.resolve(url === `${BASE}/gate` ? GATE : { ...PLAN, revision: 2 }))
    await w.find('[data-testid="plan-reread"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="plan-stale"]').exists()).toBe(false)
    expect(w.find('[data-testid="convert-preview"]').attributes('disabled')).toBeUndefined()
  })

  async function previewWith(fail: { plan?: boolean; gate?: boolean }) {
    const w = await openConvert()
    post.mockRejectedValue(new Error('HTTP 409: gate open'))
    get.mockImplementation((url: string) => {
      const isGate = url === `${BASE}/gate`
      if (isGate ? fail.gate : fail.plan) return Promise.reject(new Error(isGate ? 'HTTP 503: gate down' : 'HTTP 502: plan down'))
      return Promise.resolve(isGate ? GATE : PLAN)
    })
    await w.find('[data-testid="convert-preview"]').trigger('click')
    await flushPromises()
    return w
  }

  it('after a good load, a failed gate re-read is flagged stale and names the gate only', async () => {
    const w = await previewWith({ gate: true })
    const alert = w.find('[data-testid="plan-stale"]')
    expect(alert.text()).toContain('readiness checks could not be refreshed')
    expect(alert.text()).not.toContain('This plan could not be refreshed')
    expect(w.find('[data-testid="convert-preview"]').attributes('disabled')).toBeDefined()
  })

  it('after a good load, a failed plan re-read is flagged stale and names the plan only', async () => {
    const w = await previewWith({ plan: true })
    const alert = w.find('[data-testid="plan-stale"]')
    expect(alert.text()).toContain('This plan could not be refreshed')
    expect(alert.text()).toContain('HTTP 502: plan down')
    expect(w.find('[data-testid="convert-preview"]').attributes('disabled')).toBeDefined()
  })

  it('says both when the plan and the gate re-reads both fail', async () => {
    const w = await previewWith({ plan: true, gate: true })
    expect(w.find('[data-testid="plan-stale"]').text()).toContain('Neither the plan nor its readiness checks')
  })

  it('a failed gate re-read after a successful action is stale, not a failed save', async () => {
    const w = await openConvert()
    post.mockResolvedValue({ ...PLAN, revision: 2, conversion: { status: 'preview', contract_errors: [], preview_errors: [] } })
    get.mockImplementation((url: string) => (url === `${BASE}/gate` ? Promise.reject(new Error('HTTP 503: gate down')) : Promise.resolve(PLAN)))
    await w.find('[data-testid="convert-preview"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="plan-stale"]').text()).toContain('readiness checks could not be refreshed')
  })
})
