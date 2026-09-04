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

import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
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

/**
 * #15533 — the endpoint this view hands to PasswordChangeForm must name a route
 * the SLM actually serves.
 *
 * The oracle is the SLM's own generated contract (`autobot-slm-frontend/
 * openapi.json`, produced by `npm run gen:types:openapi` from the live app), not
 * a literal string copied out of the component: a test that asserted the string
 * would pass just as happily on `/api/users/{id}/change-password`, which is what
 * the self-service button produced before this fix and which no SLM router
 * mounts. Asserting that the modal opens is not enough either — it opened then
 * too.
 */

/**
 * #15667: the contract must be located WITHOUT `new URL(<literal>,
 * import.meta.url)`. Vite statically rewrites that exact form into an asset
 * reference, so under vitest it evaluates to a dev-server URL
 * (`http://localhost:<port>/openapi.json`) and `readFileSync` rejects it with
 * "The URL must be of scheme file", failing this whole file at import time.
 * A bare `import.meta.url` is left alone by that transform.
 */
const CONTRACT_PATH = resolve(dirname(fileURLToPath(import.meta.url)), '../../../../openapi.json')

const CONTRACT_PATHS: string[] = Object.keys(
  JSON.parse(readFileSync(CONTRACT_PATH, 'utf-8')).paths,
)

/** True when `endpoint` matches a contract path, treating `{...}` as one segment. */
function servedBySlm(endpoint: string): boolean {
  const call = endpoint.split('/').filter(Boolean)
  return CONTRACT_PATHS.some((served) => {
    const route = served.split('/').filter(Boolean)
    return (
      route.length === call.length &&
      route.every((seg, i) => seg.startsWith('{') || seg === call[i])
    )
  })
}

type PasswordVm = {
  slmUsers: Array<{ id: string; username: string }>
  openPasswordChangeModal: (user?: { id: string; username: string }, type?: 'slm' | 'autobot') => void
  passwordChangeApiEndpoint: string
  showChangePasswordModal: boolean
}

describe('UserManagementSettings password endpoint (#15533)', () => {
  function mountWithSignedInUser(): PasswordVm {
    const vm = mount(UserManagementSettings, {
      global: { plugins: [i18n], stubs: { PasswordChangeForm: true } },
    }).vm as unknown as PasswordVm
    vm.slmUsers = [{ id: 'a3f1c2d4-0000-4000-8000-000000000001', username: 'ops' }]
    return vm
  }

  it('the contract oracle rejects the pre-fix path and accepts the served one', () => {
    expect(servedBySlm('/api/users/a3f1c2d4/change-password')).toBe(false)
    expect(servedBySlm('/api/slm-users/a3f1c2d4/change-password')).toBe(true)
    expect(servedBySlm('/api/autobot-users/a3f1c2d4/change-password')).toBe(true)
  })

  it('the self-service button names a route the SLM serves', async () => {
    const vm = mountWithSignedInUser()
    await flushPromises()

    vm.openPasswordChangeModal()

    expect(vm.showChangePasswordModal).toBe(true)
    expect(vm.passwordChangeApiEndpoint).not.toBe('')
    expect(servedBySlm(vm.passwordChangeApiEndpoint)).toBe(true)
  })

  it('every reachable user type names a route the SLM serves', async () => {
    const vm = mountWithSignedInUser()
    await flushPromises()
    const user = { id: 'a3f1c2d4-0000-4000-8000-000000000002', username: 'other' }

    for (const type of ['slm', 'autobot'] as const) {
      vm.openPasswordChangeModal(user, type)
      expect(servedBySlm(vm.passwordChangeApiEndpoint)).toBe(true)
    }
  })
})
