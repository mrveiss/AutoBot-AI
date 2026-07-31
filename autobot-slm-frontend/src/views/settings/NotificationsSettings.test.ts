// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * NotificationsSettings — settings transport behaviour (#13140).
 *
 * This panel is representative of the four `settings/*.vue` copies that each
 * hand-rolled `fetch(`${authStore.getApiUrl()}/api/settings`, { headers:
 * authStore.getAuthHeaders() })`. The defect those copies shared is asserted
 * here end-to-end at the component boundary:
 *
 *   * the load carried NO `Authorization` header whenever the auth store's
 *     reactive `token` ref was unhydrated (`getAuthHeaders()` returns `{}`),
 *     even though the session was sitting in localStorage;
 *   * the resulting 401 was swallowed by `if (response.ok)` with no else, so
 *     the panel rendered its hard-coded defaults and reported no error — and
 *     "Save" would then write those defaults over the real stored values;
 *   * every write's response was discarded, so a rejected save still reported
 *     "Notification settings saved successfully".
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import NotificationsSettings from './NotificationsSettings.vue'
import { useAuthStore } from '@/stores/auth'
import en from '@/locales/en.json'

// The panel no longer touches the auth store, but an active Pinia is installed
// so this suite is a like-for-like harness for the pre-change component too
// (its `useAuthStore()` call would otherwise throw before any assertion runs).
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

const TOKEN_KEY = 'slm_access_token'
const USER_KEY = 'slm_user'

// vue-i18n 11 requires app.use(); the template uses the global $t.
const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function mountPanel() {
  return mount(NotificationsSettings, { global: { plugins: [i18n] } })
}

describe('NotificationsSettings', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  let originalLocation: Location

  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
    setActivePinia(createPinia())
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    originalLocation = window.location
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: { pathname: '/settings/notifications', href: '' } as unknown as Location,
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

  it('loads the stored preferences and reflects them in the toggles', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'session-token')
    fetchMock.mockResolvedValue(
      jsonResponse([
        { key: 'node_health_alerts', value: 'false', value_type: 'bool', id: 1, updated_at: '' },
        { key: 'email_notifications', value: 'true', value_type: 'bool', id: 2, updated_at: '' },
        { key: 'email_address', value: 'ops@example.test', value_type: 'str', id: 3, updated_at: '' },
      ])
    )

    const wrapper = mountPanel()
    await flushPromises()

    expect(fetchMock.mock.calls[0][0]).toBe('/api/settings')
    const boxes = wrapper.findAll('input[type="checkbox"]')
    expect((boxes[0].element as HTMLInputElement).checked).toBe(false)
    const email = wrapper.find('input[type="email"]').element as HTMLInputElement
    expect(email.value).toBe('ops@example.test')
    // Rendering that field also compiles its placeholder message. `en.json`
    // carried a bare `@` there, which vue-i18n reads as a linked-message
    // prefix, so revealing the field threw "Invalid linked format" and blanked
    // the panel. The message is now escaped as `admin{'@'}example.com`.
    expect(wrapper.find('input[type="email"]').attributes('placeholder')).toBe(
      'admin@example.com'
    )
  })

  it('authenticates the load from storage even when the auth-store ref is stale', async () => {
    // The auth store hydrates `token` once, at construction. Create it first,
    // then persist the session — the state after a token refresh performed by
    // the client, or a login in another tab. `authStore.getAuthHeaders()`
    // returns `{}` for a null ref, so the panel used to load ANONYMOUSLY and
    // then swallow the resulting 401; the canonical client reads storage per
    // request (sessionStorage, then localStorage).
    useAuthStore()
    localStorage.setItem(TOKEN_KEY, 'local-token')
    fetchMock.mockResolvedValue(jsonResponse([]))

    mountPanel()
    await flushPromises()

    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect((init.headers as Record<string, string>)['Authorization']).toBe('Bearer local-token')
    // The 30s request timeout the hand-rolled fetch had no equivalent of.
    expect(init.signal).toBeInstanceOf(AbortSignal)
  })

  it('surfaces a rejected session instead of silently rendering defaults', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'expired-token')
    sessionStorage.setItem(USER_KEY, '{"username":"ops"}')
    fetchMock.mockImplementation(async () => jsonResponse({ detail: 'Not authenticated' }, 401))

    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.find('.bg-red-50').exists()).toBe(true)
    expect(wrapper.find('.bg-red-50').text()).toContain('401')
    // …and the dead session is cleared rather than left in place.
    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(sessionStorage.getItem(USER_KEY)).toBeNull()
  })

  it('writes each preference to its own settings key', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'session-token')
    fetchMock.mockResolvedValue(jsonResponse([]))

    const wrapper = mountPanel()
    await flushPromises()
    fetchMock.mockClear()

    await wrapper.find('button').trigger('click')
    await flushPromises()

    const writes = fetchMock.mock.calls.filter((c) => (c[1] as RequestInit).method === 'PUT')
    const urls = writes.map((c) => String(c[0]))
    expect(urls).toContain('/api/settings/node_health_alerts')
    expect(urls).toContain('/api/settings/security_alerts')
    expect(urls).toContain('/api/settings/email_address')
    const body = JSON.parse((writes[0][1] as RequestInit).body as string)
    expect(body).toEqual({ value: 'true' })
    expect(wrapper.find('.bg-green-50').exists()).toBe(true)
  })

  it('reports a rejected write instead of claiming the save succeeded', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'session-token')
    fetchMock.mockResolvedValue(jsonResponse([]))

    const wrapper = mountPanel()
    await flushPromises()

    fetchMock.mockImplementation(async () => jsonResponse({ detail: 'read only' }, 403))
    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.bg-green-50').exists()).toBe(false)
    expect(wrapper.find('.bg-red-50').text()).toContain('Failed to save setting(s)')
  })
})
