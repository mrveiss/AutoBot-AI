// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Tests for useProviderFallbackApi — #11996 (umbrella #11994).

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useProviderFallbackApi } from '../useProviderFallbackApi'
import type { LiveEvent } from '@/services/LiveEventService'

const mockGet = vi.fn()
const mockSubscribe = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get: mockGet, post: vi.fn(), put: vi.fn(), delete: vi.fn(), patch: vi.fn() }),
}))

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api',
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() }),
}))

vi.mock('@/services/LiveEventService', () => ({
  default: { subscribe: (...args: unknown[]) => mockSubscribe(...args) },
}))

const FAKE_STATUS = {
  configured_chains: [
    { primary_model: 'gpt-4o', fallback_chain: 'gpt-4o → claude-3-5-sonnet', provider: 'multi' },
  ],
  active_fallbacks: [
    {
      conversation_id: 'conv-1',
      primary_model: 'gpt-4o',
      fallback_model: 'claude-3-5-sonnet',
      primary_provider: 'openai',
      fallback_provider: 'anthropic',
      timestamp: 1700000000,
    },
  ],
}

describe('useProviderFallbackApi.fetchFallbackStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls the GET /api/llm/fallback-status endpoint', async () => {
    mockGet.mockResolvedValue(FAKE_STATUS)
    const { fetchFallbackStatus } = useProviderFallbackApi()
    await fetchFallbackStatus()
    expect(mockGet).toHaveBeenCalledWith('/api/llm/fallback-status')
  })

  it('parses the response into configured_chains + active_fallbacks', async () => {
    mockGet.mockResolvedValue(FAKE_STATUS)
    const { fetchFallbackStatus } = useProviderFallbackApi()
    const result = await fetchFallbackStatus()
    expect(result.configured_chains).toHaveLength(1)
    expect(result.active_fallbacks[0].fallback_model).toBe('claude-3-5-sonnet')
    expect(result.active_fallbacks[0].fallback_provider).toBe('anthropic')
  })

  it('returns empty arrays (not null) when the API call throws', async () => {
    mockGet.mockRejectedValue(new Error('network error'))
    const { fetchFallbackStatus } = useProviderFallbackApi()
    const result = await fetchFallbackStatus()
    expect(result.configured_chains).toEqual([])
    expect(result.active_fallbacks).toEqual([])
  })

  it('tolerates a response missing the arrays', async () => {
    mockGet.mockResolvedValue({})
    const { fetchFallbackStatus } = useProviderFallbackApi()
    const result = await fetchFallbackStatus()
    expect(result.configured_chains).toEqual([])
    expect(result.active_fallbacks).toEqual([])
  })
})

describe('useProviderFallbackApi.subscribeToFallbackEvents', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('subscribes to the global channel', () => {
    mockSubscribe.mockReturnValue(() => {})
    const { subscribeToFallbackEvents } = useProviderFallbackApi()
    subscribeToFallbackEvents(() => {})
    expect(mockSubscribe).toHaveBeenCalledWith('global', expect.any(Function))
  })

  it('invokes the callback only for PROVIDER_FALLBACK events', () => {
    let handler: ((e: LiveEvent) => void) | null = null
    mockSubscribe.mockImplementation((_ch: string, h: (e: LiveEvent) => void) => {
      handler = h
      return () => {}
    })
    const cb = vi.fn()
    const { subscribeToFallbackEvents } = useProviderFallbackApi()
    subscribeToFallbackEvents(cb)

    handler!({
      type: 'live_event', channel: 'global', event_id: 1,
      event_type: 'agent_abstained', payload: {},
    })
    expect(cb).not.toHaveBeenCalled()

    handler!({
      type: 'live_event', channel: 'global', event_id: 2,
      event_type: 'provider_fallback',
      payload: { conversation_id: 'conv-1', exhausted: false, primary_model: 'gpt-4o' },
    })
    expect(cb).toHaveBeenCalledTimes(1)
    expect(cb.mock.calls[0][0].conversation_id).toBe('conv-1')
  })

  it('returns the unsubscribe function from the live-event service', () => {
    const unsub = vi.fn()
    mockSubscribe.mockReturnValue(unsub)
    const { subscribeToFallbackEvents } = useProviderFallbackApi()
    const returned = subscribeToFallbackEvents(() => {})
    expect(returned).toBe(unsub)
  })
})
