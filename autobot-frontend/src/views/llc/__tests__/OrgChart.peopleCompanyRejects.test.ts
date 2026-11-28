// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #21469: the People sources claimed their in-flight guard and then awaited the company resolution
// with no handler. A rejection was an unhandled promise rejection AND left the guard set, so the
// People view said "loading" for good, the canvas teams never loaded, and nothing could retry.
//
// The rejection is injected on purpose and only AFTER the mount: the tree and the executor rollup
// resolve the company on mount (and handle their own failures), so the first resolution must succeed
// for the view to reach the People list / canvas. The in-flight resolution is shared by every lazy
// loader, so a canvas entry that rejects is served to all of them — each one has its own handler.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref } from 'vue'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const post = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({
    get: (url: string, ...rest: unknown[]) =>
      String(url).endsWith('/members')
        ? Promise.resolve({ members: [{ user_id: 'u1', display_name: 'Ada', role: 'owner' }], viewer_can_manage: true })
        : get(url, ...rest),
    post,
  }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

const companyRef = ref<string | null>('c1')
const resolveCompanyId = vi.fn(() => Promise.resolve(companyRef.value))

vi.mock('@/composables/llc/useLlcCompanyContext', () => ({
  useLlcCompanyContext: () => ({ companyId: companyRef, resolveCompanyId }),
}))

import OrgChart from '../OrgChart.vue'

const CONTACT_NAME = 'Hedy Lamarr'
const INVOLVED_URL = '/api/llc/contacts/c1/involved'
const TEAMS_URL = '/api/llc/companies/c1/teams'

const NODE = {
  id: 'ceo',
  node_id: 'ceo-uuid',
  name: 'Ada',
  title: 'CEO',
  status: 'idle',
  adapter_type: 'claude',
  is_human: false,
  last_heartbeat: null,
  budget_spent: 0,
  budget_total: 0,
  assigned_item_count: 0,
  parent_id: null,
  children: [],
}

const CONTACT = {
  id: 'c0ffee00-0000-0000-0000-000000000001',
  company_id: 'c1',
  full_name: CONTACT_NAME,
  email: 'hedy@supplier.example',
  phone: null,
  role_title: 'Accounts Payable at Acme Supplies',
  notes: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

function respond(nodes: unknown[]): void {
  get.mockImplementation((url: string) => {
    if (url === '/api/llc/companies/c1/org-chart') return Promise.resolve({ nodes: structuredClone(nodes) })
    if (url === INVOLVED_URL) return Promise.resolve({ with_role: [CONTACT], unassigned: [] })
    if (url === TEAMS_URL) return Promise.resolve({ teams: [] })
    if (url === '/api/llc/companies/c1/work-items/executor-rollup') return Promise.resolve({ cells: [] })
    if (url.startsWith('/api/llc/workflows/')) return Promise.resolve([])
    return Promise.resolve({ nodes: [] })
  })
}

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

async function mountChart() {
  const wrapper = mount(OrgChart, {
    global: { plugins: [i18n], stubs: { HireAgentModal: true, CanvasNodeSidebar: true, Teleport: true } },
  })
  await flushPromises()
  return wrapper
}

type Wrapper = Awaited<ReturnType<typeof mountChart>>

async function openMode(wrapper: Wrapper, mode: 'tree' | 'people' | 'canvas'): Promise<void> {
  await wrapper.get(`[data-testid="org-view-${mode}"]`).trigger('click')
  await flushPromises()
}

function urlCalls(url: string): number {
  return get.mock.calls.filter(([u]) => String(u) === url).length
}

beforeEach(() => {
  get.mockReset()
  post.mockReset()
  post.mockResolvedValue({})
  resolveCompanyId.mockReset()
  resolveCompanyId.mockImplementation(() => Promise.resolve(companyRef.value))
  companyRef.value = 'c1'
})

describe('People sources when the company resolution rejects (#21469)', () => {
  it('ends in the unavailable state, not the loading text and not the empty state', async () => {
    respond([])
    const wrapper = await mountChart()
    resolveCompanyId.mockRejectedValueOnce(new Error('company store unavailable'))

    await openMode(wrapper, 'people')

    expect(wrapper.find('[data-testid="org-people-unavailable"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="org-people-empty"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain(en.llc.orgChart.loading)
    // Nothing was asked of the company routes: there was no company to ask about.
    expect(urlCalls(INVOLVED_URL)).toBe(0)
    expect(urlCalls(TEAMS_URL)).toBe(0)
  })

  it('retries on the next entry: reject, then resolve, then the sources load', async () => {
    respond([])
    const wrapper = await mountChart()
    resolveCompanyId.mockRejectedValueOnce(new Error('company store unavailable'))
    await openMode(wrapper, 'people')
    expect(urlCalls(INVOLVED_URL)).toBe(0)

    await openMode(wrapper, 'tree')
    await openMode(wrapper, 'people')

    expect(urlCalls(INVOLVED_URL)).toBe(1)
    expect(urlCalls(TEAMS_URL)).toBe(1)
    expect(wrapper.text()).toContain(CONTACT_NAME)
    expect(wrapper.find('[data-testid="org-people-unavailable"]').exists()).toBe(false)
  })

  it('says on the canvas that the teams are unavailable, not that the company has none', async () => {
    respond([NODE])
    const wrapper = await mountChart()
    resolveCompanyId.mockRejectedValueOnce(new Error('company store unavailable'))

    await openMode(wrapper, 'canvas')

    expect(wrapper.find('[data-testid="canvas-teams-unavailable"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="canvas-no-teams"]').exists()).toBe(false)
  })
})
