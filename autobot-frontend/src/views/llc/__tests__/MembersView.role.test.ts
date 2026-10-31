// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #19960: the members view changes a member's role in place via PATCH.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const patch = vi.fn()
const post = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { companyId: 'co1' } }),
}))
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get, patch, post, delete: vi.fn() }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))
vi.mock('@/composables/collaboration/useCollaborationInvite', async () => {
  const { ref } = await import('vue')
  return {
    useCollaborationInvite: () => ({
      users: ref([]),
      loading: ref(false),
      errorMessage: ref(''),
      fetchUsers: vi.fn(),
    }),
  }
})

import MembersView from '../MembersView.vue'

const ALL_ROLES = ['owner', 'admin', 'member', 'guest', 'lead']
const NO_OWNER = ['admin', 'member', 'guest', 'lead']

// The server stamps the viewer's own standing on every row (#20073).
function membersFor(viewerRole: string | null, grantable: string[]) {
  return [
    { user_id: 'u1', display_name: 'Alice', role: 'owner' },
    { user_id: 'u2', display_name: 'Bob', role: 'member' },
  ].map((m) => ({ ...m, viewer_role: viewerRole, viewer_grantable_roles: grantable }))
}
let members = membersFor('owner', ALL_ROLES)
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

async function mountView() {
  get.mockResolvedValue(members.map((m) => ({ ...m })))
  const wrapper = mount(MembersView, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

/** The role badge in the changed member's own row; the select's options also spell every role. */
function badgeOf(wrapper: Awaited<ReturnType<typeof mountView>>, name: string) {
  const row = wrapper.findAll('tbody tr').find((r) => r.text().includes(name))
  return row!.find('.aui-badge').text()
}

function bobSelect(wrapper: Awaited<ReturnType<typeof mountView>>) {
  return wrapper.find('select[aria-label="Change role for Bob"]')
}

async function choose(wrapper: Awaited<ReturnType<typeof mountView>>, role: string) {
  const sel = bobSelect(wrapper)
  await sel.setValue(role)
  await flushPromises()
  return sel
}

describe('MembersView role change (#19960)', () => {
  beforeEach(() => {
    get.mockReset()
    patch.mockReset()
    members = membersFor('owner', ALL_ROLES)
  })

  it('PATCHes the new role and updates the row', async () => {
    patch.mockResolvedValue({})
    const wrapper = await mountView()
    get.mockResolvedValue(members.map((m) => (m.user_id === 'u2' ? { ...m, role: 'admin' } : { ...m })))
    await choose(wrapper, 'admin')
    expect(patch).toHaveBeenCalledWith('/api/llc/companies/co1/members/u2', { role: 'admin' })
    expect(badgeOf(wrapper, 'Bob')).toBe('Admin')
    expect(badgeOf(wrapper, 'Alice')).toBe('Owner')
    expect((bobSelect(wrapper).element as HTMLSelectElement).value).toBe('admin')
    expect(wrapper.text()).not.toContain(en.llcMembers.roleChangeForbidden)
  })

  it('shows the 403 message and reverts the row', async () => {
    patch.mockRejectedValue(Object.assign(new Error('HTTP 403'), { status: 403 }))
    const wrapper = await mountView()
    const sel = await choose(wrapper, 'admin')
    expect(wrapper.text()).toContain(en.llcMembers.roleChangeForbidden)
    expect((sel.element as HTMLSelectElement).value).toBe('member')
  })

  it('shows the 409 message and reverts the row', async () => {
    patch.mockRejectedValue(Object.assign(new Error('HTTP 409'), { status: 409 }))
    const wrapper = await mountView()
    const sel = await choose(wrapper, 'guest')
    expect(wrapper.text()).toContain(en.llcMembers.roleChangeLastOwner)
    expect((sel.element as HTMLSelectElement).value).toBe('member')
  })

  it('leaves the controls the viewer may use enabled and disables them only while a change is in flight', async () => {
    let resolve!: (v: unknown) => void
    patch.mockReturnValue(new Promise((r) => (resolve = r)))
    const wrapper = await mountView()
    const selects = () => wrapper.findAll('select.members-role-select')
    expect(selects().every((s) => !s.attributes('disabled'))).toBe(true)
    await bobSelect(wrapper).setValue('admin')
    expect(selects().every((s) => s.attributes('disabled') !== undefined)).toBe(true)
    resolve({})
    await flushPromises()
    expect(selects().every((s) => !s.attributes('disabled'))).toBe(true)
  })

  it('disables every role control for a viewer who may grant nothing', async () => {
    members = membersFor('member', [])
    const wrapper = await mountView()
    const selects = wrapper.findAll('select.members-role-select')
    expect(selects).toHaveLength(2)
    expect(selects.every((s) => s.attributes('disabled') !== undefined)).toBe(true)
    const hintId = selects[0].attributes('aria-describedby')!
    expect(wrapper.find(`#${hintId}`).text()).toBe(en.llcMembers.roleNotGrantable)
    expect(wrapper.find(`#${hintId}`).classes()).toContain('sr-only')
  })

  it('does not offer owner to an admin, and locks the owner row', async () => {
    members = membersFor('admin', NO_OWNER)
    const wrapper = await mountView()
    const bobOptions = bobSelect(wrapper).findAll('option')
    expect(bobOptions.find((o) => o.element.value === 'owner')!.attributes('disabled')).toBeDefined()
    expect(bobOptions.find((o) => o.element.value === 'admin')!.attributes('disabled')).toBeUndefined()
    expect(bobSelect(wrapper).attributes('disabled')).toBeUndefined()
    const alice = wrapper.find('select[aria-label="Change role for Alice"]')
    expect(alice.attributes('disabled')).toBeDefined()
  })

  it('treats a server that sends no standing as one that grants nothing', async () => {
    members = members.map(({ viewer_role: _role, viewer_grantable_roles: _grantable, ...m }) => m) as typeof members
    const wrapper = await mountView()
    expect(bobSelect(wrapper).attributes('disabled')).toBeDefined()
  })

  it('reloads after a change, so an owner demoting themselves loses the controls at once', async () => {
    patch.mockResolvedValue({})
    const wrapper = await mountView()
    const demoted = members.map((m) => ({ ...m, viewer_role: 'member', viewer_grantable_roles: [] }))
    demoted[0].role = 'member'
    get.mockResolvedValue(demoted)
    await wrapper.find('select[aria-label="Change role for Alice"]').setValue('member')
    await flushPromises()
    expect(get).toHaveBeenCalledTimes(2)
    expect(wrapper.findAll('select.members-role-select').every((x) => x.attributes('disabled') !== undefined)).toBe(true)
  })

  it('keeps the table on screen while a reload is in flight', async () => {
    patch.mockResolvedValue({})
    const wrapper = await mountView()
    get.mockReturnValue(new Promise(() => undefined))
    await bobSelect(wrapper).setValue('admin')
    await flushPromises()
    expect(wrapper.text()).not.toContain(en.llcMembers.loading)
    expect(bobSelect(wrapper).exists()).toBe(true)
  })
})

describe('MembersView add form (#20073)', () => {
  beforeEach(() => {
    get.mockReset()
    patch.mockReset()
    post.mockReset()
    document.body.innerHTML = ''
  })

  async function openAdd(viewerRole: string | null, grantable: string[]) {
    members = membersFor(viewerRole, grantable)
    get.mockResolvedValue(members.map((m) => ({ ...m })))
    const wrapper = mount(MembersView, { global: { plugins: [i18n] }, attachTo: document.body })
    await flushPromises()
    await wrapper.find('button.base-button, header button').trigger('click')
    await flushPromises()
    return wrapper
  }
  const roleOptions = () =>
    Array.from(document.querySelectorAll('#member-role-select option')).map((o) => (o as HTMLOptionElement).value)
  const addButton = () =>
    Array.from(document.querySelectorAll('button')).find((b) => b.textContent?.trim() === en.llcMembers.confirmAdd)!

  it('offers an admin every role but owner and defaults to member', async () => {
    await openAdd('admin', ['admin', 'member', 'guest', 'lead'])
    expect(roleOptions()).toEqual(['admin', 'member', 'guest', 'lead'])
    expect((document.querySelector('#member-role-select') as HTMLSelectElement).value).toBe('member')
  })

  it('offers nothing and blocks Add for a viewer who may grant nothing', async () => {
    await openAdd('member', [])
    expect(roleOptions()).toEqual([])
    expect(addButton().disabled).toBe(true)
    expect(document.body.textContent).toContain(en.llcMembers.addNotAllowed)
  })

  it('does not read an empty company as a refusal: it offers every role and leaves the server to decide', async () => {
    members = []
    get.mockResolvedValue([])
    const wrapper = mount(MembersView, { global: { plugins: [i18n] }, attachTo: document.body })
    await flushPromises()
    await wrapper.find('header button').trigger('click')
    await flushPromises()
    expect(roleOptions()).toEqual(['owner', 'admin', 'member', 'guest', 'lead'])
    expect(document.body.textContent).not.toContain(en.llcMembers.addNotAllowed)
  })

  it('maps a 403 on add to the refusal message', async () => {
    const wrapper = await openAdd('owner', ['owner', 'admin', 'member', 'guest', 'lead'])
    post.mockRejectedValue(Object.assign(new Error('HTTP 403'), { status: 403 }))
    const vm = wrapper.vm as unknown as { selectedUserId: string; submitAdd: () => Promise<void> }
    vm.selectedUserId = 'u9'
    await vm.submitAdd()
    await flushPromises()
    expect(document.body.textContent).toContain(en.llcMembers.roleChangeForbidden)
  })
})
