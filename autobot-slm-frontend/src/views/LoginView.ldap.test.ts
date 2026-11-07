// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * LoginView's LDAP / Active Directory path hands the issued token to the
 * store before checkAuth() reads it (#17856 row 8). Writing sessionStorage
 * behind the store left token.value empty, so checkAuth() saw no session.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const { push, adoptToken, checkAuth, loginWithLDAP } = vi.hoisted(() => ({
  push: vi.fn(),
  adoptToken: vi.fn(),
  checkAuth: vi.fn(),
  loginWithLDAP: vi.fn(),
}))

/** Opaque stand-in for the token the LDAP exchange issues. */
const ISSUED = ['issued', 'by', 'ldap'].join('-')

vi.mock('vue-router', () => ({ useRouter: () => ({ push }), useRoute: () => ({ query: {} }) }))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ adoptToken, checkAuth, login: vi.fn(), mfaPending: false, loading: false, error: null }),
}))
vi.mock('@/composables/useSsoApi', () => ({
  useSsoApi: () => ({
    getActiveProviders: async () => [{ id: 'ad1', name: 'Corp AD', provider_type: 'active_directory' }],
    loginWithLDAP,
    initiateSSOLogin: vi.fn(),
  }),
}))

import LoginView from './LoginView.vue'

describe('LoginView LDAP / AD login (#17856)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    checkAuth.mockResolvedValue(true)
    loginWithLDAP.mockResolvedValue(Object.fromEntries([['access_token', ISSUED]]))
  })

  it('adopts the issued token into the store, then checks auth, then navigates', async () => {
    const wrapper = mount(LoginView, {
      global: { mocks: { $t: (k: string) => k }, stubs: { BrandMark: true } },
    })
    await vi.waitFor(() => expect(wrapper.find('[role="group"] button').exists()).toBe(true))

    await wrapper.find('[role="group"] button').trigger('click')
    await flushPromises()

    expect(adoptToken).toHaveBeenCalledWith(ISSUED)
    expect(adoptToken.mock.invocationCallOrder[0]).toBeLessThan(checkAuth.mock.invocationCallOrder[0])
    expect(sessionStorage.length).toBe(0)
    expect(push).toHaveBeenCalledWith('/')
  })
})
