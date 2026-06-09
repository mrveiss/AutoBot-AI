// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Action Queue Composable
 *
 * Issue #3275: Offline mode — queue outgoing actions that require connectivity
 * and retry automatically when the network is restored.
 *
 * Actions are persisted in localStorage so they survive page refreshes.
 */

import { ref, watch, readonly } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { useNetworkStatus } from '@/composables/useNetworkStatus'

const logger = createLogger('useActionQueue')

const STORAGE_KEY = 'autobot-action-queue'
const MAX_RETRIES = 3

export interface QueuedAction {
  id: string
  type: string
  payload: unknown
  enqueuedAt: number
  retries: number
}

type ActionHandler = (action: QueuedAction) => Promise<void>

// Module-level registry so handlers are shared across composable instances
const _handlers = new Map<string, ActionHandler>()
const _queue = ref<QueuedAction[]>(_loadQueue())
const _isProcessing = ref(false)

function _loadQueue(): QueuedAction[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as QueuedAction[]) : []
  } catch {
    return []
  }
}

function _persistQueue(): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(_queue.value))
  } catch {
    // Storage quota — log and continue; actions are best-effort
    logger.warn('Could not persist action queue to localStorage')
  }
}

async function _processQueue(): Promise<void> {
  if (_isProcessing.value || _queue.value.length === 0) return
  _isProcessing.value = true
  logger.info(`Processing action queue (${_queue.value.length} pending)`)

  // Work on a snapshot so concurrent mutations don't cause issues
  const pending = [..._queue.value]
  for (const action of pending) {
    const handler = _handlers.get(action.type)
    if (!handler) {
      logger.warn(`No handler registered for action type "${action.type}" — dropping`)
      _queue.value = _queue.value.filter((a) => a.id !== action.id)
      _persistQueue()
      continue
    }

    try {
      await handler(action)
      _queue.value = _queue.value.filter((a) => a.id !== action.id)
      _persistQueue()
      logger.debug(`Action ${action.id} (${action.type}) executed successfully`)
    } catch (err) {
      action.retries++
      if (action.retries >= MAX_RETRIES) {
        logger.error(`Action ${action.id} failed after ${MAX_RETRIES} retries — dropping`, err)
        _queue.value = _queue.value.filter((a) => a.id !== action.id)
      } else {
        logger.warn(`Action ${action.id} failed (attempt ${action.retries}), will retry`, err)
        // Update retries count in the reactive queue
        const idx = _queue.value.findIndex((a) => a.id === action.id)
        if (idx !== -1) _queue.value[idx] = { ...action }
      }
      _persistQueue()
    }
  }

  _isProcessing.value = false
}

export function useActionQueue() {
  const { isOnline } = useNetworkStatus()

  // Flush queue whenever we come back online
  watch(isOnline, (online) => {
    if (online) {
      _processQueue()
    }
  })

  /**
   * Register a handler for a given action type.
   * Must be called before any actions of that type are enqueued.
   */
  function registerHandler(type: string, handler: ActionHandler): void {
    _handlers.set(type, handler)
  }

  /**
   * Enqueue an action. If we're online the handler runs immediately;
   * otherwise the action is persisted and replayed when connectivity restores.
   */
  async function enqueue(type: string, payload: unknown): Promise<void> {
    const action: QueuedAction = {
      id: `${type}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      type,
      payload,
      enqueuedAt: Date.now(),
      retries: 0,
    }

    _queue.value = [..._queue.value, action]
    _persistQueue()
    logger.debug(`Action enqueued: ${action.id} (online=${isOnline.value})`)

    if (isOnline.value) {
      await _processQueue()
    }
  }

  /** Remove all queued actions (e.g. on logout) */
  function clearQueue(): void {
    _queue.value = []
    _persistQueue()
  }

  return {
    queue: readonly(_queue),
    isProcessing: readonly(_isProcessing),
    registerHandler,
    enqueue,
    clearQueue,
  }
}
