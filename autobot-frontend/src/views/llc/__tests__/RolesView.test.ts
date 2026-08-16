// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #14221 step 6: the Company OS Roles tab.
//
// These tests assert *rendered content*, not that the component mounted. A
// mount-only test passes while the view renders an empty shell, which is how a
// data-wiring bug survives a green suite.
//
// Two of them exist because I made the mistakes they guard:
//
//  * `api.get<T>()` returns T directly — there is no axios-style `.data`
//    wrapper. My first draft read `response.data`, which is `undefined` for
//    every call (the #14062 / #13993 defect shape: reading a key the client
//    never returns). `renders role names from the API response` fails against
//    that draft.
//  * ApiClient throws a plain Error whose message already carries the server's
//    detail. My first draft read `error.response.data.detail`, so every failure
//    silently showed the generic fallback while looking correct.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const post = vi.fn()
const del = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get, post, delete: del }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { companyId: 'c1' } }),
  useRouter: () => ({ push: vi.fn() }),
}))

import RolesView from '../RolesView.vue'

const ROLE = {
  id: 'r1',
  company_id: 'c1',
  name: 'Head of Sales',
  description: 'Owns the pipeline',
  is_system: false,
}

const SYSTEM_ROLE = { id: 'r2', company_id: 'c1', name: 'platform-admin', is_system: true }

function respond(overrides: Record<string, unknown> = {}): void {
  get.mockImplementation((url: string) => {
    if (url.includes('/holders')) return Promise.resolve(overrides.holders ?? [])
    if (url.includes('/permissions')) return Promise.resolve(overrides.permissions ?? [])
    if (url.includes('/workflows')) return Promise.resolve(overrides.workflows ?? [])
    if (url.includes('/tools')) return Promise.resolve(overrides.tools ?? [])
    if (url.includes('/credentials')) return Promise.resolve(overrides.credentials ?? [])
    return Promise.resolve(overrides.roles ?? [ROLE])
  })
}

async function mountView() {
  const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
  const wrapper = mount(RolesView, {
    global: { plugins: [i18n], stubs: { BaseModal: true } },
  })
  await flushPromises()
  return wrapper
}

