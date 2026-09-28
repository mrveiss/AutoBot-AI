// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Live canvas cell updates, over the shared event bus (#17020).
 *
 * This opened `/api/canvas/{canvasId}/ws` — a route the backend never served.
 * `api/canvas.py` defines five REST routes and no WebSocket, and the pieces
 * that would have fed such a socket were written and never called:
 * `get_canvas_cell_event` had zero callers, and so did the streaming-task
 * register/unregister pair. `CanvasView` does `onMounted(loadCanvas)` and
 * nothing else, so the canvas loaded once and no agent output or second-tab
 * edit ever reached it. "Live Canvas" was not live.
 *
 * WHY THE BUS AND NOT THE ROUTE THIS FILE ASKED FOR. `EVENT_STATE_DOCTRINE`
 * principle 5 is "channels, not routes" — a new event type extends the channel
 * grammar rather than adding an endpoint — and principle 1 is "one bus", which
 * names three parallel delivery systems as a state this codebase has already
 * been in. Serving the bespoke route would have made a third. The backend now
 * publishes `canvas_cell` on `canvas:{canvasId}`, authorized against the same
 * owner check every REST route on the resource applies.
 *
 * The message handling below is unchanged, including the conflict branch. It
 * was written for exactly this event and was simply never reached.
 */

import { onUnmounted } from 'vue'
import useEventBus, { type LiveEvent } from '@/composables/useEventBus'
import { useCanvasStore } from '@/stores/useCanvasStore'
import { createLogger } from '@/utils/debugUtils'
import type { CanvasWsMessage } from '@/types/canvas'

const logger = createLogger('useCanvasWebSocket')

/** The channel one canvas's events arrive on — mirrors `canvas.events.canvas_channel`. */
export function canvasChannel(canvasId: string): string {
  return `canvas:${canvasId}`
}

export function useCanvasWebSocket(canvasId: string) {
  const store = useCanvasStore()
  const { subscribe, isConnected, connect, disconnect } = useEventBus()

  function handleEvent(event: LiveEvent): void {
    if (event.event_type !== 'canvas_cell') return
    try {
      // The bus delivers the payload already parsed, so the JSON.parse the
      // raw-socket version needed is gone. `type` is no longer inside the
      // payload — the bus carries it as `event_type` — so it is restored here
      // to keep `CanvasWsMessage` and the store's contract unchanged.
      const msg = { ...(event.payload as Omit<CanvasWsMessage, 'type'>), type: 'canvas_cell' } as CanvasWsMessage

      if (store.conflict?.cellId === msg.cellId) {
        store.addCell('agent')
        const newId = store.cells[store.cells.length - 1].id
        store.upsertStreamCell({ ...msg, cellId: newId })
        return
      }

      store.upsertStreamCell(msg)
    } catch (err) {
      logger.error('canvas_cell handling failed', err)
    }
  }

  const unsubscribe = subscribe(canvasChannel(canvasId), handleEvent)

  // The bus is shared, so this composable unsubscribes its own channel rather
  // than disconnecting the socket other views are also using.
  onUnmounted(unsubscribe)

  return { connect, disconnect, isConnected, unsubscribe }
}

export default useCanvasWebSocket
