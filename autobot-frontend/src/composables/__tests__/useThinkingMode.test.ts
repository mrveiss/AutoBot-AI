// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useThinkingMode.test.ts — server/localStorage persistence of the extended
 * thinking toggle + budget (GH#8993). Verifies the composable routes its
 * backend reads/writes through the `fetchWithAuth` bridge (#12363 Phase 2) so
 * the JWT is attached, while keeping the graceful single-shot fallback to
 * localStorage on failure.
 */
import { describe, it, expect, beforeEach, vi, type Mock } from 'vitest'
import { nextTick } from 'vue'

const fetchWithAuthMock = vi.fn()
vi.mock('@/utils/fetchWithAuth', () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}))
vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api',
}))

let useThinkingMode: typeof import('../useThinkingMode')['useThinkingMode']

beforeEach(async () => {
  localStorage.clear()
  fetchWithAuthMock.mockReset()
  vi.resetModules()
  ;({ useThinkingMode } = await import('../useThinkingMode'))
})

function okJson(body: unknown): Response {
  return { ok: true, json: () => Promise.resolve(body) } as unknown as Response
}

describe('useThinkingMode — server load via fetchWithAuth', () => {
  it('loads server preferences through the auth bridge with credentials', async () => {
    fetchWithAuthMock.mockResolvedValue(okJson({ enabled: true, budget_tokens: 32000 }))

    const { enabled, budgetTokens, load } = useThinkingMode(() => 'sess-1')
    await load()

    expect(fetchWithAuthMock).toHaveBeenCalledWith(
      '/api/sessions/sess-1/thinking-preferences',
      expect.objectContaining({ credentials: 'include' }),
    )
    expect(enabled.value).toBe(true)
    expect(budgetTokens.value).toBe(32000)
  })

  it('unwraps a { data: prefs } envelope', async () => {
    fetchWithAuthMock.mockResolvedValue(okJson({ data: { enabled: true, budget_tokens: 5000 } }))

    const { budgetTokens, load } = useThinkingMode(() => 'sess-2')
    await load()

    expect(budgetTokens.value).toBe(5000)
  })

  it('falls back to localStorage when the server responds not-ok', async () => {
    fetchWithAuthMock.mockResolvedValue({ ok: false } as unknown as Response)
    localStorage.setItem(
      'autobot_thinking_preferences',
      JSON.stringify({ enabled: true, budget_tokens: 10000 }),
    )

    const { enabled, load } = useThinkingMode(() => 'sess-3')
    await load()

    expect(enabled.value).toBe(true)
  })

  it('does not hit the server when no session id is present', async () => {
    const { load } = useThinkingMode(() => null)
    await load()
    expect(fetchWithAuthMock).not.toHaveBeenCalled()
  })

  it('clamps an unknown budget from the server to the default', async () => {
    fetchWithAuthMock.mockResolvedValue(okJson({ enabled: false, budget_tokens: 999 }))

    const { budgetTokens, load } = useThinkingMode(() => 'sess-4')
    await load()

    expect(budgetTokens.value).toBe(10000)
  })
})

describe('useThinkingMode — persist via fetchWithAuth', () => {
  it('PUTs updated preferences through the auth bridge on change', async () => {
    fetchWithAuthMock.mockResolvedValue({ ok: true } as unknown as Response)

    const { setBudget } = useThinkingMode(() => 'sess-9')
    setBudget(32000)
    await nextTick()
    // flush:'post' watcher runs after the DOM tick; allow the microtask queue.
    await Promise.resolve()

    const putCall = (fetchWithAuthMock as Mock).mock.calls.find(
      ([, opts]) => (opts as RequestInit | undefined)?.method === 'PUT',
    )
    expect(putCall).toBeTruthy()
    // Destructure once (putCall asserted truthy above) so the RequestInit
    // access isn't a `?.`-then-required member read (no-unsafe-optional-chaining).
    const [putUrl, putInit] = putCall ?? []
    expect(putUrl).toBe('/api/sessions/sess-9/thinking-preferences')
    expect((putInit as RequestInit).credentials).toBe('include')
    expect(JSON.parse((putInit as RequestInit).body as string)).toEqual({
      enabled: false,
      budget_tokens: 32000,
    })
    // Also mirrored to localStorage.
    expect(localStorage.getItem('autobot_thinking_preferences')).toContain('32000')
  })

  it('swallows a persist failure without throwing', async () => {
    fetchWithAuthMock.mockRejectedValue(new Error('network down'))

    const { toggle } = useThinkingMode(() => 'sess-10')
    expect(() => toggle()).not.toThrow()
    await nextTick()
    await Promise.resolve()
  })
})
