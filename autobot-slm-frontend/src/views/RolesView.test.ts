// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * RolesView transport — #13140 definition-of-done item 3.
 *
 * This view's `apiFetch` helper was migrated onto `slmApiClient` and left
 * without a test. Two of its properties are deliberate and undefended, and both
 * would be destroyed by the obvious later "simplification" to the client's typed
 * `get`/`post` helpers:
 *
 *   * **`body.detail` reaches the operator.** The helpers flatten a rejected
 *     response into `HTTP <n>: <msg>`, so the backend's reason — which this view
 *     renders in `errorMessage` — would be replaced by a status code.
 *   * **Writes are single-shot.** `post()`/`delete()` would retry a 5xx, and a
 *     retried role write is a second attempt at a change the operator confirmed
 *     once.
 *
 * The third is the defect the migration fixed and nothing pins: the bearer used
 * to come from `authStore.getAuthHeaders()`, which returns `{}` while the
 * store's `token` ref is null. That ref is seeded from storage once at store
 * construction, so a token that landed afterwards was invisible and the request
 * went out anonymous. The client re-reads storage per call.
 *
 * Asserted against the global `fetch` rather than a mocked `slmApiClient`, so the
 * endpoint paths are checked through the real base-URL resolution, not around it.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import RolesView from './RolesView.vue'
import en from '@/locales/en.json'

const TOKEN_KEY = 'slm_access_token'

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function mountView() {
  return mount(RolesView, { global: { plugins: [i18n] } })
}

/** The URLs requested, in call order. */
function requestedUrls(fetchMock: ReturnType<typeof vi.fn>): string[] {
  return fetchMock.mock.calls.map((call) => call[0] as string)
}

describe('RolesView transport', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
    fetchMock = vi.fn().mockResolvedValue(jsonResponse([]))
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('resolves every mount request against the SLM API base', async () => {
    mountView()
    await flushPromises()

    const urls = requestedUrls(fetchMock)
    expect(urls).toContain('/api/roles')
    expect(urls).toContain('/api/roles/fleet-health')
    expect(urls).toContain('/api/nodes')
  })

  it('applies the client timeout the raw fetch never had', async () => {
    mountView()
    await flushPromises()

    expect((fetchMock.mock.calls[0][1] as RequestInit).signal).toBeInstanceOf(AbortSignal)
  })

  it('reads the bearer from storage per request, not from a ref seeded at construction', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'roles-token')
    mountView()
    await flushPromises()

    for (const call of fetchMock.mock.calls) {
      const headers = call[1].headers as Record<string, string>
      expect(headers.Authorization).toBe('Bearer roles-token')
    }
  })

  it('falls back to localStorage for the bearer', async () => {
    localStorage.setItem(TOKEN_KEY, 'persisted-roles-token')
    mountView()
    await flushPromises()

    const headers = fetchMock.mock.calls[0][1].headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer persisted-roles-token')
  })

  it('sends no Authorization header when there is no session, rather than "Bearer null"', async () => {
    mountView()
    await flushPromises()

    const headers = fetchMock.mock.calls[0][1].headers as Record<string, string>
    expect(headers.Authorization).toBeUndefined()
  })

  it("surfaces the backend's own detail message, not a status code", async () => {
    // The reason this helper calls rawRequest: the typed helpers would replace
    // "role store is locked" with "HTTP 409".
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'role store is locked' }, 409))
    const wrapper = mountView()
    await flushPromises()

    const vm = wrapper.vm as unknown as { errorMessage: string | null }
    expect(vm.errorMessage).toBe('Request failed: role store is locked')
  })

  it('reports a rejection with no detail body rather than swallowing it', async () => {
    fetchMock.mockResolvedValue(new Response('', { status: 500 }))
    const wrapper = mountView()
    await flushPromises()

    const vm = wrapper.vm as unknown as { errorMessage: string | null }
    expect(vm.errorMessage).toBe('Request failed: HTTP 500')
  })

  it('dispatches a failed request ONCE — a retried role write is a second change', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'nope' }, 500))
    mountView()
    await flushPromises()

    // Three mount calls, one attempt each: no retry budget was inherited.
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('leaves a stored session alone when the backend rejects for any other reason', async () => {
    // A 500 is not a session rejection, so the client must not clear the token.
    sessionStorage.setItem(TOKEN_KEY, 'still-valid')
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'internal' }, 500))
    mountView()
    await flushPromises()

    expect(sessionStorage.getItem(TOKEN_KEY)).toBe('still-valid')
  })
})
