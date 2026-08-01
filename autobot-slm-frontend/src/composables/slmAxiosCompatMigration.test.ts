// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #13079 / #13140 — the three SLM-backend composables migrated off their
 * private `axios.create` instances onto `slmApiClient` (via `slmApiCompat`).
 *
 *   * `useOrchestration.ts:115` — `axios.create({ baseURL: getSlmApiBase() })`,
 *     **no timeout at all**.
 *   * `useOrchestrationManagement.ts:86` — same, plus a 30s timeout.
 *   * `useExternalAgents.ts:23` — a bare `axios.create()`: **no baseURL** (every
 *     call site pasted `getSlmApiBase()` in) and **no timeout**.
 *
 * All three attached the bearer from `sessionStorage.getItem('slm_access_token')`
 * only — the `localStorage` fallback `stores/auth.ts` seeds from and
 * `ApiClient.getAuthToken()` (`ApiClient.ts:113`) honours was missing — and none
 * reproduced the client's 401 session teardown (`:128-151`).
 *
 * These tests run the REAL `slmApiClient` with `fetch` stubbed, so they assert
 * the header that actually goes on the wire, the AbortSignal that actually
 * bounds the request and the storage that actually gets cleared — not that a
 * mock was called. Blocks are labelled defect proof vs regression guard.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const TOKEN_KEY = 'slm_access_token'

// useOrchestrationManagement pulls in the fleet store and the SLM WebSocket;
// neither participates in the transport under test.
vi.mock('@/stores/fleet', () => ({
  useFleetStore: () => ({
    nodes: [],
    setServiceStatus: vi.fn(),
    updateServiceStatus: vi.fn(),
  }),
}))

vi.mock('@/composables/useSlmWebSocket', () => ({
  useSlmWebSocket: () => ({
    connect: vi.fn(),
    subscribeAll: vi.fn(),
    onServiceStatus: vi.fn(),
    connected: { value: false },
  }),
}))

import { useOrchestration } from './useOrchestration'
import { useOrchestrationManagement } from './useOrchestrationManagement'
import { useExternalAgents } from './useExternalAgents'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

let fetchMock: ReturnType<typeof vi.fn>
let originalLocation: Location

/**
 * The last call that reached the stubbed `fetch`.
 *
 * A private `axios.create()` instance issues XHR and never touches `fetch`, so
 * an unmigrated composable records nothing here. Asserting that explicitly
 * keeps the pre-change failure legible ("never reached slmApiClient") instead
 * of an incidental TypeError on an empty mock.
 */
function lastFetchCall(): [string, RequestInit] {
  const calls = fetchMock.mock.calls
  expect(
    calls.length,
    'the composable never reached slmApiClient — no fetch was issued'
  ).toBeGreaterThan(0)
  return calls[calls.length - 1] as [string, RequestInit]
}

function lastInit(): RequestInit {
  return lastFetchCall()[1]
}

function lastUrl(): string {
  return lastFetchCall()[0]
}

function authHeader(): unknown {
  return (lastInit().headers as Record<string, string>)['Authorization']
}

beforeEach(() => {
  sessionStorage.clear()
  localStorage.clear()
  fetchMock = vi.fn().mockResolvedValue(jsonResponse([]))
  vi.stubGlobal('fetch', fetchMock)

  originalLocation = window.location
  Object.defineProperty(window, 'location', {
    configurable: true,
    writable: true,
    value: { pathname: '/orchestration', href: '' } as unknown as Location,
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

// =============================================================================
// Defect proofs — transport the private instances did not have.
// =============================================================================

describe('the localStorage token fallback the private interceptors lacked (#13079)', () => {
  it('useExternalAgents sends the bearer held only in localStorage', async () => {
    // `stores/auth.ts` seeds its token ref from sessionStorage WITH a
    // localStorage fallback, so a session restored from localStorage alone is
    // real. The private `sessionStorage.getItem(...)` interceptor saw nothing
    // and the request went out unauthenticated.
    localStorage.setItem(TOKEN_KEY, 'local-only-token')

    await useExternalAgents().fetchAgents()

    expect(authHeader()).toBe('Bearer local-only-token')
  })

  it('useOrchestration sends the bearer held only in localStorage', async () => {
    localStorage.setItem(TOKEN_KEY, 'local-only-token')

    await useOrchestration().fetchServices()

    expect(authHeader()).toBe('Bearer local-only-token')
  })

  it('useOrchestrationManagement sends the bearer held only in localStorage', async () => {
    localStorage.setItem(TOKEN_KEY, 'local-only-token')

    await useOrchestrationManagement().fetchServiceDefinitions()

    expect(authHeader()).toBe('Bearer local-only-token')
  })

  it('still prefers the sessionStorage token when both are present', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'session-token')
    localStorage.setItem(TOKEN_KEY, 'local-token')

    await useExternalAgents().fetchAgents()

    expect(authHeader()).toBe('Bearer session-token')
  })
})

describe('the request timeout the private instances lacked (#13079)', () => {
  it('useExternalAgents bounds a request that previously had no timeout', async () => {
    // `axios.create()` with no `timeout` never aborts: a hung
    // POST /external-agents/{id}/verify (which reaches out to a remote A2A
    // agent) left the panel spinning indefinitely.
    await useExternalAgents().verifyAgent(7)

    expect(lastInit().signal).toBeInstanceOf(AbortSignal)
  })

  it('useOrchestration bounds a request that previously had no timeout', async () => {
    await useOrchestration().fetchFleetStatus()

    expect(lastInit().signal).toBeInstanceOf(AbortSignal)
  })
})

describe('the 401 session teardown the private instances lacked (#13079)', () => {
  it('clears the stored session and redirects when an authenticated call is rejected', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'expired-token')
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'token expired' }, 401))

    await useOrchestrationManagement().fetchServiceDefinitions()

    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(window.location.href).toBe('/login')
  })

  it('does NOT clear the session on a 401 to a token-less call', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'unauthenticated' }, 401))

    await useExternalAgents().fetchAgents()

    expect(window.location.href).toBe('')
  })
})

