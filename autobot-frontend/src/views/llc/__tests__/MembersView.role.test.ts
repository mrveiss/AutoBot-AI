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

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { companyId: 'co1' } }),
}))
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get, patch, post: vi.fn(), delete: vi.fn() }) }))
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

const MEMBERS = [
  { user_id: 'u1', display_name: 'Alice', role: 'owner' },
  { user_id: 'u2', display_name: 'Bob', role: 'member' },
]
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

async function mountView() {
  get.mockResolvedValue(MEMBERS.map((m) => ({ ...m })))
  const wrapper = mount(MembersView, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
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
  })

  it('PATCHes the new role and updates the row', async () => {
    patch.mockResolvedValue({})
    const wrapper = await mountView()
    await choose(wrapper, 'admin')
    expect(patch).toHaveBeenCalledWith('/api/llc/companies/co1/members/u2', { role: 'admin' })
    expect(wrapper.text()).toContain('Admin')
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

  it('leaves every control enabled (the viewer role is unknown) and disables them only while a change is in flight', async () => {
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
})
