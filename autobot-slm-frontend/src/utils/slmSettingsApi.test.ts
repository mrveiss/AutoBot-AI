// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Behavioural tests for the SLM settings/setup endpoints (#13140).
 *
 * These assert what the hand-rolled `authStore.getApiUrl()` + `getAuthHeaders()`
 * copies actually LOST, not merely that a helper is called:
 *
 *   * the request reaches `getSlmApiBase()`-derived URLs, including under a
 *     co-located `/slm` base (the old `getApiUrl()` hard-returned `''` in DEV);
 *   * `Authorization` is attached from `sessionStorage` OR `localStorage` — the
 *     old `getAuthHeaders()` returned `{}` when the store ref was unhydrated,
 *     silently sending the request unauthenticated;
 *   * a 401 clears the SLM session and redirects, instead of being swallowed;
 *   * every request carries an abort signal (the timeout the copies lacked);
 *   * `getSetting`/`getWizardStatus` still return `null` on a non-OK response,
 *     and `upsertSetting` still PUTs-then-POSTs on 404.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  listSettings,
  getSetting,
  upsertSetting,
  getTimeConfig,
  putTimeConfig,
  syncTimeToNodes,
  getWizardStatus,
  resetWizard,
} from './slmSettingsApi'
import { slmApiClient } from './ApiClient'

const TOKEN_KEY = 'slm_access_token'
const USER_KEY = 'slm_user'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function headerOf(call: unknown[], name: string): string | undefined {
  const init = call[1] as RequestInit
  return (init.headers as Record<string, string>)[name]
}

