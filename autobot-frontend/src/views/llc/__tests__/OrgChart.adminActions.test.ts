// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #21001: besides attach/detach (#20682), two more org chart actions are refused with a 403 to anyone
// who is not a company owner/admin: deleting a contact (the shared-directory delete,
// `require_company_admin`) and pausing/resuming/terminating an agent (`require_board_role`,
// owner/admin). Creating or editing a contact and hiring an agent have no such check on the server
// and are deliberately not gated. Who may is the members list's `viewer_can_manage`.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref } from 'vue'
import en from '@/i18n/locales/en.json'

const get = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get, post: vi.fn(), delete: vi.fn(), patch: vi.fn() }),
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
import OrgTreeNode from '../OrgTreeNode.vue'
import OrgPeopleList from '@/components/llc/OrgPeopleList.vue'
import CanvasNodeSidebar from '@/components/llc/CanvasNodeSidebar.vue'

const CONTACT = {
  id: 'c0ffee00-0000-0000-0000-000000000001', company_id: 'c1', full_name: 'Hedy Lamarr', email: 'hedy@supplier.example',
  phone: null, role_title: 'Accounts Payable', notes: null, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
}
const AGENT = {
  id: 'ceo', node_id: 'n-ceo', name: 'Ada', title: 'CEO', status: 'idle', adapter_type: 'claude',
  is_human: false, last_heartbeat: null, budget_spent: 0, budget_total: 0, assigned_item_count: 0,
  parent_id: null, children: [],
}

function respond(viewerRole: string | null | 'fail'): void {
  get.mockImplementation((url: string) => {
    if (url.endsWith('/members')) {
      return viewerRole === 'fail'
        ? Promise.reject(new Error('HTTP 503'))
        : Promise.resolve({ members: [{ user_id: 'u1', display_name: 'Ada', role: 'member' }], viewer_can_manage: viewerRole === 'owner' || viewerRole === 'admin' })
    }
    if (url.includes('/org-chart')) return Promise.resolve({ nodes: [AGENT] })
    if (url.includes('/involved')) return Promise.resolve({ with_role: [CONTACT], unassigned: [] })
    return Promise.resolve({ nodes: [], teams: [], cells: [] })
  })
}

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

async function mountChart() {
  const wrapper = mount(OrgChart, {
    global: { plugins: [i18n], stubs: { HireAgentModal: true, Teleport: true } },
  })
  await flushPromises()
  return wrapper
}

async function openDrawer(wrapper: Awaited<ReturnType<typeof mountChart>>) {
  wrapper.findAllComponents(OrgTreeNode)[0].vm.$emit('select', structuredClone(AGENT))
  await flushPromises()
}

describe('OrgChart owner/admin-only actions (#21001)', () => {
  beforeEach(() => {
    get.mockReset()
  })

  it.each(['owner', 'admin'])('offers pause and terminate to a company %s', async (role) => {
    respond(role)
    const wrapper = await mountChart()
    await openDrawer(wrapper)
    expect(wrapper.findComponent(CanvasNodeSidebar).exists()).toBe(true)
    expect(wrapper.find('[data-testid="org-drawer-pause"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="org-drawer-terminate"]').exists()).toBe(true)
  })

  it.each(['member', 'lead', 'guest', null, 'fail'])('hides pause and terminate from viewer role %s', async (role) => {
    respond(role as string | null)
    const wrapper = await mountChart()
    await openDrawer(wrapper)
    expect(wrapper.findComponent(CanvasNodeSidebar).exists()).toBe(true)
    expect(wrapper.find('[data-testid="org-drawer-pause"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="org-drawer-terminate"]').exists()).toBe(false)
  })

  async function peopleList(role: string | null | 'fail') {
    respond(role)
    const wrapper = await mountChart()
    await wrapper.get('[data-testid="org-view-people"]').trigger('click')
    await flushPromises()
    return wrapper
  }

  it.each(['owner', 'admin'])('offers contact delete to a company %s', async (role) => {
    const wrapper = await peopleList(role)
    expect(wrapper.text()).toContain('Hedy Lamarr')
    expect(wrapper.findComponent(OrgPeopleList).props('canDeleteContacts')).toBe(true)
    expect(wrapper.find(`[data-testid="org-person-delete-contact:${CONTACT.id}"]`).exists()).toBe(true)
  })

  it.each(['member', 'lead', 'guest', null, 'fail'])('hides contact delete but keeps editing for viewer role %s', async (role) => {
    const wrapper = await peopleList(role as string | null)
    expect(wrapper.text()).toContain('Hedy Lamarr')
    expect(wrapper.findComponent(OrgPeopleList).props('canDeleteContacts')).toBe(false)
    expect(wrapper.find(`[data-testid="org-person-delete-contact:${CONTACT.id}"]`).exists()).toBe(false)
    // Editing a contact is not owner/admin-only on the server, so it stays.
    expect(wrapper.find(`[data-testid="org-person-edit-contact:${CONTACT.id}"]`).exists()).toBe(true)
  })
})
