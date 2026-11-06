// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #20086: every plan-edit route has a UI action that calls it through the generated client.
// Each test names the method, the path and the body the action must send.

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const post = vi.fn()
const patch = vi.fn()
const del = vi.fn()
const confirmFn = vi.fn()
vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get, post, put: vi.fn(), patch, delete: del }),
}))
vi.mock('@/composables/useConfirmDialog', () => ({ useConfirmDialog: () => ({ confirm: confirmFn }) }))
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {}, params: { companyId: 'co-1' } }),
  useRouter: () => ({ push: vi.fn() }),
}))

import WorkflowPlanDetail from '../WorkflowPlanDetail.vue'
import { useWorkflowPlans } from '@/composables/llc/useWorkflowPlans'

const BASE = '/api/llc/company-os/workflow-plans/quote'
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const metric = (step_key: string, freq: number, dur: number) => ({
  step_key,
  frequency: { value: freq, unit: 'per_week', source: 'self_reported' },
  duration: { value: dur, unit: 'hours', source: 'self_reported' },
})
const PLAN = {
  key: 'quote',
  revision: 1,
  name: 'Quote the same day',
  status: 'labeled',
  lanes: [{ key: 'lane-1', name: 'Owner', holder_kind: 'user', position: 0 }],
  steps: [
    { key: 'step-1', lane_key: 'lane-1', label: 'Ask', position: 0 },
    { key: 'step-2', lane_key: 'lane-1', label: 'Quote', position: 1 },
  ],
  edges: [{ from_step: 'step-1', to_step: 'step-2', condition: null }],
  handoffs: [],
  step_metrics: [metric('step-1', 5, 1), metric('step-2', 2, 4)],
  sub_steps: [],
  edge_cases: [{ key: 'edge-1', step_key: 'step-2', description: 'Customer cancels', classification: 'ai' }],
  one_number: { step_key: 'step-2', title: 'T', return_kind: 'more_yeses', target_value: null },
  conversion: null,
}
const GATE = { status: 'labeled', next_status: 'approved', missing: [] }

async function open(tab: string): Promise<VueWrapper> {
  get.mockImplementation((url: string) => Promise.resolve(url === `${BASE}/gate` ? GATE : PLAN))
  for (const verb of [post, patch, del]) verb.mockResolvedValue(PLAN)
  const w = mount(WorkflowPlanDetail, { props: { planKey: 'quote', api: useWorkflowPlans() }, global: { plugins: [i18n] } })
  await flushPromises()
  await w.find(`[data-testid="step-${tab}"]`).trigger('click')
  return w
}

const settle = () => flushPromises()

beforeEach(() => {
  vi.clearAllMocks()
  confirmFn.mockResolvedValue(true)
})

