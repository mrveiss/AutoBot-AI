// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #20917: a step waiting for its owner shows on the approvals page with no company selected.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const post = vi.fn()

vi.mock('vue-router', () => ({ useRoute: () => ({ params: {} }) }))
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get, post }) }))
vi.mock('@/services/LiveEventService', () => ({ default: { subscribe: vi.fn(() => vi.fn()) } }))
vi.mock('@/composables/useNotificationBus', () => ({ useNotificationBus: () => ({ showToast: vi.fn() }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import ApprovalsInbox from '../ApprovalsInbox.vue'
import { useApprovalGatesStore } from '@/stores/useApprovalGatesStore'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const STEP = {
  id: 'a1',
  title: 'Workflow step waiting for approval',
  description: '1/2: Restart nginx',
  approval_type: 'workflow_gate',
  source: 'workflow_step',
  risk_tier: 'high',
  context: { command: 'systemctl restart nginx' },
}

async function mountInbox(rows: unknown[]) {
  setActivePinia(createPinia())
  get.mockImplementation((url: string) => Promise.resolve(url.includes('/approval-gates/pending') ? rows : []))
  post.mockResolvedValue({})
  await useApprovalGatesStore().start()
  const wrapper = mount(ApprovalsInbox, {
    global: { plugins: [i18n], stubs: { StuckFileCleanupPanel: true } },
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  get.mockReset()
  post.mockReset()
})

describe('ApprovalsInbox without a company (#20917)', () => {
  it('shows a waiting workflow step and approves it through the store', async () => {
    const wrapper = await mountInbox([STEP])
    const section = wrapper.get('[data-testid="waiting-for-you"]')
    expect(section.text()).toContain('Restart nginx')
    expect(section.text()).toContain('systemctl restart nginx')
    await section.findAll('button')[0].trigger('click')
    expect(post).toHaveBeenCalledWith('/api/approval-gates/a1/approve', {})
  })

  it('labels the reject of a workflow step "Skip step" and rejects through the store', async () => {
    const wrapper = await mountInbox([STEP])
    const reject = wrapper.get('[data-testid="waiting-for-you"]').findAll('button')[1]
    expect(reject.text()).toBe('Skip step')
    await reject.trigger('click')
    expect(post).toHaveBeenCalledWith('/api/approval-gates/a1/reject', {})
  })

  it('has no section when nothing is waiting, and leaves removal proposals to their panel (control)', async () => {
    expect((await mountInbox([])).find('[data-testid="waiting-for-you"]').exists()).toBe(false)
    const proposal = { ...STEP, id: 'a2', approval_type: 'destructive_action', source: null }
    expect((await mountInbox([proposal])).find('[data-testid="waiting-for-you"]').exists()).toBe(false)
  })
})
