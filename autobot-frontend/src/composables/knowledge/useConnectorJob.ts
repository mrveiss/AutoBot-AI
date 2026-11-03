// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
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
/** About a minute of polls for a just-started sync to report its job. */
const FIRST_JOB_WAIT_POLLS = 12

/** Fetch current in-flight job state. Returns null when no job is active (404); any other failure throws. */
export async function fetchConnectorJob(connectorId: string): Promise<ConnectorJobState | null> {
  try {
    return await apiClient.get<ConnectorJobState>(
      `${getApiBase()}/knowledge_base/connectors/${connectorId}/job`
    )
  } catch (err) {
    const e = err as { status?: number; response?: { status?: number } }
    if (e?.status === 404 || e?.response?.status === 404) {
      return null
    }
    throw err
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
  /** True when the last progress request failed; the job's state is then unknown, not "running". */
  const pollFailed = ref(false)
  let timerId: ReturnType<typeof setTimeout> | null = null
  let seenJob = false
  let pollsWithoutJob = 0

  function _clearTimer() {
    if (timerId !== null) {
      clearTimeout(timerId)
      timerId = null
    }
  }

  async function _poll(connectorId: string) {
    if (!isPolling.value) return
    let state: ConnectorJobState | null
    try {
      state = await fetchConnectorJob(connectorId)
    } catch (err) {
      // A failed request is not "no job yet": stop here rather than show Running for a minute.
      logger.error('fetchConnectorJob error', err)
      jobState.value = null
      pollFailed.value = true
      isPolling.value = false
      return
    }
    jobState.value = state

    // #19714: a sync just started writes its job state after change detection, so an early "no job"
    // isn't the end of it. Keep asking for a bounded time, until a job has been seen.
    const waiting = state === null && !seenJob && pollsWithoutJob++ < FIRST_JOB_WAIT_POLLS
    if (state !== null) seenJob = true
    if ((state?.status === 'running' || waiting) && isPolling.value) {
      timerId = setTimeout(() => _poll(connectorId), POLL_INTERVAL_MS)
    } else {
      isPolling.value = false
    }
  }

  function start(connectorId: string) {
    _clearTimer()
    seenJob = false
    pollsWithoutJob = 0
    pollFailed.value = false
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
    pollFailed: readonly(pollFailed),
    start,
    stop,
  }
}
