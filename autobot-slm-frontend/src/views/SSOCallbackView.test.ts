// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * SSOCallbackView - the landing exchanges a one-time code, never reads a
 * token from the URL, and strips the query from history (#18394).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const { push, query, rawRequest, checkAuth, adoptToken } = vi.hoisted(() => ({
  push: vi.fn(),
  adoptToken: vi.fn(),
  query: {} as Record<string, string>,
  rawRequest: vi.fn(),
  checkAuth: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
  useRoute: () => ({ query }),
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ checkAuth, adoptToken }) }))
vi.mock('@/utils/ApiClient', () => ({ slmApiClient: { rawRequest } }))

import SSOCallbackView from './SSOCallbackView.vue'

function mountView() {
  return mount(SSOCallbackView, { global: { mocks: { $t: (k: string) => k } } })
}

describe('SSOCallbackView (#18394)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    checkAuth.mockResolvedValue(true)
    for (const k of Object.keys(query)) delete query[k]
    sessionStorage.clear()
    window.history.replaceState(null, '', '/sso-callback?code=abc')
  })

  it('exchanges the code by POST, stores the token, strips the query', async () => {
    query.code = 'abc'
    rawRequest.mockResolvedValue({ ok: true, json: async () => ({ access_token: 'jwt' }) })
    mountView()
    await flushPromises()
    expect(rawRequest).toHaveBeenCalledWith('/auth/sso/exchange', { method: 'POST', body: { code: 'abc' } })
    // The store adopts the token before checkAuth reads it (#17856 row 8)
    expect(adoptToken).toHaveBeenCalledWith('jwt')
    expect(adoptToken.mock.invocationCallOrder[0]).toBeLessThan(checkAuth.mock.invocationCallOrder[0])
    expect(window.location.search).toBe('')
    expect(push).toHaveBeenCalledWith('/')
  })

  it('ignores a legacy ?token= param and goes to login', async () => {
    query.token = 'leaked'
    window.history.replaceState(null, '', '/sso-callback?token=leaked')
    mountView()
    await flushPromises()
    expect(rawRequest).not.toHaveBeenCalled()
    expect(adoptToken).not.toHaveBeenCalled()
    expect(window.location.search).toBe('')
    expect(push).toHaveBeenCalledWith({ name: 'login', query: { error: 'no_token' } })
  })

  it('sends a rejected code to login with sso_failed', async () => {
    query.code = 'used'
    rawRequest.mockResolvedValue({ ok: false })
    mountView()
    await flushPromises()
    expect(adoptToken).not.toHaveBeenCalled()
    expect(push).toHaveBeenCalledWith({ name: 'login', query: { error: 'sso_failed' } })
  })
})
