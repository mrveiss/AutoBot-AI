/**
 * Client-side reconnect replay (#14818).
 *
 * The backend half of replay is covered by `events/channel_stream_replay_14818_test.py`.
 * This is the client half, which was the untested side: tracking the highest
 * `event_id` seen per channel, sending it back on re-subscribe, and treating a
 * `resync` directive as "your view is untrustworthy" rather than silently
 * carrying on.
 *
 * The distinguishing cases here are the negative ones — a marker that must not
 * go backwards, and a resync that must *clear* the marker. Getting either wrong
 * produces a client that asks the server to replay from a position the server
 * has already said it cannot serve.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { LiveEventService } from '@/services/LiveEventService'

/** Reach the private message handler without standing up a real socket. */
function deliver(service: LiveEventService, payload: unknown): void {
  ;(service as unknown as { _onMessage: (e: MessageEvent) => void })._onMessage({
    data: JSON.stringify(payload),
  } as MessageEvent)
}

/** Capture what the service would put on the wire. */
function captureSends(service: LiveEventService): Array<Record<string, unknown>> {
  const sent: Array<Record<string, unknown>> = []
  ;(service as unknown as { _send: (d: Record<string, unknown>) => boolean })._send = (d) => {
    sent.push(d)
    return true
  }
  return sent
}

function liveEvent(channel: string, eventId: number, eventType = 'thing.happened') {
  return {
    type: 'live_event',
    channel,
    event_type: eventType,
    event_id: eventId,
    payload: { n: eventId },
  }
}

describe('LiveEventService high-water mark (#14818)', () => {
  let service: LiveEventService

  beforeEach(() => {
    service = new LiveEventService()
  })

  it('has no marker for a channel it has never seen', () => {
    expect(service.lastSeenEventId('chat:c1')).toBeUndefined()
  })

  it('records the event_id of a delivered event', () => {
    deliver(service, liveEvent('chat:c1', 7))
    expect(service.lastSeenEventId('chat:c1')).toBe(7)
  })

  it('advances the marker as later events arrive', () => {
    deliver(service, liveEvent('chat:c1', 7))
    deliver(service, liveEvent('chat:c1', 8))
    expect(service.lastSeenEventId('chat:c1')).toBe(8)
  })

  it('never moves the marker backwards', () => {
    // A replayed batch arrives with ids below what we already hold. Lowering the
    // marker would make the next reconnect re-request events we already have.
    deliver(service, liveEvent('chat:c1', 9))
    deliver(service, liveEvent('chat:c1', 4))
    expect(service.lastSeenEventId('chat:c1')).toBe(9)
  })

  it('keeps a separate marker per channel', () => {
    deliver(service, liveEvent('chat:c1', 3))
    deliver(service, liveEvent('session:s1', 11))
    expect(service.lastSeenEventId('chat:c1')).toBe(3)
    expect(service.lastSeenEventId('session:s1')).toBe(11)
  })
})

describe('LiveEventService subscribe frames (#14818)', () => {
  let service: LiveEventService

  beforeEach(() => {
    service = new LiveEventService()
  })

  it('queues rather than sends while disconnected', () => {
    // subscribe() is guarded on isConnected — subscriptions taken before the
    // socket opens are replayed by _onOpen instead of being dropped on the
    // floor. Asserted explicitly so the queueing path is not mistaken for a
    // silently failed send.
    const sent = captureSends(service)
    service.subscribe('chat:c1', () => {})

    expect(sent).toHaveLength(0)
  })

  it('omits last_event_id on a first-ever subscribe', () => {
    service.isConnected.value = true
    const sent = captureSends(service)
    service.subscribe('chat:c1', () => {})

    expect(sent).toHaveLength(1)
    expect(sent[0]).toEqual({ action: 'subscribe', channel: 'chat:c1' })
    // Omitted rather than sent as 0: the server distinguishes "never seen
    // anything" from "resume me", and 0 would be a resume request.
    expect(sent[0]).not.toHaveProperty('last_event_id')
  })

  it('sends the marker when resuming a channel it has seen', () => {
    service.isConnected.value = true
    service.subscribe('chat:c1', () => {})
    deliver(service, liveEvent('chat:c1', 42))

    const sent = captureSends(service)
    ;(service as unknown as { _sendAction: (a: string, c: string) => void })._sendAction(
      'subscribe',
      'chat:c1',
    )

    expect(sent[0]).toEqual({ action: 'subscribe', channel: 'chat:c1', last_event_id: 42 })
  })

  it('never sends last_event_id on unsubscribe', () => {
    deliver(service, liveEvent('chat:c1', 42))
    const sent = captureSends(service)
    ;(service as unknown as { _sendAction: (a: string, c: string) => void })._sendAction(
      'unsubscribe',
      'chat:c1',
    )

    expect(sent[0]).toEqual({ action: 'unsubscribe', channel: 'chat:c1' })
  })
})

describe('LiveEventService resync handling (#14818)', () => {
  let service: LiveEventService

  beforeEach(() => {
    service = new LiveEventService()
  })

  it('clears the marker so the next subscribe does not resume from a dead position', () => {
    deliver(service, liveEvent('chat:c1', 42))
    expect(service.lastSeenEventId('chat:c1')).toBe(42)

    deliver(service, { type: 'resync', channel: 'chat:c1', reason: 'gap_exceeds_retention' })

    expect(service.lastSeenEventId('chat:c1')).toBeUndefined()
  })

  it('notifies resync listeners with the reason', () => {
    const seen: string[] = []
    service.onResync('chat:c1', (r) => seen.push(r.reason))

    deliver(service, { type: 'resync', channel: 'chat:c1', reason: 'replay_unavailable' })

    expect(seen).toEqual(['replay_unavailable'])
  })

  it('only notifies listeners for the affected channel', () => {
    const c1: string[] = []
    const s1: string[] = []
    service.onResync('chat:c1', (r) => c1.push(r.reason))
    service.onResync('session:s1', (r) => s1.push(r.reason))

    deliver(service, { type: 'resync', channel: 'chat:c1', reason: 'replay_corrupt' })

    expect(c1).toHaveLength(1)
    expect(s1).toHaveLength(0)
  })

  it('stops notifying after the returned disposer runs', () => {
    const seen: string[] = []
    const dispose = service.onResync('chat:c1', (r) => seen.push(r.reason))
    dispose()

    deliver(service, { type: 'resync', channel: 'chat:c1', reason: 'replay_unavailable' })

    expect(seen).toHaveLength(0)
  })

  it('a throwing resync listener does not stop the others', () => {
    const survivor: string[] = []
    service.onResync('chat:c1', () => {
      throw new Error('listener exploded')
    })
    service.onResync('chat:c1', (r) => survivor.push(r.reason))

    deliver(service, { type: 'resync', channel: 'chat:c1', reason: 'replay_unavailable' })

    expect(survivor).toEqual(['replay_unavailable'])
  })
})

describe('LiveEventService control frames', () => {
  let service: LiveEventService

  beforeEach(() => {
    service = new LiveEventService()
  })

  it('does not dispatch a subscribed ack to channel listeners', () => {
    const cb = vi.fn()
    service.subscribe('chat:c1', cb)

    deliver(service, { type: 'subscribed', channel: 'chat:c1', replayed: 3 })

    expect(cb).not.toHaveBeenCalled()
  })

  it('delivers a live_event to that channel listener', () => {
    const cb = vi.fn()
    service.subscribe('chat:c1', cb)

    deliver(service, liveEvent('chat:c1', 1))

    expect(cb).toHaveBeenCalledTimes(1)
    expect(cb.mock.calls[0][0].event_id).toBe(1)
  })
})
