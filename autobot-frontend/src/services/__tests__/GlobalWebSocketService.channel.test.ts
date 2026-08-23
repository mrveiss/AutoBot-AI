/**
 * Channel-socket migration of the global event service (#14822, #14818).
 *
 * `GlobalWebSocketService` moved from the legacy `/api/ws` broadcast endpoint to
 * the channel socket `/api/ws/live`. That endpoint speaks a different shape —
 * events arrive wrapped as `{type:'live_event', channel, event_type, event_id,
 * payload}` — while every existing listener in the app is registered against the
 * old flat `{type, payload}` form.
 *
 * The unwrapping seam is what keeps those listeners working, so these tests pin
 * it, along with the high-water mark that lets a reconnect replay the gap.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { GlobalWebSocketService } from '@/services/GlobalWebSocketService'

type Privates = {
  _handleMessage: (e: MessageEvent) => void
  _unwrapChannelEvent: (d: Record<string, unknown>) => Record<string, unknown>
  lastGlobalEventId: number | null
  send: (d: Record<string, unknown>) => boolean
}

function deliver(service: GlobalWebSocketService, payload: unknown): void {
  ;(service as unknown as Privates)._handleMessage({
    data: JSON.stringify(payload),
  } as MessageEvent)
}

function privates(service: GlobalWebSocketService): Privates {
  return service as unknown as Privates
}

function liveEvent(eventId: number, eventType = 'workflow_step_started') {
  return {
    type: 'live_event',
    channel: 'global',
    event_type: eventType,
    event_id: eventId,
    payload: { step: eventId },
  }
}

describe('GlobalWebSocketService channel unwrapping (#14822)', () => {
  let service: GlobalWebSocketService

  beforeEach(() => {
    service = new GlobalWebSocketService()
  })

  it('presents a channel event to listeners in the legacy flat shape', () => {
    // The whole point of the seam: listeners registered before the migration
    // must keep firing on `event_type`, not on the literal string 'live_event'.
    const listener = vi.fn()
    service.on('workflow_step_started', listener)

    deliver(service, liveEvent(1))

    expect(listener).toHaveBeenCalledTimes(1)
    expect(listener.mock.calls[0][0]).toMatchObject({
      type: 'workflow_step_started',
      payload: { step: 1 },
      channel: 'global',
    })
  })

  it('does not emit under the wrapper type', () => {
    const wrong = vi.fn()
    service.on('live_event', wrong)

    deliver(service, liveEvent(1))

    expect(wrong).not.toHaveBeenCalled()
  })

  it('still emits the generic message event', () => {
    const listener = vi.fn()
    service.on('message', listener)

    deliver(service, liveEvent(2))

    expect(listener).toHaveBeenCalledTimes(1)
  })

  it('passes a non-channel frame through untouched', () => {
    const unwrapped = privates(service)._unwrapChannelEvent({ type: 'legacy_thing', payload: { a: 1 } })
    expect(unwrapped).toEqual({ type: 'legacy_thing', payload: { a: 1 } })
  })

  it('defaults a missing payload to an empty object rather than undefined', () => {
    const unwrapped = privates(service)._unwrapChannelEvent({
      type: 'live_event',
      channel: 'global',
      event_type: 'x',
      event_id: 1,
    })
    expect(unwrapped.payload).toEqual({})
  })
})

describe('GlobalWebSocketService control frames (#14822)', () => {
  let service: GlobalWebSocketService

  beforeEach(() => {
    service = new GlobalWebSocketService()
  })

  it.each(['subscribed', 'unsubscribed', 'connection_established'])(
    'does not dispatch the %s control frame to listeners',
    (frameType) => {
      const listener = vi.fn()
      service.on('message', listener)

      deliver(service, { type: frameType, channel: 'global' })

      expect(listener).not.toHaveBeenCalled()
    },
  )

  it('answers a server ping with an action-shaped frame', () => {
    // The channel socket dispatches on `action`; the legacy `type`-shaped pong
    // was silently ignored, leaving the heartbeat inert.
    const sent: Array<Record<string, unknown>> = []
    privates(service).send = (d) => {
      sent.push(d)
      return true
    }

    deliver(service, { type: 'ping' })

    expect(sent).toHaveLength(1)
    expect(sent[0].action).toBe('ping')
    expect(sent[0]).not.toHaveProperty('type')
  })
})

describe('GlobalWebSocketService global high-water mark (#14818)', () => {
  let service: GlobalWebSocketService

  beforeEach(() => {
    service = new GlobalWebSocketService()
  })

  it('starts with no marker', () => {
    expect(privates(service).lastGlobalEventId).toBeNull()
  })

  it('advances on each delivered event', () => {
    deliver(service, liveEvent(5))
    expect(privates(service).lastGlobalEventId).toBe(5)
    deliver(service, liveEvent(6))
    expect(privates(service).lastGlobalEventId).toBe(6)
  })

  it('never moves backwards on a replayed batch', () => {
    deliver(service, liveEvent(9))
    deliver(service, liveEvent(2))
    expect(privates(service).lastGlobalEventId).toBe(9)
  })

  it('clears the marker on resync and tells listeners to rebuild', () => {
    const listener = vi.fn()
    service.on('resync', listener)
    deliver(service, liveEvent(9))

    deliver(service, { type: 'resync', channel: 'global', reason: 'gap_exceeds_retention' })

    expect(privates(service).lastGlobalEventId).toBeNull()
    expect(listener).toHaveBeenCalledTimes(1)
  })

  it('ignores a non-numeric event_id rather than corrupting the marker', () => {
    deliver(service, liveEvent(4))
    deliver(service, { ...liveEvent(0), event_id: 'not-a-number' })
    expect(privates(service).lastGlobalEventId).toBe(4)
  })
})
