/**
 * useConnectorJob — live sync job state poller for a single connector.
 *
 * Issue #8149: polls GET /knowledge_base/connectors/{id}/job every 5 s
 * while status is "running".  Stops automatically on terminal status or
 * when the caller calls stop().
 */

import { ref, readonly, onUnmounted } from 'vue'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'
import type { ConnectorJobState, ConnectorLeaderState, ConnectorHistoryEntry } from '@/types/knowledgeBase'

const logger = createLogger('useConnectorJob')

const POLL_INTERVAL_MS = 5_000

/** Fetch current in-flight job state. Returns null when no job is active (404). */
export async function fetchConnectorJob(connectorId: string): Promise<ConnectorJobState | null> {
  try {
    return await apiClient.get<ConnectorJobState>(
      `${getApiBase()}/knowledge_base/connectors/${connectorId}/job`
    )
  } catch (err: any) {
    if (err?.status === 404 || err?.response?.status === 404) {
      return null
    }
    logger.error('fetchConnectorJob error', err)
    return null
  }
}

/** Fetch sync history for a connector. */
export async function fetchConnectorHistory(
  connectorId: string,
  limit = 20
): Promise<ConnectorHistoryEntry[]> {
  const res = await apiClient.get<{ history: ConnectorHistoryEntry[] }>(
    `${getApiBase()}/knowledge_base/connectors/${connectorId}/history?limit=${limit}`
  )
  return res.history ?? []
}

/** Fetch the current scheduler leader worker ID. */
export async function fetchSchedulerLeader(): Promise<string | null> {
  const res = await apiClient.get<ConnectorLeaderState>(
    `${getApiBase()}/knowledge_base/connectors/scheduler/leader`
  )
  return res.leader ?? null
}

/**
 * Composable: reactive job state + auto-poll while running.
 *
 * @example
 * const { jobState, isPolling, start, stop } = useConnectorJob()
 * start('connector-uuid')
 */
export function useConnectorJob() {
  const jobState = ref<ConnectorJobState | null>(null)
  const isPolling = ref(false)
  let timerId: ReturnType<typeof setTimeout> | null = null

  function _clearTimer() {
    if (timerId !== null) {
      clearTimeout(timerId)
      timerId = null
    }
  }

  async function _poll(connectorId: string) {
    if (!isPolling.value) return
    const state = await fetchConnectorJob(connectorId)
    jobState.value = state

    if (state?.status === 'running' && isPolling.value) {
      timerId = setTimeout(() => _poll(connectorId), POLL_INTERVAL_MS)
    } else {
      isPolling.value = false
    }
  }

  function start(connectorId: string) {
    _clearTimer()
    isPolling.value = true
    _poll(connectorId)
  }

  function stop() {
    _clearTimer()
    isPolling.value = false
  }

  onUnmounted(stop)

  return {
    jobState: readonly(jobState),
    isPolling: readonly(isPolling),
    start,
    stop,
  }
}