describe('slmSettingsApi', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  let originalLocation: Location

  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    originalLocation = window.location
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: { pathname: '/settings/general', href: '' } as unknown as Location,
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

  // -------------------------------------------------------------------------
  // Endpoint paths + base-URL resolution
  // -------------------------------------------------------------------------

  it('addresses the settings endpoints under the resolved SLM API base', async () => {
    fetchMock.mockResolvedValue(jsonResponse([]))
    await listSettings()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/settings')

    fetchMock.mockResolvedValue(jsonResponse({ key: 'a', value: null }))
    await getSetting('llc.project_disposal_policy')
    expect(fetchMock.mock.calls[1][0]).toBe('/api/settings/llc.project_disposal_policy')

    fetchMock.mockResolvedValue(jsonResponse({ timezone: 'UTC', ntp_servers: [] }))
    await getTimeConfig()
    expect(fetchMock.mock.calls[2][0]).toBe('/api/settings/time/config')

    fetchMock.mockResolvedValue(jsonResponse({ success: true, message: '', node_count: 0 }))
    await syncTimeToNodes(null)
    expect(fetchMock.mock.calls[3][0]).toBe('/api/settings/time/sync')

    fetchMock.mockResolvedValue(jsonResponse({ completed: false, current_step: 'nodes' }))
    await getWizardStatus()
    expect(fetchMock.mock.calls[4][0]).toBe('/api/setup/status')

    fetchMock.mockResolvedValue(jsonResponse({ ok: true }))
    await resetWizard()
    expect(fetchMock.mock.calls[5][0]).toBe('/api/setup/reset')
  })

  it('follows a co-located base ("/slm/api"), which the retired getApiUrl() could not', async () => {
    const override = slmApiClient as unknown as { baseUrlOverride: string | null }
    slmApiClient.setBaseUrl('/slm/api')
    try {
      fetchMock.mockResolvedValue(jsonResponse([]))
      await listSettings()
      expect(fetchMock.mock.calls[0][0]).toBe('/slm/api/settings')
    } finally {
      // Restore lazy getSlmApiBase() resolution for the remaining tests.
      override.baseUrlOverride = null
    }
  })

  // -------------------------------------------------------------------------
  // Auth header — the fallback the copies did not have
  // -------------------------------------------------------------------------

  it('sends the bearer token from sessionStorage', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'session-token')
    fetchMock.mockResolvedValue(jsonResponse([]))

    await listSettings()

    expect(headerOf(fetchMock.mock.calls[0], 'Authorization')).toBe('Bearer session-token')
  })

  it('falls back to localStorage when sessionStorage holds no token', async () => {
    localStorage.setItem(TOKEN_KEY, 'local-token')
    fetchMock.mockResolvedValue(jsonResponse([]))

    await listSettings()

    expect(headerOf(fetchMock.mock.calls[0], 'Authorization')).toBe('Bearer local-token')
  })

  it('attaches the bearer to writes as well as reads', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'session-token')
    fetchMock.mockResolvedValue(jsonResponse({ key: 'k', value: 'v' }))

    await upsertSetting('dark_mode', { value: 'true' })

    expect(headerOf(fetchMock.mock.calls[0], 'Authorization')).toBe('Bearer session-token')
    expect(headerOf(fetchMock.mock.calls[0], 'Content-Type')).toBe('application/json')
  })

  // -------------------------------------------------------------------------
  // 401 handling — previously swallowed
  // -------------------------------------------------------------------------

  it('clears the SLM session and redirects when an authenticated read is rejected', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'expired-token')
    sessionStorage.setItem(USER_KEY, '{"username":"ops"}')
    localStorage.setItem(TOKEN_KEY, 'expired-token')
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'Not authenticated' }, 401))

    await expect(listSettings()).rejects.toThrow(/401/)

    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(sessionStorage.getItem(USER_KEY)).toBeNull()
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(window.location.href).toBe('/login')
  })

  it('surfaces a server error instead of yielding an empty settings list', async () => {
    // A fresh Response per attempt: `get()` retries a 5xx, and a Response body
    // can only be read once.
    fetchMock.mockImplementation(async () => jsonResponse({ detail: 'boom' }, 500))

    await expect(listSettings({ maxRetries: 1 })).rejects.toThrow('HTTP 500: boom')
  })

  // -------------------------------------------------------------------------
  // Timeout — every request carries an abort signal
  // -------------------------------------------------------------------------

  it('carries an abort signal on every request (the timeout the copies lacked)', async () => {
    fetchMock.mockResolvedValue(jsonResponse([]))

    await listSettings()

    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(init.signal).toBeInstanceOf(AbortSignal)
  })

  // -------------------------------------------------------------------------
  // Preserved status-code contracts
  // -------------------------------------------------------------------------

  it('getSetting() returns null on a non-OK response rather than throwing', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'missing' }, 404))

    await expect(getSetting('nope')).resolves.toBeNull()
  })

  it('getTimeConfig()/getWizardStatus() return null on a non-OK response', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'missing' }, 404))

    await expect(getTimeConfig()).resolves.toBeNull()
    await expect(getWizardStatus()).resolves.toBeNull()
  })

  it('upsertSetting() PUTs first and POSTs the same body on 404', async () => {
    fetchMock.mockImplementation(async (_url: string, init: RequestInit) =>
      init.method === 'PUT' ? jsonResponse({ detail: 'no such key' }, 404) : jsonResponse({}, 201)
    )

    await expect(upsertSetting('new.key', { value: 'v', description: 'd' })).resolves.toBe(true)

    expect(fetchMock.mock.calls.map((c) => (c[1] as RequestInit).method)).toEqual(['PUT', 'POST'])
    expect(fetchMock.mock.calls[0][0]).toBe('/api/settings/new.key')
    expect(fetchMock.mock.calls[1][0]).toBe('/api/settings/new.key')
    const body = JSON.parse((fetchMock.mock.calls[1][1] as RequestInit).body as string)
    expect(body).toEqual({ value: 'v', description: 'd' })
  })

  it('upsertSetting() does not POST when the PUT succeeds', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ key: 'k', value: 'v' }))

    await expect(upsertSetting('dark_mode', { value: 'true' })).resolves.toBe(true)

    expect(fetchMock.mock.calls.map((c) => (c[1] as RequestInit).method)).toEqual(['PUT'])
  })

  it('upsertSetting() reports failure on a non-404 rejection instead of throwing', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'read only' }, 403))

    await expect(upsertSetting('dark_mode', { value: 'true' })).resolves.toBe(false)
  })

  it('putTimeConfig() sends the full TimeConfig payload', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ timezone: 'Europe/Riga', ntp_servers: ['a'] }))

    await putTimeConfig({ timezone: 'Europe/Riga', ntp_servers: ['a'] })

    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('PUT')
    expect(JSON.parse(init.body as string)).toEqual({
      timezone: 'Europe/Riga',
      ntp_servers: ['a'],
    })
  })

  it('syncTimeToNodes(null) requests every node', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ success: true, message: 'ok', node_count: 3 }))

    const result = await syncTimeToNodes(null)

    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ node_ids: null })
    expect(result.node_count).toBe(3)
  })
})
