// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Agent Events Composable (GH#6626)
 *
 * Provides Vue-friendly access to agent lifecycle events, particularly
 * abstention events when an agent cannot confidently complete a task.
 *
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 */

import { onUnmounted, getCurrentInstance } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import liveEventService, { type LiveEvent } from '@/services/LiveEventService'
import { AGENT_ABSTAINED, type AgentAbstainedPayload } from '@/constants/agentEvents'

const logger = createLogger('useAgentEvents')

export interface UseAgentEventsOptions {
  /**
   * Callback invoked when an agent abstains from a task
   */
  onAgentAbstained?: (payload: AgentAbstainedPayload) => void
}

export interface UseAgentEventsReturn {
  /**
   * Subscribe to agent abstention events for a specific task
   */
  subscribeToTaskAbstention: (taskId: string, callback: (payload: AgentAbstainedPayload) => void) => () => void

  /**
   * Subscribe to all agent abstention events on the global channel
   */
  subscribeToGlobalAbstention: (callback: (payload: AgentAbstainedPayload) => void) => () => void
}

/**
 * Composable for handling agent lifecycle events, particularly abstention
 *
 * @param options - Configuration options for event handlers
 * @returns Methods for subscribing to agent events
 */
export function useAgentEvents(options: UseAgentEventsOptions = {}): UseAgentEventsReturn {
  const unsubscribers: Array<() => void> = []

  /**
   * Subscribe to abstention events for a specific task
   */
  const subscribeToTaskAbstention = (
    taskId: string,
    callback: (payload: AgentAbstainedPayload) => void
  ): (() => void) => {
    const channel = `task:${taskId}`

    const handler = (event: LiveEvent) => {
      if (event.event_type === AGENT_ABSTAINED) {
        const payload = event.payload as AgentAbstainedPayload
        logger.info(`Agent abstained on task ${taskId}: ${payload.abstention_reason}`)
        callback(payload)

        // Also invoke global handler if provided
        if (options.onAgentAbstained) {
          options.onAgentAbstained(payload)
        }
      }
    }

    const unsub = liveEventService.subscribe(channel, handler)
    unsubscribers.push(unsub)
    return unsub
  }

  /**
   * Subscribe to all abstention events on the global channel
   */
  const subscribeToGlobalAbstention = (
    callback: (payload: AgentAbstainedPayload) => void
  ): (() => void) => {
    const channel = 'global'

    const handler = (event: LiveEvent) => {
      if (event.event_type === AGENT_ABSTAINED) {
        const payload = event.payload as AgentAbstainedPayload
        logger.info(`Agent abstained on task ${payload.task_id}: ${payload.abstention_reason}`)
        callback(payload)

        // Also invoke global handler if provided
        if (options.onAgentAbstained) {
          options.onAgentAbstained(payload)
        }
      }
    }

    const unsub = liveEventService.subscribe(channel, handler)
    unsubscribers.push(unsub)
    return unsub
  }

  // Cleanup on unmount - only if inside a Vue component
  const instance = getCurrentInstance()
  if (instance) {
    onUnmounted(() => {
      unsubscribers.forEach(unsub => unsub())
      unsubscribers.length = 0
    })
  }

  return {
    subscribeToTaskAbstention,
    subscribeToGlobalAbstention,
  }
}