describe('map step edits one lane, step or edge at a time', () => {
  it('POST /lanes adds a lane', async () => {
    const w = await open('map')
    // the first input without a test id is the "Lane name" field of the add row
    await w.findAll('input').find((i) => !i.attributes('data-testid'))!.setValue('Sales')
    await w.find('[data-testid="add-lane"]').trigger('click')
    await settle()
    expect(post).toHaveBeenCalledWith(`${BASE}/lanes`, { key: 'lane-2', name: 'Sales', holder_kind: 'user', position: 1 })
  })

  it('PATCH /lanes/{lane_key} renames a lane', async () => {
    const w = await open('map')
    const input = w.find('[data-testid="rename-lane-lane-1"]')
    await input.setValue('Founder')
    await input.trigger('change')
    await settle()
    expect(patch).toHaveBeenCalledWith(`${BASE}/lanes/lane-1`, { name: 'Founder' })
  })

  it('DELETE /lanes/{lane_key} deletes a lane once confirmed, and not when declined', async () => {
    const w = await open('map')
    confirmFn.mockResolvedValueOnce(false)
    await w.find('[data-testid="delete-lane-lane-1"]').trigger('click')
    await settle()
    expect(del).not.toHaveBeenCalled()
    await w.find('[data-testid="delete-lane-lane-1"]').trigger('click')
    await settle()
    expect(del).toHaveBeenCalledWith(`${BASE}/lanes/lane-1`)
  })

  it('POST /steps adds a step that is connected to nothing', async () => {
    const w = await open('map')
    const fields = w.findAll('input').filter((i) => !i.attributes('data-testid'))
    await fields[2].setValue('Site visit') // lane name, step, then the unconnected-step field
    await w.find('[data-testid="add-loose-step"]').trigger('click')
    await settle()
    expect(post).toHaveBeenCalledWith(`${BASE}/steps`, { key: 'step-3', lane_key: 'lane-1', label: 'Site visit', position: 2 })
    expect(post).not.toHaveBeenCalledWith(`${BASE}/edges`, expect.anything())
  })

  it('PATCH /steps/{step_key} renames a step', async () => {
    const w = await open('map')
    const input = w.find('[data-testid="rename-step-step-1"]')
    await input.setValue('Ask about the job')
    await input.trigger('change')
    await settle()
    expect(patch).toHaveBeenCalledWith(`${BASE}/steps/step-1`, { label: 'Ask about the job' })
  })

  it('DELETE /steps/{step_key} deletes a step once confirmed', async () => {
    const w = await open('map')
    await w.find('[data-testid="delete-step-step-2"]').trigger('click')
    await settle()
    expect(del).toHaveBeenCalledWith(`${BASE}/steps/step-2`)
  })

  it('POST /edges connects two steps', async () => {
    const w = await open('map')
    await w.find('[data-testid="edge-from"]').setValue('step-2')
    await w.find('[data-testid="edge-to"]').setValue('step-1')
    await w.find('[data-testid="add-edge"]').trigger('click')
    await settle()
    expect(post).toHaveBeenCalledWith(`${BASE}/edges`, { from_step: 'step-2', to_step: 'step-1' })
  })

  it('PATCH /edges/{from}/{to} sets the condition of a path', async () => {
    const w = await open('map')
    const input = w.find('[data-testid="edge-condition-step-1-step-2"]')
    await input.setValue('  if approved ')
    await input.trigger('change')
    await settle()
    expect(patch).toHaveBeenCalledWith(`${BASE}/edges/step-1/step-2`, { condition: 'if approved' })
  })

  it('DELETE /edges/{from}/{to} cuts a connection once confirmed', async () => {
    const w = await open('map')
    await w.find('[data-testid="delete-edge-step-1-step-2"]').trigger('click')
    await settle()
    expect(del).toHaveBeenCalledWith(`${BASE}/edges/step-1/step-2`)
  })
})

describe('label step edits and deletes an edge case', () => {
  it('PATCH /edge-cases/{edge_case_key} rewords an edge case', async () => {
    const w = await open('label')
    const input = w.find('[data-testid="edit-edge-case-edge-1"]')
    await input.setValue('Customer walks away')
    await input.trigger('change')
    await settle()
    expect(patch).toHaveBeenCalledWith(`${BASE}/edge-cases/edge-1`, { description: 'Customer walks away' })
  })

  it('DELETE /edge-cases/{edge_case_key} deletes it once confirmed', async () => {
    const w = await open('label')
    await w.find('[data-testid="delete-edge-case-edge-1"]').trigger('click')
    await settle()
    expect(del).toHaveBeenCalledWith(`${BASE}/edge-cases/edge-1`)
  })
})

describe('one number step ranks candidates on the server', () => {
  it('GET /one-number/candidates?return_kind= orders the list by the server rank', async () => {
    const w = await open('oneNumber')
    const order = () => w.findAll('input[type="radio"]').map((r) => (r.element as HTMLInputElement).value)
    expect(order()).toEqual(['step-2', 'step-1']) // local order: 2x4 = 8 beats 5x1 = 5
    get.mockResolvedValueOnce({ return_kind: 'more_yeses', unmeasured: [], candidates: [{ step_key: 'step-1', rank: 1 }, { step_key: 'step-2', rank: 2 }] })
    await w.find('[data-testid="one-number-rank"]').trigger('click')
    await settle()
    expect(get).toHaveBeenCalledWith(`${BASE}/one-number/candidates?return_kind=more_yeses`)
    expect(order()).toEqual(['step-1', 'step-2'])
  })
})
