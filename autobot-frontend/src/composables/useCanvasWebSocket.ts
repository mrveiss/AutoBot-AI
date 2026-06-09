// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { useWebSocket } from '@/composables/useWebSocket'
import { useCanvasStore } from '@/stores/useCanvasStore'
import { getBackendUrl } from '@/config/ssot-config'
import type { CanvasWsMessage } from '@/types/canvas'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useCanvasWebSocket')

export function useCanvasWebSocket(canvasId: string) {
  const store = useCanvasStore()
  const wsUrl = `${getBackendUrl().replace(/^http/, 'ws')}/api/canvas/${canvasId}/ws`

  function handleMessage(data: unknown) {
    try {
      const msg = JSON.parse(data as string) as CanvasWsMessage
      if (msg.type !== 'canvas_cell') return

      if (store.conflict?.cellId === msg.cellId) {
        store.addCell('agent')
        const newId = store.cells[store.cells.length - 1].id
        store.upsertStreamCell({ ...msg, cellId: newId })
        return
      }

      store.upsertStreamCell(msg)
    } catch (err) {
      logger.error('WS parse error', err)
    }
  }

  const { connect, disconnect, isConnected } = useWebSocket(wsUrl, {
    autoConnect: true,
    autoReconnect: true,
    onMessage: handleMessage,
  })

  return { connect, disconnect, isConnected }
}
