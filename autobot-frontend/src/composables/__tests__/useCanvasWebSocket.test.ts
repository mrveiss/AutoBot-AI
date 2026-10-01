// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The canvas consumer subscribes to a channel the backend publishes on (#17020).
 *
 * It opened `/api/canvas/{canvasId}/ws`, which `api/canvas.py` never served —
 * five REST routes and no WebSocket. So the handler below, conflict branch
 * included, had never run in a browser: `CanvasView` loaded once and received
 * nothing.
 *
 * WHY THESE ASSERT THE CHANNEL NAME AND NOT "A CONNECTION HAPPENS". The old
 * version connected successfully as far as the client could tell — `useWebSocket`
 * with `autoReconnect` retried a 404 forever and the composable reported no
 * error. A test that asserted "it connects" would have passed against the
 * broken version. The channel string is the contract, and it has to match what
 * `canvas.events.canvas_channel` formats on the backend.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

const subscribe = vi.fn()
const unsubscribeFn = vi.fn()

vi.mock('@/composables/useEventBus', () => ({
  default: () => ({
    subscribe,
    unsubscribe: vi.fn(),
    connect: vi.fn(),
    disconnect: vi.fn(),
    isConnected: { value: true },
  }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import { useCanvasWebSocket, canvasChannel } from '../useCanvasWebSocket'
import { useCanvasStore } from '@/stores/useCanvasStore'

type Handler = (event: { event_type: string; payload: Record<string, unknown> }) => void

function cellEvent(overrides: Record<string, unknown> = {}) {
  return {
    event_type: 'canvas_cell',
    payload: { cellId: 'cell-1', canvasId: 'cv-1', seq: 3, delta: 'hello', state: 'streaming', ...overrides },
  }
}

describe('useCanvasWebSocket (#17020)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    subscribe.mockReset()
    unsubscribeFn.mockReset()
    subscribe.mockReturnValue(unsubscribeFn)
  })

  it('subscribes to canvas:{id} and not to a bespoke socket path', () => {
    useCanvasWebSocket('cv-1')

    expect(subscribe).toHaveBeenCalledTimes(1)
    const [channel] = subscribe.mock.calls[0]
    expect(channel).toBe('canvas:cv-1')
    // The route it used to open. If this string ever comes back, the third
    // transport the doctrine forbids has come back with it.
    expect(channel).not.toContain('/ws')
    expect(channel).not.toContain('/api/canvas')
  })

  it('exports the channel formatter so no call site builds the name by hand', () => {
    expect(canvasChannel('cv-9')).toBe('canvas:cv-9')
  })

  it('applies a canvas_cell event to the store', () => {
    const store = useCanvasStore()
    const spy = vi.spyOn(store, 'upsertStreamCell')
    useCanvasWebSocket('cv-1')
    const handler = subscribe.mock.calls[0][1] as Handler

    handler(cellEvent())

    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({ cellId: 'cell-1', seq: 3, delta: 'hello', state: 'streaming' }),
    )
  })

  it('restores the type field the bus carries separately', () => {
    // The raw socket put `type` inside the message; the bus carries it as
    // `event_type`. `CanvasWsMessage` and the store's contract are unchanged,
    // so the composable has to put it back.
    const store = useCanvasStore()
    const spy = vi.spyOn(store, 'upsertStreamCell')
    useCanvasWebSocket('cv-1')
    const handler = subscribe.mock.calls[0][1] as Handler

    handler(cellEvent())

    expect(spy).toHaveBeenCalledWith(expect.objectContaining({ type: 'canvas_cell' }))
  })

  it('ignores an event type it does not handle', () => {
    // Negative control: the channel carries whatever else is published to it,
    // and without this the assertions above are satisfied by a handler that
    // forwards everything.
    const store = useCanvasStore()
    const spy = vi.spyOn(store, 'upsertStreamCell')
    useCanvasWebSocket('cv-1')
    const handler = subscribe.mock.calls[0][1] as Handler

    handler({ event_type: 'workflow_completed', payload: { cellId: 'cell-1' } })

    expect(spy).not.toHaveBeenCalled()
  })

  it('routes a conflicting cell to a new agent cell instead of overwriting', () => {
    // The branch that had never executed. A delta for the cell the user is
    // resolving must not land on top of their edit.
    const store = useCanvasStore()
    store.addCell('user')
    const conflictedId = store.cells[store.cells.length - 1].id
    store.conflict = { cellId: conflictedId, pausedAgentSeq: 2 }
    const spy = vi.spyOn(store, 'upsertStreamCell')

    useCanvasWebSocket('cv-1')
    const handler = subscribe.mock.calls[0][1] as Handler
    handler(cellEvent({ cellId: conflictedId }))

    expect(spy).toHaveBeenCalledTimes(1)
    const [applied] = spy.mock.calls[0] as [{ cellId: string }]
    expect(applied.cellId).not.toBe(conflictedId)
  })

  it('returns its unsubscribe rather than disconnecting the shared bus', () => {
    // The bus is shared with every other live view, so tearing down this
    // composable must not close the socket the workflow dashboard is using.
    const api = useCanvasWebSocket('cv-1')

    expect(api.unsubscribe).toBe(unsubscribeFn)
  })
})
