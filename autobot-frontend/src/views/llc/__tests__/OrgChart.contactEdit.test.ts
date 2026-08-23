// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// #14603: the mutation half of contact editing — the PATCH the People list's
// editor submits, and the refetch that follows it. `OrgPeopleList.contactEdit
// .test.ts` proves the form itself is contact-only and carries the right
// values; this file proves OrgChart.vue wires that emit to the real endpoint
// (`PATCH /api/llc/contacts/{company_id}/{contact_id}`, which already exists
// — no backend work here) and reloads from source rather than trusting the
// form's own copy of the data (no optimistic mutation).
//
// Every reload assertion counts the GET calls, the same discipline
// `OrgChart.toolMutation.test.ts` uses for tool attach/detach — a "refetch"
// that quietly hits the `peopleLoaded` guard and does nothing would still
// leave the pre-edit name on screen while looking correct.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref } from 'vue'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const post = vi.fn()
const patch = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get, post, patch }),
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

const AGENT_NAME = 'Ada'
const USER_NAME = 'Grace'
const CONTACT_NAME = 'Hedy Lamarr'
const CONTACT_ID = 'c0ffee00-0000-0000-0000-000000000001'
const CONTACT_KEY = `contact:${CONTACT_ID}`
const USER_ID = '11111111-1111-1111-1111-111111111111'

const ORG_NODES = [
  {
    id: 'ceo',
    node_id: 'ceo-uuid',
    name: AGENT_NAME,
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
  },
  {
    id: `user:${USER_ID}`,
    node_id: USER_ID,
    name: USER_NAME,
    title: 'lead',
    status: 'idle',
    adapter_type: 'human',
    is_human: true,
    last_heartbeat: null,
    budget_spent: 0,
    budget_total: 0,
    assigned_item_count: 0,
    parent_id: null,
    children: [],
  },
]

function contactRecord(fullName: string) {
  return {
    id: CONTACT_ID,
    company_id: 'c1',
    full_name: fullName,
    email: 'hedy@supplier.example',
    phone: null,
    role_title: 'Accounts Payable',
    notes: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }
}

/** GET responses. `contactName` is what the *second* /involved call returns,
 * so a test can tell the pre-save list apart from the post-save one. */
function mockApi({
  contactName = CONTACT_NAME,
  afterSaveName = contactName,
}: { contactName?: string; afterSaveName?: string } = {}) {
  let involvedCalls = 0
  get.mockImplementation((url: string) => {
    if (url === '/api/llc/companies/c1/org-chart') {
      return Promise.resolve({ nodes: structuredClone(ORG_NODES) })
    }
    if (url === '/api/llc/companies/c1/work-items/executor-rollup') {
      return Promise.resolve({ cells: [] })
    }
    if (url === '/api/llc/contacts/c1/involved') {
      involvedCalls += 1
      const name = involvedCalls === 1 ? contactName : afterSaveName
      return Promise.resolve({ with_role: [contactRecord(name)], unassigned: [] })
    }
    if (url === '/api/llc/companies/c1/teams') {
      return Promise.resolve({ teams: [] })
    }
    throw new Error(`unexpected GET ${url}`)
  })
}

function involvedCallCount(): number {
  return get.mock.calls.filter(([url]) => url === '/api/llc/contacts/c1/involved').length
}

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

async function mountPeople() {
  const wrapper = mount(OrgChart, { global: { plugins: [i18n], stubs: { HireAgentModal: true } } })
  await flushPromises()
  await wrapper.get('[data-testid="org-view-people"]').trigger('click')
  await flushPromises()
  return wrapper
}

async function openEditor(wrapper: Awaited<ReturnType<typeof mountPeople>>) {
  await wrapper.get(`[data-testid="org-person-edit-${CONTACT_KEY}"]`).trigger('click')
}

beforeEach(() => {
  get.mockReset()
  post.mockReset()
  patch.mockReset()
  post.mockResolvedValue({})
  mockApi()
})

