// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #13079 — the RBAC bootstrap pair in UserManagementSettings.
 *
 * `checkRbacStatus` and `initializeRbac` were the last two raw `fetch` calls in
 * this view; every other call already went through `useAutobotApi` (autobot
 * backend) or `useSlmUserApi` (SLM backend). The forked transport meant the
 * RBAC panel could 401 while the user list beside it loaded fine.
 *
 * The heavy sibling composables are stubbed so these tests stay on the two
 * endpoints that moved.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import axios from 'axios'
import UserManagementSettings from './UserManagementSettings.vue'
import en from '@/locales/en.json'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    token: 'test-token',
    isAdmin: true,
    isAuthenticated: true,
    user: { username: 'ops' },
    logout: vi.fn(),
  }),
}))

vi.mock('@/composables/useSlmUserApi', () => ({
  useSlmUserApi: () => ({
    listUsers: vi.fn(async () => []),
    listTeams: vi.fn(async () => []),
    createUser: vi.fn(),
    updateUser: vi.fn(),
    deleteUser: vi.fn(),
    createTeam: vi.fn(),
    updateTeam: vi.fn(),
    deleteTeam: vi.fn(),
  }),
}))

vi.mock('@/composables/useSsoApi', () => ({
  useSsoApi: () => ({
    listProviders: vi.fn(async () => []),
    createProvider: vi.fn(),
    updateProvider: vi.fn(),
    deleteProvider: vi.fn(),
    testProvider: vi.fn(),
  }),
}))

vi.mock('axios', () => {
  const instance = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: () => undefined },
      response: { use: () => undefined },
    },
  }
  return { default: { create: () => instance } }
})

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

type MockedClient = { get: ReturnType<typeof vi.fn>; post: ReturnType<typeof vi.fn> }

function client(): MockedClient {
  return (axios.create as unknown as () => MockedClient)()
}

type Vm = {
  error: string | null
  rbacStatus: { initialized: boolean; message: string }
  rbacInitOptions: { createAdmin: boolean; adminUsername: string }
  checkRbacStatus: () => Promise<void>
  initializeRbac: () => Promise<void>
}

function mountView(): Vm {
  return mount(UserManagementSettings, {
    global: { plugins: [i18n], stubs: { PasswordChangeForm: true } },
  }).vm as unknown as Vm
}

describe('UserManagementSettings RBAC transport (#13079)', () => {
  beforeEach(() => {
    const c = client()
    c.get.mockReset()
    c.post.mockReset()
    c.get.mockImplementation(async (url: string) => {
      if (url === '/settings/rbac/status') {
        return { data: { initialized: true, message: 'RBAC ready' }, status: 200 }
      }
      return { data: { users: [] }, status: 200 }
    })
    c.post.mockResolvedValue({ data: { message: 'RBAC initialized' }, status: 200 })
  })

  it('GETs /settings/rbac/status through the shared client', async () => {
    const vm = mountView()
    await flushPromises()
    client().get.mockClear()

    await vm.checkRbacStatus()

    expect(client().get.mock.calls[0][0]).toBe('/settings/rbac/status')
    expect(vm.rbacStatus.initialized).toBe(true)
    expect(vm.rbacStatus.message).toBe('RBAC ready')
  })

  it('POSTs the bootstrap options to /settings/rbac/initialize', async () => {
    const vm = mountView()
    await flushPromises()
    vm.rbacInitOptions.createAdmin = true
    vm.rbacInitOptions.adminUsername = 'ops'

    await vm.initializeRbac()
    await flushPromises()

    expect(client().post.mock.calls[0].slice(0, 2)).toEqual([
      '/settings/rbac/initialize',
      { create_admin: true, admin_username: 'ops' },
    ])
  })

  it('surfaces the backend detail when the bootstrap is refused', async () => {
    const vm = mountView()
    await flushPromises()
    client().post.mockRejectedValue({ response: { data: { detail: 'RBAC already initialized' } } })

    await vm.initializeRbac()

    expect(vm.error).toBe('RBAC already initialized')
  })

  it('leaves the status message unchanged text when the status probe fails', async () => {
    const vm = mountView()
    await flushPromises()
    client().get.mockRejectedValue(new Error('offline'))

    await vm.checkRbacStatus()

    expect(vm.rbacStatus.message).toBe('Failed to check RBAC status')
  })
})
