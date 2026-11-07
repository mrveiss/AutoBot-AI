// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #20682/#21001: the company id is not known at mount when no route param, query or stored choice
// names one: it is resolved later from the company list. The viewer's role must load once it is, or
// the owner/admin-only controls would stay hidden for the very people they are for.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref } from 'vue'
import en from '@/i18n/locales/en.json'

const get = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get, post: vi.fn(), delete: vi.fn() }),
}))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ params: {}, query: {} }),
}))
// Starts empty, as the real composable does; resolving sets it later, after the view has mounted.
const companyRef = ref('')
vi.mock('@/composables/llc/useLlcCompanyContext', () => ({
  useLlcCompanyContext: () => ({
    companyId: companyRef,
    resolveCompanyId: async () => {
      await Promise.resolve()
      companyRef.value = 'c1'
      return 'c1'
    },
  }),
}))

import OrgChart from '../OrgChart.vue'

const PEOPLE = [
  {
    id: 'ceo', node_id: 'n-ceo', name: 'Ada', title: 'CEO', status: 'idle', adapter_type: 'claude',
    is_human: false, last_heartbeat: null, budget_spent: 0, budget_total: 0, assigned_item_count: 0,
    parent_id: null, children: [],
  },
]

function respond(viewerRole: string): void {
  get.mockImplementation((url: string) => {
    if (url.endsWith('/members')) {
      return Promise.resolve([{ user_id: 'u1', display_name: 'Ada', role: 'member', viewer_can_manage: viewerRole === 'owner' }])
    }
    if (url.includes('/org-chart')) return Promise.resolve({ nodes: PEOPLE })
    if (url.includes('/api/llc/roles/')) return Promise.resolve([{ id: 'r1', name: 'Head of Sales' }])
    return Promise.resolve({ nodes: [] })
  })
}

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

async function canvasAfterLateResolve() {
  const wrapper = mount(OrgChart, {
    global: { plugins: [i18n], stubs: { CanvasNodeSidebar: true, OrgPeopleList: true } },
  })
  await flushPromises()
  await wrapper.find('[data-testid="org-view-canvas"]').trigger('click')
  await flushPromises()
  return wrapper
}

describe('OrgChart viewer role with a company id that resolves after mount', () => {
  beforeEach(() => {
    get.mockReset()
    companyRef.value = ''
  })

  it('offers the attach forms to an owner once the id resolves', async () => {
    respond('owner')
    const wrapper = await canvasAfterLateResolve()
    expect(companyRef.value).toBe('c1')
    expect(get.mock.calls.some((c) => String(c[0]).endsWith('/companies/c1/members'))).toBe(true)
    expect(wrapper.find('[data-testid="process-attach-form"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="tool-attach-form"]').exists()).toBe(true)
  })

  it('still hides them from a member', async () => {
    respond('member')
    const wrapper = await canvasAfterLateResolve()
    expect(companyRef.value).toBe('c1')
    expect(wrapper.find('[data-testid="process-attach-form"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="tool-attach-form"]').exists()).toBe(false)
  })
})
