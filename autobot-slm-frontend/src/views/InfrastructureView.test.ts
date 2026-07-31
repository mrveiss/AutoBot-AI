// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * InfrastructureView — the `Bearer null` group (#13140).
 *
 * Seven of this issue's call sites built their credential like this:
 *
 *     Authorization: `Bearer ${sessionStorage.getItem('slm_access_token')}`
 *
 * unconditionally — `InfrastructureWizard` ×4, `InfrastructureView` ×1,
 * `DeploymentWizard` ×1 (and `AgentsView` ×3 with `authStore.token`). With no
 * session `getItem` returns `null`, template interpolation stringifies it, and
 * the request went out with the literal header `Bearer null`: a MALFORMED
 * credential rather than an absent one, which a backend is entitled to treat
 * differently from an anonymous request, and which made the resulting 401
 * indistinguishable from a genuinely expired session.
 *
 * This view is the smallest member of that group, so it carries the assertion
 * for all of them. Also asserted: the non-OK response that `if (response.ok)`
 * with no `else` used to drop now reaches the catch, and the endpoint resolves
 * against the API base.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import InfrastructureView from './InfrastructureView.vue'
import en from '@/locales/en.json'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ params: {}, query: {} }),
}))

const TOKEN_KEY = 'slm_access_token'

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function mountView() {
  return mount(InfrastructureView, {
    global: {
      plugins: [i18n],
      stubs: { InfrastructureWizard: true },
    },
  })
}

describe('InfrastructureView playbook transport', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  let originalLocation: Location

  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
    setActivePinia(createPinia())
    fetchMock = vi.fn().mockResolvedValue(jsonResponse({ playbooks: [] }))
    vi.stubGlobal('fetch', fetchMock)

    originalLocation = window.location
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: { pathname: '/infrastructure', href: '' } as unknown as Location,
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

  it('sends NO Authorization header when there is no session, not "Bearer null"', async () => {
    mountView()
    await flushPromises()

    const headers = fetchMock.mock.calls[0][1].headers as Record<string, string>
    expect(headers.Authorization).toBeUndefined()
  })

  it('sends the stored bearer when a session exists', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'infra-token')
    mountView()
    await flushPromises()

    const headers = fetchMock.mock.calls[0][1].headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer infra-token')
  })

  it('resolves the playbook list against the API base and applies a timeout', async () => {
    mountView()
    await flushPromises()

    expect(fetchMock.mock.calls[0][0]).toBe('/api/infrastructure/playbooks')
    expect((fetchMock.mock.calls[0][1] as RequestInit).signal).toBeInstanceOf(AbortSignal)
  })

  it('retries a 5xx page load, then fails without touching the session', async () => {
    // Two things pinned here. First: a 500 used to be dropped by
    // `if (response.ok)` with no else, so the view rendered "no playbooks" for
    // a dead backend exactly as it did for a genuinely empty list; it now
    // travels the error path. Second: this is a page LOAD, not a poll, so it
    // deliberately keeps `get()`'s default retry — a transient 5xx recovers on
    // its own — which is why `isLoading` is still true immediately after the
    // first attempt and only settles once the back-off is spent.
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'inventory unavailable' }, 500))
    const wrapper = mountView()
    const vm = wrapper.vm as unknown as { playbooks: unknown[]; isLoading: boolean }
    await flushPromises()

    expect(vm.isLoading).toBe(true)
    await vi.waitFor(() => expect(vm.isLoading).toBe(false), { timeout: 9000 })

    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(vm.playbooks).toEqual([])
    // A 500 is not a session rejection: the client must not clear or redirect.
    expect(window.location.href).toBe('')
  })

  it('clears the session and redirects when the playbook load is unauthorised', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'expired-token')
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'Not authenticated' }, 401))
    mountView()
    await flushPromises()

    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(window.location.href).toBe('/login')
  })
})