describe('RolesView (#14221 step 6)', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    del.mockReset()
  })

  it('renders role names from the API response', async () => {
    // Guards the `.data` mistake: with `response.data` this renders nothing.
    respond({ roles: [ROLE, SYSTEM_ROLE] })
    const wrapper = await mountView()

    expect(wrapper.text()).toContain('Head of Sales')
    expect(wrapper.text()).toContain('platform-admin')
  })

  it('renders what the selected role carries, not just that it loaded', async () => {
    respond({
      permissions: ['knowledge.read'],
      workflows: ['wf-quarterly'],
      tools: ['llc.create_work_item'],
    })
    const wrapper = await mountView()

    const text = wrapper.text()
    expect(text).toContain('knowledge.read')
    expect(text).toContain('wf-quarterly')
    expect(text).toContain('llc.create_work_item')
  })

  it('shows a past holder as past, so departure history stays visible', async () => {
    // The whole point of the issue: a tenure that ended is still a fact.
    respond({
      holders: [
        {
          id: 'a1',
          role_id: 'r1',
          holder_type: 'user',
          holder_id: 'u-9',
          ended_at: '2026-01-01T00:00:00Z',
        },
      ],
    })
    const wrapper = await mountView()

    expect(wrapper.text()).toContain('u-9')
    expect(wrapper.text()).toContain(en.llcRoles.pastHolder)
  })

  it('requests only current holders unless past ones are asked for', async () => {
    respond()
    await mountView()

    const holderCalls = get.mock.calls.map((c) => String(c[0])).filter((u) => u.includes('/holders'))
    expect(holderCalls).toHaveLength(1)
    expect(holderCalls[0]).toContain('include_past=false')
  })

  it('renders credentials as ids only', async () => {
    // The backend never exposes a secret's value or name through this surface;
    // this asserts the view does not invent a place to put one.
    respond({ credentials: ['11111111-2222-3333-4444-555555555555'] })
    const wrapper = await mountView()

    expect(wrapper.text()).toContain('11111111-2222-3333-4444-555555555555')
  })

  it("surfaces the server's reason for a refusal, not a generic message", async () => {
    // ApiClient throws `Error('HTTP 403: <detail>')`. Reading an axios-shaped
    // `error.response.data.detail` would show the generic fallback instead —
    // hiding whether the user was refused or sent something invalid.
    get.mockRejectedValue(
      new Error("HTTP 403: membership role 'member' may not perform this change"),
    )
    const wrapper = await mountView()

    expect(wrapper.text()).toContain('may not perform this change')
    expect(wrapper.text()).not.toContain(en.llcRoles.errorLoad)
  })

  it('falls back to a translated message when the error carries no detail', async () => {
    get.mockRejectedValue({})
    const wrapper = await mountView()

    expect(wrapper.text()).toContain(en.llcRoles.errorLoad)
  })

  it('reloads the list after creating a role', async () => {
    respond()
    post.mockResolvedValue(undefined)
    const wrapper = await mountView()
    const vm = wrapper.vm as unknown as {
      newRoleName: string
      createRole: () => Promise<void>
    }

    const before = get.mock.calls.length
    vm.newRoleName = 'SRE'
    await vm.createRole()
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/api/llc/roles/c1', {
      name: 'SRE',
      description: null,
    })
    expect(get.mock.calls.length).toBeGreaterThan(before)
  })

  it('shows the empty state rather than a blank panel when there are no roles', async () => {
    respond({ roles: [] })
    const wrapper = await mountView()

    expect(wrapper.text()).toContain(en.llcRoles.empty)
  })

  it('requests past holders when the toggle is on', async () => {
    respond()
    const wrapper = await mountView()
    const vm = wrapper.vm as unknown as {
      includePastHolders: boolean
      loadDetail: () => Promise<void>
    }

    vm.includePastHolders = true
    await vm.loadDetail()
    await flushPromises()

    const holderCalls = get.mock.calls.map((c) => String(c[0])).filter((u) => u.includes('/holders'))
    expect(holderCalls.at(-1)).toContain('include_past=true')
  })

  it('opens and closes the create modal', async () => {
    respond()
    const wrapper = await mountView()
    const vm = wrapper.vm as unknown as {
      isCreateModalOpen: boolean
      newRoleName: string
      openCreateModal: () => void
      closeCreateModal: () => void
    }

    vm.newRoleName = 'left over from last time'
    vm.openCreateModal()
    expect(vm.isCreateModalOpen).toBe(true)
    // Reopening must not present the previous attempt's text as a new draft.
    expect(vm.newRoleName).toBe('')

    vm.closeCreateModal()
    expect(vm.isCreateModalOpen).toBe(false)
  })

  it('surfaces the refusal when creating a role is not permitted', async () => {
    respond()
    post.mockRejectedValue(new Error("HTTP 403: membership role 'member' may not perform this change"))
    const wrapper = await mountView()
    const vm = wrapper.vm as unknown as {
      newRoleName: string
      createRole: () => Promise<void>
    }

    vm.newRoleName = 'SRE'
    await vm.createRole()
    await flushPromises()

    expect(wrapper.text()).toContain('may not perform this change')
  })

  it('deletes a role and reloads the list', async () => {
    respond()
    del.mockResolvedValue(undefined)
    const wrapper = await mountView()
    const vm = wrapper.vm as unknown as {
      selectedRoleId: string | null
      removeRole: (id: string) => Promise<void>
    }

    // The reload must see the role gone. Leaving it in the mock response would
    // model an impossible state, and the view would legitimately re-select it.
    respond({ roles: [] })
    const before = get.mock.calls.length
    await vm.removeRole('r1')
    await flushPromises()

    expect(del).toHaveBeenCalledWith('/api/llc/roles/c1/r1')
    expect(get.mock.calls.length).toBeGreaterThan(before)
    // Selection must not survive the row it pointed at, or the detail pane
    // renders a role that no longer exists.
    expect(vm.selectedRoleId).toBeNull()
    expect(wrapper.text()).toContain(en.llcRoles.empty)
  })

  it('re-selects a remaining role after a delete', async () => {
    respond()
    del.mockResolvedValue(undefined)
    const wrapper = await mountView()
    const vm = wrapper.vm as unknown as {
      selectedRoleId: string | null
      removeRole: (id: string) => Promise<void>
    }

    respond({ roles: [SYSTEM_ROLE] })
    await vm.removeRole('r1')
    await flushPromises()

    expect(vm.selectedRoleId).toBe('r2')
  })

  it('surfaces the reason a delete was refused', async () => {
    respond()
    del.mockRejectedValue(new Error('HTTP 400: a system role cannot be deleted'))
    const wrapper = await mountView()
    const vm = wrapper.vm as unknown as { removeRole: (id: string) => Promise<void> }

    await vm.removeRole('r1')
    await flushPromises()

    expect(wrapper.text()).toContain('system role cannot be deleted')
  })
})
