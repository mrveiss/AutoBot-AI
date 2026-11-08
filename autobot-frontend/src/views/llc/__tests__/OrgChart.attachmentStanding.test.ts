// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #20682: the attach and detach routes answer 403 to anyone who is not an owner/admin of the
// company, so the org chart must not offer them to anyone else. Who may is the members list's
// server-derived `viewer_can_manage` (it also lets a platform admin with no membership through);
// until it is known the controls stay hidden.

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
  useRoute: () => ({ params: { companyId: 'c1' }, query: {} }),
}))
const companyRef = ref('c1')
vi.mock('@/composables/llc/useLlcCompanyContext', () => ({
  useLlcCompanyContext: () => ({
    companyId: companyRef,
    resolveCompanyId: () => Promise.resolve(companyRef.value),
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
const PROCESSES = [{ role_id: 'r1', role_name: 'Head of Sales', workflow_id: 'wf-1' }]
const TOOLS = [{ role_id: 'r1', role_name: 'Head of Sales', tool_name: 'web_search' }]

function member(viewerRole: string | null, canManage = viewerRole === 'owner' || viewerRole === 'admin') {
  return [{ user_id: 'u1', display_name: 'Ada', role: viewerRole ?? 'member', viewer_role: viewerRole, viewer_can_manage: canManage }]
}

function respond(members: unknown): void {
  get.mockImplementation((url: string) => {
    if (url.includes('/members')) return typeof members === 'function' ? (members as () => unknown)() : Promise.resolve(members)
    if (url.includes('/tool-nodes')) return Promise.resolve({ nodes: TOOLS })
    if (url.includes('/process-nodes')) return Promise.resolve({ nodes: PROCESSES })
    if (url.includes('/org-chart')) return Promise.resolve({ nodes: PEOPLE })
    if (url.includes('/api/llc/roles/')) return Promise.resolve([{ id: 'r1', name: 'Head of Sales' }])
    return Promise.resolve({ nodes: [] })
  })
}

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

async function canvasWrapper() {
  const wrapper = mount(OrgChart, {
    global: { plugins: [i18n], stubs: { CanvasNodeSidebar: true, OrgPeopleList: true } },
  })
  await flushPromises()
  await wrapper.find('[data-testid="org-view-canvas"]').trigger('click')
  await flushPromises()
  return wrapper
}

const CONTROLS = ['process-detach-btn', 'tool-detach-btn', 'process-attach-form', 'tool-attach-form']

describe('OrgChart attachment controls follow the server owner/admin check (#20682)', () => {
  beforeEach(() => {
    get.mockReset()
  })

  it.each(['owner', 'admin'])('shows detach and attach to a company %s', async (role) => {
    respond(member(role))
    const wrapper = await canvasWrapper()
    expect(wrapper.find('[data-testid="org-standing-unavailable"]').exists()).toBe(false)
    // Guard against a vacuous pass: the canvas did draw the nodes the buttons sit on.
    expect(wrapper.findAll('[data-testid="process-detach-btn"]').length).toBeGreaterThan(0)
    for (const id of CONTROLS) expect(wrapper.find(`[data-testid="${id}"]`).exists()).toBe(true)
  })

  it.each(['member', 'lead', 'guest'])('hides every attach and detach control from a %s', async (role) => {
    respond(member(role))
    const wrapper = await canvasWrapper()
    expect(wrapper.find('[data-testid="org-view-canvas"]').exists()).toBe(true)
    for (const id of CONTROLS) expect(wrapper.find(`[data-testid="${id}"]`).exists()).toBe(false)
  })

  it('hides them from a viewer with no membership the server does not let through', async () => {
    respond(member(null))
    const wrapper = await canvasWrapper()
    for (const id of CONTROLS) expect(wrapper.find(`[data-testid="${id}"]`).exists()).toBe(false)
  })

  it('offers them to a platform admin with no membership, as the server allows (#20682)', async () => {
    respond(member(null, true))
    const wrapper = await canvasWrapper()
    for (const id of CONTROLS) expect(wrapper.find(`[data-testid="${id}"]`).exists()).toBe(true)
  })

  it('hides them while the viewer standing cannot be read', async () => {
    respond(() => Promise.reject(new Error('HTTP 503')))
    const wrapper = await canvasWrapper()
    // Said, not silent: a failed load must not read as a permission refusal.
    expect(wrapper.find('[data-testid="org-standing-unavailable"]').exists()).toBe(true)
    for (const id of CONTROLS) expect(wrapper.find(`[data-testid="${id}"]`).exists()).toBe(false)
  })
})
