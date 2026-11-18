// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * The sign-in page says why the router or the SSO callback sent someone there (#20631).
 * The reasons arrived in the query and nothing showed them.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const route = vi.hoisted(() => ({ query: {} as Record<string, string> }))

vi.mock('vue-router', () => ({ useRouter: () => ({ push: () => undefined }), useRoute: () => route }))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ login: () => undefined, mfaPending: false, loading: false, error: null }),
}))
vi.mock('@/composables/useSsoApi', () => ({
  useSsoApi: () => ({ getActiveProviders: async () => [], loginWithLDAP: () => undefined, initiateSSOLogin: () => undefined }),
}))

import LoginView from './LoginView.vue'

async function pageText(query: Record<string, string>): Promise<string> {
  route.query = query
  const wrapper = mount(LoginView, { global: { mocks: { $t: (key: string) => key }, stubs: { BrandMark: true } } })
  await flushPromises()
  return wrapper.text()
}

describe('LoginView query errors (#20631)', () => {
  it('says the console is for administrators', async () => {
    expect(await pageText({ error: 'admin_only' })).toContain('loginView.adminOnly')
  })

  it.each(['sso_failed', 'no_token'])('reports %s as a failed SSO login', async (error) => {
    expect(await pageText({ error })).toContain('loginView.ssoLoginFailed')
  })

  it('control: no reason, no message', async () => {
    const text = await pageText({})
    expect(text).not.toContain('loginView.adminOnly')
    expect(text).not.toContain('loginView.ssoLoginFailed')
  })
})
