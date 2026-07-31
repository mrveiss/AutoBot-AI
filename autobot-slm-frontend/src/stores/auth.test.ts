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

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
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

/**
 * Transport contract (#13140).
 *
 * The login/MFA/me/refresh/logout path used to build its own URLs from the
 * store-private `getApiUrl()` — which hard-returns `''` under
 * `import.meta.env.DEV` and therefore ignores `VITE_API_URL`, unlike
 * `getSlmApiBase()` — and its own `Authorization` header from the reactive
 * `token` ref alone. It now goes through `slmApiClient.rawRequest`.
 *
 * These tests pin what that buys (base-URL resolution, the
 * sessionStorage→localStorage bearer fallback, an abort signal per request) and
 * what it must NOT disturb: a 401 on an `/auth/` or `/mfa/` endpoint is a
 * credential failure, so the client's auth-endpoint opt-out must leave the
 * stored session and the current route alone.
 */
describe('authStore — canonical-client transport (#13140)', () => {
  let originalLocation: Location
  let assignMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    setActivePinia(createPinia())
    sessionStorage.clear()
    localStorage.clear()
    mockFetch.mockReset()
    vi.stubGlobal('fetch', mockFetch)

    assignMock = vi.fn()
    originalLocation = window.location
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: { pathname: '/fleet', href: '', assign: assignMock } as unknown as Location,
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: originalLocation,
    })
  })

  function authHeaderOf(index: number): string | undefined {
    const init = mockFetch.mock.calls[index][1] as RequestInit
    return (init.headers as Record<string, string>)['Authorization']
  }

  it('resolves every auth endpoint under the SLM API base', async () => {
    const store = useAuthStore()

    mockFetch.mockResolvedValueOnce(jsonResponse({ access_token: 'tok', token_type: 'bearer' }))
    mockFetch.mockResolvedValueOnce(jsonResponse({ username: 'admin', is_admin: true }))
    await store.login('admin', 'pw')

    expect(mockFetch.mock.calls[0][0]).toBe('/api/auth/login')
    expect(mockFetch.mock.calls[1][0]).toBe('/api/auth/me')

    mockFetch.mockResolvedValueOnce(jsonResponse({ access_token: 'tok2', token_type: 'bearer' }))
    await store.refreshToken()
    expect(mockFetch.mock.calls[2][0]).toBe('/api/auth/refresh')

    mockFetch.mockResolvedValueOnce(jsonResponse({ logout_url: null }))
    await store.logout()
    expect(mockFetch.mock.calls[3][0]).toBe('/api/auth/logout')
  })

  it('sends the login credentials as a JSON body with an abort signal attached', async () => {
    const store = useAuthStore()
    mockFetch.mockResolvedValueOnce(jsonResponse({ requires_mfa: true, temp_token: 't' }))

    await store.login('admin', 'pw')

    const init = mockFetch.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ username: 'admin', password: 'pw' })
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json')
    // The 30s timeout the hand-rolled fetch had no equivalent of.
    expect(init.signal).toBeInstanceOf(AbortSignal)
  })

  it('attaches the bearer from sessionStorage on /auth/me', async () => {
    sessionStorage.setItem('slm_access_token', 'session-token')
    mockFetch.mockResolvedValueOnce(jsonResponse({ username: 'admin', is_admin: true }))

    const store = useAuthStore()
    await store.fetchCurrentUser()

    expect(authHeaderOf(0)).toBe('Bearer session-token')
    expect(store.user).toEqual({ username: 'admin', isAdmin: true })
  })

  it('falls back to a localStorage-persisted session on /auth/me', async () => {
    // A "remember me" session lives in localStorage; the store hydrates `token`
    // from the same pair, but the hand-rolled header depended on that ref alone.
    localStorage.setItem('slm_access_token', 'local-token')
    mockFetch.mockResolvedValueOnce(jsonResponse({ username: 'admin', is_admin: false }))

    const store = useAuthStore()
    await store.fetchCurrentUser()

    expect(authHeaderOf(0)).toBe('Bearer local-token')
  })

  it('sends the current bearer on refresh and stores the new token', async () => {
    sessionStorage.setItem('slm_access_token', 'old-token')
    mockFetch.mockResolvedValueOnce(jsonResponse({ access_token: 'new-token', token_type: 'bearer' }))

    const store = useAuthStore()
    expect(await store.refreshToken()).toBe(true)

    expect((mockFetch.mock.calls[0][1] as RequestInit).method).toBe('POST')
    expect(authHeaderOf(0)).toBe('Bearer old-token')
    expect(sessionStorage.getItem('slm_access_token')).toBe('new-token')
  })

  it('revokes server-side with the bearer still attached, then clears locally', async () => {
    sessionStorage.setItem('slm_access_token', 'live-token')
    sessionStorage.setItem('slm_user', '{"username":"admin","isAdmin":true}')
    localStorage.setItem('slm_access_token', 'live-token')
    mockFetch.mockResolvedValueOnce(jsonResponse({ logout_url: null }))

    const store = useAuthStore()
    await store.logout()

    expect(authHeaderOf(0)).toBe('Bearer live-token')
    expect(sessionStorage.getItem('slm_access_token')).toBeNull()
    expect(sessionStorage.getItem('slm_user')).toBeNull()
    expect(localStorage.getItem('slm_access_token')).toBeNull()
  })

  it('follows an RP-initiated logout_url when the backend returns one', async () => {
    sessionStorage.setItem('slm_access_token', 'live-token')
    mockFetch.mockResolvedValueOnce(jsonResponse({ logout_url: 'https://idp.example/end' }))

    const store = useAuthStore()
    await store.logout()

    expect(assignMock).toHaveBeenCalledWith('https://idp.example/end')
  })

  it('clears the local session even when the revoke call fails outright', async () => {
    sessionStorage.setItem('slm_access_token', 'live-token')
    localStorage.setItem('slm_access_token', 'live-token')
    mockFetch.mockRejectedValueOnce(new Error('network down'))

    const store = useAuthStore()
    await store.logout()

    expect(sessionStorage.getItem('slm_access_token')).toBeNull()
    expect(localStorage.getItem('slm_access_token')).toBeNull()
  })

  it('does not clear the session or redirect when a login is rejected 401', async () => {
    // The auth-endpoint opt-out (ApiClient.isAuthEndpoint): a 401 on
    // `/auth/login` is a bad password, not a rejected session.
    sessionStorage.setItem('slm_access_token', 'pre-existing')
    mockFetch.mockResolvedValueOnce(jsonResponse({ detail: 'Invalid credentials' }, false, 401))

    const store = useAuthStore()
    expect(await store.login('admin', 'wrong')).toBe(false)

    expect(store.error).toBe('Invalid credentials')
    expect(sessionStorage.getItem('slm_access_token')).toBe('pre-existing')
    expect(window.location.href).toBe('')
  })

  it('does not clear the session or redirect when an MFA code is rejected 401', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ requires_mfa: true, temp_token: 'temp-1' }))
    const store = useAuthStore()
    await store.login('admin', 'pw')

    sessionStorage.setItem('slm_access_token', 'pre-existing')
    mockFetch.mockResolvedValueOnce(jsonResponse({ detail: 'Invalid code' }, false, 401))

    expect(await store.completeMFALogin('000000')).toBe(false)
    expect(store.error).toBe('Invalid code')
    expect(sessionStorage.getItem('slm_access_token')).toBe('pre-existing')
    expect(window.location.href).toBe('')
  })
})
