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

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { GlobalWebSocketService } from '@/services/GlobalWebSocketService'

type Privates = {
  _handleMessage: (e: MessageEvent) => void
  _handleOpen: (resolve: () => void) => void
  _unwrapChannelEvent: (d: Record<string, unknown>) => Record<string, unknown>
  lastGlobalEventId: number | null
  send: (d: Record<string, unknown>) => boolean
  stopHeartbeat: () => void
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

describe('GlobalWebSocketService subscribe-on-open (#14822)', () => {
  let service: GlobalWebSocketService
  let sent: Array<Record<string, unknown>>

  beforeEach(() => {
    service = new GlobalWebSocketService()
    sent = []
    privates(service).send = (d) => {
      sent.push(d)
      return true
    }
  })

  afterEach(() => {
    // _handleOpen starts the heartbeat interval; leaving it running leaks a
    // timer into later test files in the same worker.
    privates(service).stopHeartbeat()
  })

  it('subscribes to the global channel on open', () => {
    // The channel socket delivers nothing until something is subscribed, so
    // without this frame the migrated service would connect and go silent.
    privates(service)._handleOpen(() => {})

    expect(sent).toContainEqual({ action: 'subscribe', channel: 'global' })
  })

  it('omits last_event_id on a first connection', () => {
    privates(service)._handleOpen(() => {})

    const subscribe = sent.find((f) => f.action === 'subscribe')!
    expect(subscribe).not.toHaveProperty('last_event_id')
  })

  it('resumes from the marker on a reconnect', () => {
    deliver(service, liveEvent(17))
    sent.length = 0

    privates(service)._handleOpen(() => {})

    expect(sent).toContainEqual({ action: 'subscribe', channel: 'global', last_event_id: 17 })
  })

  it('resolves the connect promise', () => {
    const resolve = vi.fn()
    privates(service)._handleOpen(resolve)
    expect(resolve).toHaveBeenCalledTimes(1)
  })

  it('marks the service connected', () => {
    privates(service)._handleOpen(() => {})
    expect(service.isConnected.value).toBe(true)
    expect(service.connectionState.value).toBe('connected')
  })
})

describe('GlobalWebSocketService URL construction (#14822)', () => {
  const realLocation = window.location

  afterEach(() => {
    Object.defineProperty(window, 'location', { value: realLocation, writable: true })
  })

  function stubLocation(value: Record<string, string>) {
    Object.defineProperty(window, 'location', { value, writable: true })
  }

  it('targets the channel socket behind the nginx proxy', () => {
    stubLocation({ protocol: 'http:', host: 'autobot.example', port: '', hostname: 'autobot.example' })
    const service = new GlobalWebSocketService()

    expect(service.getWebSocketUrl().endsWith('/ws/live')).toBe(true)
    expect(service.getWebSocketUrl()).not.toMatch(/\/ws$/)
  })

  it('upgrades to wss on an https page', () => {
    // ws:// on an https page is blocked outright by browsers, so the scheme
    // has to follow the page.
    stubLocation({ protocol: 'https:', host: 'autobot.example', port: '', hostname: 'autobot.example' })
    const service = new GlobalWebSocketService()

    expect(service.getWebSocketUrl().startsWith('wss://')).toBe(true)
  })

  it('targets the channel socket through the Vite dev proxy too', () => {
    // The dev branch is a separate code path; if only the production branch
    // were migrated, local development would still talk to the legacy endpoint
    // and nobody would notice until deploy.
    stubLocation({ protocol: 'http:', host: 'localhost:5173', port: '5173', hostname: 'localhost' })
    const service = new GlobalWebSocketService()

    expect(service.getWebSocketUrl().endsWith('/ws/live')).toBe(true)
  })
})

describe('GlobalWebSocketService heartbeat (#14822)', () => {
  let service: GlobalWebSocketService

  beforeEach(() => {
    vi.useFakeTimers()
    service = new GlobalWebSocketService()
  })

  afterEach(() => {
    service.stopHeartbeat()
    vi.useRealTimers()
  })

  it('pings with an action-shaped frame while the socket is open', () => {
    const sent: Array<Record<string, unknown>> = []
    privates(service).send = (d) => {
      sent.push(d)
      return true
    }
    ;(service as unknown as { ws: { readyState: number } }).ws = { readyState: WebSocket.OPEN }

    service.startHeartbeat()
    vi.advanceTimersByTime(30000)

    expect(sent.some((f) => f.action === 'ping')).toBe(true)
    // The legacy `type`-shaped ping was silently ignored by the channel socket,
    // leaving the heartbeat inert while looking healthy.
    expect(sent.every((f) => !('type' in f))).toBe(true)
  })

  it('stops itself when the socket is no longer open', () => {
    const sent: Array<Record<string, unknown>> = []
    privates(service).send = (d) => {
      sent.push(d)
      return true
    }
    ;(service as unknown as { ws: { readyState: number } | null }).ws = null

    service.startHeartbeat()
    vi.advanceTimersByTime(90000)

    expect(sent).toHaveLength(0)
  })
})

describe('GlobalWebSocketService testConnection (#14822)', () => {
  let service: GlobalWebSocketService

  beforeEach(() => {
    service = new GlobalWebSocketService()
  })

  it('resolves true when a pong arrives, using an action-shaped ping', async () => {
    const sent: Array<Record<string, unknown>> = []
    privates(service).send = (d) => {
      sent.push(d)
      return true
    }
    service.isConnected.value = true

    const pending = service.testConnection()
    expect(sent[0]).toMatchObject({ action: 'ping', test: true })

    service.emit('pong', {})

    await expect(pending).resolves.toBe(true)
  })

  it('reports false when a reconnect attempt fails', async () => {
    // The disconnected branch tries to reconnect first. connect() is stubbed
    // because the real one opens a socket — a test must never depend on the
    // network, and an unstubbed call would hang until the connect timeout.
    service.isConnected.value = false
    ;(service as unknown as { connect: () => Promise<void> }).connect = () =>
      Promise.reject(new Error('no backend'))

    await expect(service.testConnection()).resolves.toBe(false)
  })

  it('reports the connected state after a successful reconnect', async () => {
    service.isConnected.value = false
    ;(service as unknown as { connect: () => Promise<void> }).connect = async () => {
      service.isConnected.value = true
    }

    await expect(service.testConnection()).resolves.toBe(true)
  })
})
