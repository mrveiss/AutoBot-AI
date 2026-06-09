// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Composable: useAnalyticsSourceManagement
 *
 * Encapsulates all API calls for the SourceManager panel:
 * - fetchSources: GET /api/analytics/codebase/sources
 * - fetchQueueStatus: GET /api/analytics/codebase/index/queue
 * - fetchSourcesForPolling: GET /api/analytics/codebase/sources (polling variant)
 * - fetchQueueStatusForPolling: GET /api/analytics/codebase/index/queue (polling variant)
 * - syncSource: POST /api/analytics/codebase/sources/:id/sync
 * - deleteSource: DELETE /api/analytics/codebase/sources/:id
 * - cancelQueueItem: DELETE /api/analytics/codebase/index/queue/:sourceId
 *
 * Issue #6057: Extract fetchWithAuth calls from SourceManager.vue
 * Migrated from bare fetchWithAuth to useFetchEndpoint (#6152) for GET calls,
 * useApi for POST/DELETE mutations.
 */

import { ref } from 'vue'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import type { CodeSource } from '@/types/analytics'

const logger = createLogger('useAnalyticsSourceManagement')

interface RunningTask {
  task_id: string
  source_id?: string
  started_at?: string
}

interface QueueStatus {
  queue_length: number
  running: RunningTask | null
}

interface SourcesRaw {
  sources?: CodeSource[]
}

interface QueueStatusRaw {
  queue_length?: number
  running?: RunningTask | null
}

export function useAnalyticsSourceManagement() {
  const isLoadingSources = ref(false)
  const sourcesError = ref<string | null>(null)
  const api = useApiClient()

  // ---- Sources endpoint ---------------------------------------------------

  const sourcesEndpoint = useFetchEndpoint<SourcesRaw, CodeSource[]>(
    {
      path: '/api/analytics/codebase/sources',
      pickData: (raw) => raw.sources ?? [],
      onError: (message) => {
        logger.error('Failed to load sources:', message)
        sourcesError.value = `Failed to load sources: ${message}`
      },
      label: 'Sources',
    },
  )

  async function fetchSources(): Promise<CodeSource[]> {
    isLoadingSources.value = true
    sourcesError.value = null
    try {
      await sourcesEndpoint.load()
      if (sourcesEndpoint.error.value) throw new Error(sourcesEndpoint.error.value)
      return sourcesEndpoint.data.value ?? []
    } finally {
      isLoadingSources.value = false
    }
  }

  // ---- Queue status endpoint ----------------------------------------------

  const queueStatusEndpoint = useFetchEndpoint<QueueStatusRaw, QueueStatus>(
    {
      path: '/api/analytics/codebase/index/queue',
      pickData: (raw) => ({
        queue_length: raw.queue_length ?? 0,
        running: raw.running ?? null,
      }),
      onError: (message) => {
        logger.warn('Failed to load queue status:', message)
      },
      fallbackData: () => ({ queue_length: 0, running: null }),
      label: 'Queue status',
    },
  )

  async function fetchQueueStatus(): Promise<QueueStatus | null> {
    try {
      await queueStatusEndpoint.load()
      return queueStatusEndpoint.data.value
    } catch {
      return null
    }
  }

  // ---- Polling variants (separate endpoint instances) --------------------

  const sourcesPollingEndpoint = useFetchEndpoint<SourcesRaw, CodeSource[]>(
    {
      path: '/api/analytics/codebase/sources',
      pickData: (raw) => raw.sources ?? [],
      label: 'Sources (polling)',
    },
  )

  async function fetchSourcesForPolling(): Promise<CodeSource[]> {
    await sourcesPollingEndpoint.load()
    if (sourcesPollingEndpoint.error.value) throw new Error(sourcesPollingEndpoint.error.value)
    return sourcesPollingEndpoint.data.value ?? []
  }

  const queuePollingEndpoint = useFetchEndpoint<QueueStatusRaw, QueueStatus>(
    {
      path: '/api/analytics/codebase/index/queue',
      pickData: (raw) => ({
        queue_length: raw.queue_length ?? 0,
        running: raw.running ?? null,
      }),
      label: 'Queue status (polling)',
    },
  )

  async function fetchQueueStatusForPolling(): Promise<QueueStatus> {
    await queuePollingEndpoint.load()
    if (queuePollingEndpoint.error.value) throw new Error(queuePollingEndpoint.error.value)
    return queuePollingEndpoint.data.value ?? { queue_length: 0, running: null }
  }

  // ---- Mutations (POST/DELETE via useApi) ---------------------------------

  async function syncSource(sourceId: string): Promise<void> {
    await api.post(`/api/analytics/codebase/sources/${sourceId}/sync`)
  }

  async function deleteSource(sourceId: string): Promise<void> {
    await api.delete(`/api/analytics/codebase/sources/${sourceId}`)
  }

  async function cancelQueueItem(sourceId: string): Promise<boolean> {
    try {
      await api.delete(`/api/analytics/codebase/index/queue/${sourceId}`)
      return true
    } catch {
      logger.warn('Could not cancel queue item')
      return false
    }
  }

  return {
    isLoadingSources,
    sourcesError,
    fetchSources,
    fetchQueueStatus,
    fetchSourcesForPolling,
    fetchQueueStatusForPolling,
    syncSource,
    deleteSource,
    cancelQueueItem,
  }
}
