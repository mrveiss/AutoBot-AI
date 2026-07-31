// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * DeploymentWizard — the fallback that never ran (#13140).
 *
 * `fetchRoles` was written with a `catch` that rebuilds the role list from
 * `NODE_ROLE_METADATA` "if API fails", but the success path was guarded by
 * `if (response.ok)` with NO else. A `fetch` only rejects on a network-level
 * failure, so an HTTP failure — a 500 from the deployment service, a 403 from
 * a role the operator lacks, a 502 from the proxy — fell straight through both
 * branches: `roles` stayed EMPTY, the fallback written for exactly that case
 * never ran, and the wizard's role picker rendered blank with no explanation.
 *
 * Routing the call through `slmApiClient.get()` makes an HTTP failure a
 * rejection, so the existing fallback finally does its job. That is a
 * deliberate behaviour change, asserted here rather than assumed.
 *
 * The same call also built `Bearer ${sessionStorage.getItem(...)}`
 * unconditionally — the literal `Bearer null` with no session.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import DeploymentWizard from './DeploymentWizard.vue'
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

type WizardVm = { roles: { name: string }[]; fetchRoles: () => Promise<void> }

/**
 * The wizard also loads the fleet on mount. Route by URL so only
 * `/deployments/roles` is under test and the fleet store gets the shape it
 * expects rather than a role payload.
 */
function routeFetch(rolesResponse: () => Response) {
  return vi.fn((url: string) => {
    if (String(url).includes('/deployments/roles')) {
      return Promise.resolve(rolesResponse())
    }
    return Promise.resolve(jsonResponse({ nodes: [] }))
  })
}

function mountWizard() {
  return mount(DeploymentWizard, {
    props: { visible: true },
    global: { plugins: [i18n] },
  })
}

describe('DeploymentWizard role transport', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  let originalLocation: Location

  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
    setActivePinia(createPinia())
    fetchMock = routeFetch(() => jsonResponse({ roles: [] }))
    vi.stubGlobal('fetch', fetchMock)

    originalLocation = window.location
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: { pathname: '/deployments', href: '' } as unknown as Location,
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

  it('falls back to the built-in role metadata when the role fetch is rejected', async () => {
    // Pre-change this left `roles` empty and the picker blank.
    fetchMock = routeFetch(() => jsonResponse({ detail: 'deployment service down' }, 500))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountWizard()
    const vm = wrapper.vm as unknown as WizardVm

    await vi.waitFor(() => expect(vm.roles.length).toBeGreaterThan(0), { timeout: 9000 })
    expect(vm.roles.every((r) => typeof r.name === 'string' && r.name.length > 0)).toBe(true)
  })

  it('sends NO Authorization header when there is no session, not "Bearer null"', async () => {
    mountWizard()
    await flushPromises()

    const call = fetchMock.mock.calls.find((c) => String(c[0]).includes('/deployments/roles'))!
    expect((call[1].headers as Record<string, string>).Authorization).toBeUndefined()
  })

  it('resolves the role list against the API base with the stored bearer and a timeout', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'deploy-token')
    mountWizard()
    await flushPromises()

    const call = fetchMock.mock.calls.find((c) => String(c[0]).includes('/deployments/roles'))!
    expect(call[0]).toBe('/api/deployments/roles')
    expect((call[1].headers as Record<string, string>).Authorization).toBe('Bearer deploy-token')
    expect((call[1] as RequestInit).signal).toBeInstanceOf(AbortSignal)
  })
})
