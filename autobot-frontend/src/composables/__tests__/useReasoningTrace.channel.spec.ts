// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The reasoning trace subscribes to its OWN session's channel (#17354).
 *
 * It used to subscribe to `global`, which the backend admits every
 * authenticated client to, and each handler compared `payload.session_id`
 * against its own before rendering. That comparison is not a boundary: the tool
 * names, tool arguments, result summaries and streamed model text of every
 * other operator's turn arrived first and were dropped by politeness.
 * `session:{id}` is owner-checked in `api/live_events.py`.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const subscribe = vi.fn(() => unsubscribe)
const unsubscribe = vi.fn()

vi.mock('@/services/LiveEventService', () => ({
  default: {
    subscribe: (channel: string, cb: unknown) => subscribe(channel, cb),
  },
}))

import { useReasoningTrace } from '../useReasoningTrace'

describe('useReasoningTrace channel', () => {
  beforeEach(() => {
    subscribe.mockClear()
    unsubscribe.mockClear()
  })

  it('subscribes to the owning session channel, never to global', () => {
    useReasoningTrace('s1')

    expect(subscribe).toHaveBeenCalledTimes(1)
    expect(subscribe.mock.calls[0][0]).toBe('session:s1')
    expect(subscribe.mock.calls.map((c) => c[0])).not.toContain('global')
  })

  it('subscribes to nothing while the session id is unknown', () => {
    useReasoningTrace(null)

    expect(subscribe).not.toHaveBeenCalled()
  })

  it('re-binds when the session id changes, releasing the previous channel', async () => {
    const sessionId = ref<string | null>('s1')
    useReasoningTrace(sessionId)
    expect(subscribe.mock.calls[0][0]).toBe('session:s1')

    sessionId.value = 's2'
    await Promise.resolve()

    expect(unsubscribe).toHaveBeenCalledTimes(1)
    expect(subscribe.mock.calls[1][0]).toBe('session:s2')
  })

  it('only records trace entries for event types it handles', () => {
    const { entries } = useReasoningTrace('s1')
    const handler = subscribe.mock.calls[0][1] as (e: Record<string, unknown>) => void

    handler({ event_type: 'agent.tool.call', payload: { tool_name: 'shell', session_id: 's1' } })
    handler({ event_type: 'something.else', payload: { session_id: 's1' } })

    expect(entries.value.map((e) => e.label)).toEqual(['shell'])
  })
})
