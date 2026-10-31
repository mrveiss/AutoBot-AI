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
})