describe('FastAPI detail survives the axios.isAxiosError seam change (#13079)', () => {
  it('useOrchestration surfaces the backend detail, not "HTTP 500"', async () => {
    // `slmApiCompat` rejects with an axios-SHAPED error that is NOT an axios
    // instance, so the composable's original `axios.isAxiosError(e)` guard
    // would have skipped the detail branch and shown "HTTP 500" instead.
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'orchestrator offline' }, 500))

    const o = useOrchestration()
    await o.fetchServices()

    expect(o.error.value).toBe('orchestrator offline')
  })

  it('useOrchestrationManagement surfaces the backend detail on a refused action', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'service is masked' }, 409))

    // The composable returns `reactive(...)`, so `error` is unwrapped.
    const o = useOrchestrationManagement()
    await o.startService('autobot-backend')

    expect(o.error).toBe('service is masked')
  })

  it('useExternalAgents surfaces the backend detail', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'agent card unreachable' }, 502))

    const registry = useExternalAgents()
    await registry.verifyAgent(7)

    expect(registry.error).toBe('agent card unreachable')
  })
})

// =============================================================================
// Regression guards — the wire contract must survive the migration.
// =============================================================================

describe('endpoints stay relative to the API base (regression guard)', () => {
  it('useExternalAgents no longer pastes getSlmApiBase() into each path', async () => {
    await useExternalAgents().fetchAgents()

    expect(lastUrl()).toBe('/api/external-agents')
    // The old form double-prefixed once the client resolved the base itself.
    expect(lastUrl()).not.toContain('/api/api/')
  })

  it('useExternalAgents CRUD paths are unchanged', async () => {
    const registry = useExternalAgents()

    await registry.getAgent(3)
    expect(lastUrl()).toBe('/api/external-agents/3')

    await registry.createAgent({ name: 'a' } as never)
    expect(lastUrl()).toBe('/api/external-agents')
    expect(lastInit().method).toBe('POST')

    await registry.updateAgent(3, { name: 'b' } as never)
    expect(lastUrl()).toBe('/api/external-agents/3')
    expect(lastInit().method).toBe('PUT')

    await registry.deleteAgent(3)
    expect(lastUrl()).toBe('/api/external-agents/3')
    expect(lastInit().method).toBe('DELETE')

    await registry.refreshAgentCard(3)
    expect(lastUrl()).toBe('/api/external-agents/3/refresh')

    await registry.fetchCards()
    expect(lastUrl()).toBe('/api/external-agents/cards')
  })

  it('useOrchestration service + fleet reads keep their paths', async () => {
    const o = useOrchestration()

    await o.fetchServices()
    expect(lastUrl()).toBe('/api/orchestration/services')

    await o.fetchService('autobot-backend')
    expect(lastUrl()).toBe('/api/orchestration/services/autobot-backend')

    await o.fetchFleetStatus()
    expect(lastUrl()).toBe('/api/orchestration/status')
  })

  it('useOrchestrationManagement fleet + category paths and bodies are unchanged', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ services: [], total_services: 0 }))
    const o = useOrchestrationManagement()

    await o.fetchFleetServices()
    expect(lastUrl()).toBe('/api/fleet/services')

    await o.updateServiceCategory('autobot-backend', 'system')
    expect(lastUrl()).toBe('/api/fleet/services/autobot-backend/category')
    expect(lastInit().method).toBe('PATCH')
    expect(JSON.parse(lastInit().body as string)).toEqual({ category: 'system' })
  })

  it('useOrchestrationManagement sends JSON bodies for service actions', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ success: true }))

    await useOrchestrationManagement().startService('autobot-backend')

    expect(lastInit().method).toBe('POST')
    expect((lastInit().headers as Record<string, string>)['Content-Type']).toBe(
      'application/json'
    )
  })
})
