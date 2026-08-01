// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Correlation tests for the provider-fallback chip composable (#11997 /
 * umbrella #11994).
 *
 * Focus: the conversation-id → assistant-message-id mapping. The live event
 * seam is global (all conversations), so the composable must pin a fallback
 * ONLY to the message the caller's resolver returns — and must NOT attribute a
 * fallback whose conversation the resolver does not recognise (the
 * cross-conversation leak guarded by ChatMessages.resolveFallbackTargetMessage
 * returning null for unloaded conversations).
 *
 * useProviderFallbackApi is mocked so the test drives the subscribe callback
 * directly. The composable's map is module-level, so each test resets modules
 * and re-imports for isolation.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { ProviderFallbackPayload } from '@/constants/providerFallbackEvents'

vi.mock('@/composables/useProviderFallbackApi', () => ({
  useProviderFallbackApi: vi.fn(),
}))

function makePayload(conversationId: string): ProviderFallbackPayload {
  return {
    conversation_id: conversationId,
    request_id: null,
    primary_model: 'gpt-4',
    primary_provider: 'openai',
    fallback_model: 'claude',
    fallback_provider: 'anthropic',
    reason: 'rate_limit',
    chain_tried: ['openai', 'anthropic'],
    degraded_skipped: [],
    exhausted: false,
    timestamp: 0,
  }
}

describe('useProviderFallbackChip', () => {
  let captured: ((p: ProviderFallbackPayload) => void) | null
  let unsubscribe: ReturnType<typeof vi.fn>
  let useProviderFallbackChip: typeof import('../useProviderFallbackChip').useProviderFallbackChip

  beforeEach(async () => {
    vi.resetModules()
    captured = null
    unsubscribe = vi.fn()
    const api = await import('@/composables/useProviderFallbackApi')
    vi.mocked(api.useProviderFallbackApi).mockReturnValue({
      subscribeToFallbackEvents: vi.fn((cb: (p: ProviderFallbackPayload) => void) => {
        captured = cb
        return unsubscribe
      }),
    } as unknown as ReturnType<typeof api.useProviderFallbackApi>)
    ;({ useProviderFallbackChip } = await import('../useProviderFallbackChip'))
  })

  it('pins a fallback to the resolved message of its own conversation', () => {
    const { start, getFallbackForMessage } = useProviderFallbackChip()
    const resolve = vi.fn((cid: string) => (cid === 'conv-A' ? 'msg-A' : null))
    start(resolve)

    const payload = makePayload('conv-A')
    captured?.(payload)

    expect(resolve).toHaveBeenCalledWith('conv-A')
    expect(getFallbackForMessage('msg-A')).toEqual(payload)
  })

  it('does NOT attribute a fallback from an unrecognised conversation (no cross-conversation leak)', () => {
    const { start, getFallbackForMessage, fallbackByMessageId } = useProviderFallbackChip()
    // Resolver only knows conv-A (the loaded conversation); conv-B is elsewhere.
    const resolve = vi.fn((cid: string) => (cid === 'conv-A' ? 'msg-A' : null))
    start(resolve)

    captured?.(makePayload('conv-B'))

    expect(resolve).toHaveBeenCalledWith('conv-B')
    expect(fallbackByMessageId.size).toBe(0)
    expect(getFallbackForMessage('msg-A')).toBeNull()
  })

  it('stops correlating after the returned unsubscribe is called', () => {
    const { start } = useProviderFallbackChip()
    const stop = start(vi.fn(() => 'msg-A'))

    stop()

    expect(unsubscribe).toHaveBeenCalledTimes(1)
  })

  it('getFallbackForMessage returns null for a message with no fallback', () => {
    const { getFallbackForMessage } = useProviderFallbackChip()
    expect(getFallbackForMessage('never-set')).toBeNull()
  })
})
