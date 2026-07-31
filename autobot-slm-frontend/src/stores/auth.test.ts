// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Auth store — MFA login transport contract (#12420).
 *
 * `POST /api/mfa/verify-login` binds `temp_token` from the QUERY string: the
 * backend declares it as a bare `str` argument beside the Pydantic body model
 * (`autobot-slm-backend/api/mfa.py:96-99`), which FastAPI treats as a query
 * parameter, and the generated OpenAPI contract lists it under
 * `operations.verify_mfa_login_api_mfa_verify_login_post.parameters.query`.
 *
 * The store used to send it in the JSON body, so the backend rejected every MFA
 * login with a 422 for the missing required query parameter. These tests drive
 * the full mfa-pending → verify flow and pin the request shape so it cannot
 * regress into the body again.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from './auth'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

const mockFetch = vi.fn()

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    json: async () => body,
  } as unknown as Response
}

describe('authStore.completeMFALogin — verify-login transport contract (#12420)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    sessionStorage.clear()
    localStorage.clear()
    mockFetch.mockReset()
    vi.stubGlobal('fetch', mockFetch)
  })

  /** Drive `login()` so the store holds a temp token, then verify the MFA code. */
  async function loginThenVerify(tempToken: string, code: string): Promise<boolean> {
    const store = useAuthStore()
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ requires_mfa: true, temp_token: tempToken })
    )
    await store.login('admin', 'pw')

    // verify-login, then the fetchCurrentUser() follow-up call.
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ access_token: 'final-token', token_type: 'bearer', expires_in: 3600 })
    )
    mockFetch.mockResolvedValueOnce(jsonResponse({ username: 'admin', is_admin: true }))
    return store.completeMFALogin(code)
  }

  it('sends temp_token as a query parameter, not a body field', async () => {
    await loginThenVerify('temp-abc', '123456')

    const [url, init] = mockFetch.mock.calls[1]
    expect(url).toContain('/api/mfa/verify-login?temp_token=temp-abc')
    expect(JSON.parse(init.body)).toEqual({ code: '123456' })
    expect(JSON.parse(init.body)).not.toHaveProperty('temp_token')
  })

  it('URL-encodes a temp token containing query-unsafe characters', async () => {
    await loginThenVerify('a+b/c=d', '123456')

    const [url] = mockFetch.mock.calls[1]
    expect(url).toContain('temp_token=a%2Bb%2Fc%3Dd')
  })

  it('stores the returned access token and clears the pending MFA state', async () => {
    const store = useAuthStore()
    const result = await loginThenVerify('temp-abc', '123456')

    expect(result).toBe(true)
    expect(store.token).toBe('final-token')
    expect(sessionStorage.getItem('slm_access_token')).toBe('final-token')
    expect(store.mfaPending).toBe(false)
  })
})

/**
 * `POST /api/auth/login` declares the union `TokenResponse | MfaChallengeResponse`
 * (`autobot-slm-backend/api/auth.py:81`). The store used to flatten both members
 * into one all-optional hand-written interface, which made `access_token`
 * optional everywhere and forced two `!` assertions on the live login path.
 *
 * Both contract members carry an `additionalProperties` catch-all, so the branch
 * is chosen by a structural check on the discriminator rather than `in`. These
 * tests pin that discrimination (#13138).
 */
describe('authStore.login — /api/auth/login response union (#13138)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    sessionStorage.clear()
    localStorage.clear()
    mockFetch.mockReset()
    vi.stubGlobal('fetch', mockFetch)
  })

  it('takes the token branch and authenticates when no MFA challenge is returned', async () => {
    const store = useAuthStore()
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ access_token: 'plain-token', token: 'plain-token', token_type: 'bearer', expires_in: 3600 })
    )
    mockFetch.mockResolvedValueOnce(jsonResponse({ username: 'admin', is_admin: true }))

    expect(await store.login('admin', 'pw')).toBe(true)
    expect(store.token).toBe('plain-token')
    expect(store.mfaPending).toBe(false)
  })

  it('takes the challenge branch without storing a token', async () => {
    const store = useAuthStore()
    mockFetch.mockResolvedValueOnce(jsonResponse({ requires_mfa: true, temp_token: 'temp-xyz' }))

    expect(await store.login('admin', 'pw')).toBe(false)
    expect(store.mfaPending).toBe(true)
    expect(store.token).toBeNull()
    expect(sessionStorage.getItem('slm_access_token')).toBeNull()
    // Only the login call — no follow-up /api/auth/me while MFA is pending.
    expect(mockFetch).toHaveBeenCalledTimes(1)
  })

  it('reads access_token, not the mirrored token field', async () => {
    // The SLM mirrors the JWT under `token` for clients written against the core
    // backend (`autobot-slm-backend/models/schemas.py:31-48`). A divergent pair
    // must resolve to `access_token`.
    const store = useAuthStore()
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ access_token: 'canonical', token: 'mirror', token_type: 'bearer', expires_in: 3600 })
    )
    mockFetch.mockResolvedValueOnce(jsonResponse({ username: 'admin', is_admin: true }))

    await store.login('admin', 'pw')
    expect(store.token).toBe('canonical')
  })

  it('does not mistake requires_mfa:false for a challenge', async () => {
    const store = useAuthStore()
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ requires_mfa: false, access_token: 'not-a-challenge', token_type: 'bearer', expires_in: 3600 })
    )
    mockFetch.mockResolvedValueOnce(jsonResponse({ username: 'admin', is_admin: true }))

    expect(await store.login('admin', 'pw')).toBe(true)
    expect(store.mfaPending).toBe(false)
    expect(store.token).toBe('not-a-challenge')
  })
})