describe('saving a contact edit calls the existing PATCH endpoint (#14603)', () => {
  it('sends full_name, role_title, email and phone to /api/llc/contacts/{company}/{contact}', async () => {
    patch.mockResolvedValue(contactRecord('Hedy Renamed'))
    mockApi({ afterSaveName: 'Hedy Renamed' })
    const wrapper = await mountPeople()

    await openEditor(wrapper)
    await wrapper.get(`[data-testid="org-person-edit-name-${CONTACT_KEY}"]`).setValue('Hedy Renamed')
    await wrapper.get(`[data-testid="org-person-edit-form-${CONTACT_KEY}"]`).trigger('submit')
    await flushPromises()

    expect(patch).toHaveBeenCalledTimes(1)
    expect(patch).toHaveBeenCalledWith(`/api/llc/contacts/c1/${CONTACT_ID}`, {
      full_name: 'Hedy Renamed',
      role_title: 'Accounts Payable',
      email: 'hedy@supplier.example',
      phone: null,
    })
  })

  it('never reaches a user or agent — there is no edit control to click', async () => {
    const wrapper = await mountPeople()

    expect(wrapper.find(`[data-testid^="org-person-edit-user:"]`).exists()).toBe(false)
    expect(wrapper.find(`[data-testid="org-person-edit-ceo"]`).exists()).toBe(false)
    expect(patch).not.toHaveBeenCalled()
  })
})

describe('a successful save reloads from the server rather than patching locally (#14603)', () => {
  it('shows the new name only after the refetch resolves, and refetches exactly once', async () => {
    mockApi({ afterSaveName: 'Hedy Renamed' })
    patch.mockResolvedValue(contactRecord('Hedy Renamed'))
    const wrapper = await mountPeople()
    expect(involvedCallCount()).toBe(1)

    await openEditor(wrapper)
    await wrapper.get(`[data-testid="org-person-edit-name-${CONTACT_KEY}"]`).setValue('Hedy Renamed')
    await wrapper.get(`[data-testid="org-person-edit-form-${CONTACT_KEY}"]`).trigger('submit')
    await flushPromises()

    expect(involvedCallCount()).toBe(2)
    expect(wrapper.text()).toContain('Hedy Renamed')
    expect(wrapper.text()).not.toContain(CONTACT_NAME)
  })
})

describe('a failed save reports the error and leaves the contact unchanged (#14603)', () => {
  it('does not refetch and keeps showing the pre-edit name', async () => {
    patch.mockRejectedValue(new Error('HTTP 500: contact save failed'))
    const wrapper = await mountPeople()
    expect(involvedCallCount()).toBe(1)

    await openEditor(wrapper)
    await wrapper.get(`[data-testid="org-person-edit-name-${CONTACT_KEY}"]`).setValue('Hedy Renamed')
    await wrapper.get(`[data-testid="org-person-edit-form-${CONTACT_KEY}"]`).trigger('submit')
    await flushPromises()

    // No optimistic update, and no refetch — the failed call is not "reload
    // and hope", it is a reported failure with the prior state intact. The
    // editor itself stays open with the failed draft (proven in
    // OrgPeopleList.contactEdit.test.ts); what this asserts is that the
    // *underlying* data behind the row was never mutated locally.
    expect(involvedCallCount()).toBe(1)
    expect(wrapper.get(`[data-testid="org-person-edit-error-${CONTACT_KEY}"]`).text()).toBe(
      'HTTP 500: contact save failed',
    )

    // Closing the editor (without saving) returns to the read view — which
    // must still show the original name, proving the failed PATCH never
    // touched the data the row renders from.
    await wrapper.get(`[data-testid="org-person-edit-cancel-${CONTACT_KEY}"]`).trigger('click')
    expect(wrapper.text()).toContain(CONTACT_NAME)
    expect(wrapper.text()).not.toContain('Hedy Renamed')
  })
})
