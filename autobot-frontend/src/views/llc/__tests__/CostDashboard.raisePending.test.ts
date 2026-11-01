// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #8214: a company that gates budget raises answers the limit PATCH with 202 pending_approval. The dashboard
// must say the request was filed and must not claim the limit changed (no close, no refetch of a new limit).

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const patch = vi.fn()
vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get, post: vi.fn(), put: vi.fn(), patch, delete: vi.fn() }),
}))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { companyId: 'c1' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

// The modal is the only @autobot/ui piece the dashboard uses; a plain one keeps its slot content in the DOM.
vi.mock('@autobot/ui', () => ({
  BaseModal: { props: ['modelValue'], template: '<div v-if="modelValue"><slot /><slot name="actions" /></div>' },
}))

vi.mock('@/utils/formatHelpers', () => ({ createDateFormatter: () => () => '' }))

import CostDashboard from '../CostDashboard.vue'
import { limitPatchBody } from '../budgetLimitRequest'

const BUDGET = {
  agent_id: 'a1', agent_name: 'Agent One', budget_mode: 'dollars', budget_limit: '10.000000',
  budget_spent: '1.000000', token_limit: null, tokens_spent: 0, remaining: '9', is_over_limit: false,
  alert_triggered: false, alert_threshold: 0.8,
}
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

async function openSettingsModal() {
  get.mockImplementation((url: string) => Promise.resolve(String(url).includes('/budget') ? [BUDGET] : []))
  const wrapper = mount(CostDashboard, {
    global: { plugins: [i18n], stubs: { Icon: true } },
  })
  await flushPromises()
  await wrapper.find('.btn-settings').trigger('click')
  return wrapper
}

describe('raising a budget limit in a company that gates it (#8214)', () => {
  beforeEach(() => {
    get.mockReset()
    patch.mockReset()
  })

  it('shows the pending notice and leaves the form open on a 202', async () => {
    patch.mockResolvedValue({ status: 'pending_approval', approval_id: 'ap1' })
    const wrapper = await openSettingsModal()
    await wrapper.find('.btn-primary').trigger('click')
    await flushPromises()

    expect(patch).toHaveBeenCalledWith('/api/llc/budget/a1/limit', expect.objectContaining({ budget_mode: 'dollars' }))
    const notice = wrapper.find('[data-testid="budget-raise-pending"]')
    expect(notice.exists()).toBe(true)
    expect(notice.text()).toBe(en.llc.cost.raisePendingApproval)
  })

  it('closes the form with no notice when the limit was applied', async () => {
    patch.mockResolvedValue({ agent_id: 'a1', budget_limit: '5.000000' })
    const wrapper = await openSettingsModal()
    await wrapper.find('.btn-primary').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="budget-raise-pending"]').exists()).toBe(false)
    expect(wrapper.find('.btn-primary').exists()).toBe(false)
  })
})

describe('limitPatchBody', () => {
  it('sends only the limit of the chosen mode', () => {
    const base = { budget_limit: 12.5, token_limit: 900, alert_threshold_pct: 80 }
    expect(limitPatchBody({ ...base, budget_mode: 'dollars' })).toEqual({
      budget_mode: 'dollars', alert_threshold: 0.8, budget_limit: '12.50',
    })
    expect(limitPatchBody({ ...base, budget_mode: 'tokens' })).toEqual({
      budget_mode: 'tokens', alert_threshold: 0.8, token_limit: 900,
    })
  })
})
