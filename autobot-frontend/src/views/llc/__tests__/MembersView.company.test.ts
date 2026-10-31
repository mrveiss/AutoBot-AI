// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #19960: the members view is not remounted when the route moves to another company, so what it
// shows and what it sends are scoped to the company a request was made for.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { reactive } from 'vue'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const patch = vi.fn()
const route = reactive({ params: { companyId: 'coA' } })

vi.mock('vue-router', () => ({ useRoute: () => route }))
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

const ALL = ['owner', 'admin', 'member', 'guest', 'lead']
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

function rowsOf(prefix: string) {
  return [
    { user_id: `${prefix}-u1`, display_name: `${prefix} Alice`, role: 'owner' },
    { user_id: `${prefix}-u2`, display_name: `${prefix} Bob`, role: 'member' },
  ].map((m) => ({ ...m, viewer_role: 'owner', viewer_grantable_roles: ALL }))
}

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: Error) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function setup() {
  return mount(MembersView, { global: { plugins: [i18n] } })
}

async function moveTo(companyId: string) {
  route.params.companyId = companyId
  await flushPromises()
}

describe('MembersView company change (#19960)', () => {
  beforeEach(() => {
    get.mockReset()
    patch.mockReset()
    route.params.companyId = 'coA'
  })

  it('drops the old rows at once and loads the new company', async () => {
    get.mockResolvedValueOnce(rowsOf('A'))
    const wrapper = setup()
    await flushPromises()
    expect(wrapper.text()).toContain('A Bob')
    const next = deferred<ReturnType<typeof rowsOf>>()
    get.mockReturnValueOnce(next.promise)
    await moveTo('coB')
    expect(wrapper.text()).not.toContain('A Bob')
    expect(wrapper.findAll('select.members-role-select')).toHaveLength(0)
    expect(get).toHaveBeenLastCalledWith('/api/llc/companies/coB/members')
    next.resolve(rowsOf('B'))
    await flushPromises()
    expect(wrapper.text()).toContain('B Bob')
  })

  it('ignores a list response for a company no longer shown', async () => {
    const late = deferred<ReturnType<typeof rowsOf>>()
    get.mockReturnValueOnce(late.promise).mockResolvedValueOnce(rowsOf('B'))
    const wrapper = setup()
    await moveTo('coB')
    expect(wrapper.text()).toContain('B Bob')
    late.resolve(rowsOf('A'))
    await flushPromises()
    expect(wrapper.text()).toContain('B Bob')
    expect(wrapper.text()).not.toContain('A Bob')
  })

  it('does not let a late list failure blank or flag the company now shown', async () => {
    const late = deferred<never>()
    get.mockReturnValueOnce(late.promise).mockResolvedValueOnce(rowsOf('B'))
    const wrapper = setup()
    await moveTo('coB')
    late.reject(new Error('x'))
    await flushPromises()
    expect(wrapper.text()).toContain('B Bob')
    expect(wrapper.text()).not.toContain(en.llcMembers.loadError)
  })

  it('sends a role change to the company and user it was made for, and ignores a late answer', async () => {
    get.mockResolvedValueOnce(rowsOf('A')).mockResolvedValueOnce(rowsOf('B'))
    const answer = deferred<unknown>()
    patch.mockReturnValueOnce(answer.promise)
    const wrapper = setup()
    await flushPromises()
    await wrapper.find('select[aria-label="Change role for A Bob"]').setValue('admin')
    expect(patch).toHaveBeenCalledWith('/api/llc/companies/coA/members/A-u2', { role: 'admin' })
    await moveTo('coB')
    answer.resolve({})
    await flushPromises()
    expect(wrapper.text()).toContain('B Bob')
    const bob = wrapper.find('select[aria-label="Change role for B Bob"]')
    expect((bob.element as HTMLSelectElement).value).toBe('member')
    expect(bob.attributes('disabled')).toBeUndefined()
    expect(patch).toHaveBeenCalledTimes(1)
  })

  it('does not show a late role-change refusal against the company now shown', async () => {
    get.mockResolvedValueOnce(rowsOf('A')).mockResolvedValueOnce(rowsOf('B'))
    const answer = deferred<unknown>()
    patch.mockReturnValueOnce(answer.promise)
    const wrapper = setup()
    await flushPromises()
    await wrapper.find('select[aria-label="Change role for A Bob"]').setValue('admin')
    await moveTo('coB')
    const refused = Object.assign(new Error('HTTP 403'), { status: 403 })
    answer.reject(refused)
    await flushPromises()
    expect(wrapper.text()).not.toContain(en.llcMembers.roleChangeForbidden)
  })
})
