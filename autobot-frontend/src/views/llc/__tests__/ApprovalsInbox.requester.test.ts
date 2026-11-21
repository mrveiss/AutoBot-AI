// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #20521: the requester id is the verified `user:<id>`; a label the request carried is what the inbox shows.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const get = vi.fn()

vi.mock('vue-router', () => ({ useRoute: () => ({ params: { companyId: 'c1' } }) }))
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get, post: vi.fn() }) }))
vi.mock('@/services/LiveEventService', () => ({ default: { subscribe: vi.fn(() => vi.fn()) } }))
vi.mock('@/composables/useNotificationBus', () => ({ useNotificationBus: () => ({ showToast: vi.fn() }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import ApprovalsInbox from '../ApprovalsInbox.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const USER_REQUESTER = 'user:3f2b8c1e-6a4d-4e0b-9c57-1d2e8a7b4f60'

const row = (id: string, payload: Record<string, unknown>) => ({
  id,
  company_id: 'c1',
  type: 'strategy',
  status: 'pending',
  payload,
  requested_by_agent_id: USER_REQUESTER,
  decided_by_agent_id: null,
  created_at: '2026-11-21T10:00:00Z',
})

async function mountInbox(rows: unknown[]) {
  setActivePinia(createPinia())
  get.mockImplementation((url: string) => Promise.resolve(url.includes('/api/llc/approvals') ? rows : []))
  const wrapper = mount(ApprovalsInbox, { global: { plugins: [i18n], stubs: { StuckFileCleanupPanel: true } } })
  await flushPromises()
  return wrapper
}

beforeEach(() => get.mockReset())

describe('ApprovalsInbox requester (#20521)', () => {
  it('shows the request label when it carries one', async () => {
    const wrapper = await mountInbox([row('a1', { requested_label: 'data_hygiene_console' })])
    const text = wrapper.text()
    expect(text).toContain(en.llc.approvals.requestedBy.replace('{id}', 'data_hygiene_console'))
    expect(text).not.toContain(USER_REQUESTER)
  })

  it('keeps showing the requester id when there is no label', async () => {
    const wrapper = await mountInbox([row('a2', {})])
    expect(wrapper.text()).toContain(en.llc.approvals.requestedBy.replace('{id}', USER_REQUESTER))
  })
})
