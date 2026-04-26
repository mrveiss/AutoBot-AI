// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Composable: useAnalyticsSourceManagement
 *
 * Encapsulates all fetchWithAuth API calls for the SourceManager panel:
 * - fetchSources: GET /api/analytics/codebase/sources
 * - fetchQueueStatus: GET /api/analytics/codebase/index/queue
 * - fetchSourcesForPolling: GET /api/analytics/codebase/sources (polling variant)
 * - fetchQueueStatusForPolling: GET /api/analytics/codebase/index/queue (polling variant)
 * - syncSource: POST /api/analytics/codebase/sources/:id/sync
 * - deleteSource: DELETE /api/analytics/codebase/sources/:id
 * - cancelQueueItem: DELETE /api/analytics/codebase/index/queue/:sourceId
 *
 * Issue #6057: Extract fetchWithAuth calls from SourceManager.vue
 */

import { ref } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
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

async function getBackendUrl(): Promise<string> {
  return appConfig.getServiceUrl('backend')
}

export function useAnalyticsSourceManagement() {
  const isLoadingSources = ref(false)
  const sourcesError = ref<string | null>(null)

  async function fetchSources(): Promise<CodeSource[]> {
    isLoadingSources.value = true
    sourcesError.value = null
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/sources`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      return data.sources ?? []
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      logger.error('Failed to load sources:', msg)
      sourcesError.value = `Failed to load sources: ${msg}`
      throw err
    } finally {
      isLoadingSources.value = false
    }
  }

  async function fetchQueueStatus(): Promise<QueueStatus | null> {
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/index/queue`)
      if (!response.ok) return null
      const data = await response.json()
      return {
        queue_length: data.queue_length ?? 0,
        running: data.running ?? null,
      }
    } catch (err: unknown) {
      logger.warn('Failed to load queue status:', err instanceof Error ? err.message : String(err))
      return null
    }
  }

  async function fetchSourcesForPolling(): Promise<CodeSource[]> {
    const backendUrl = await getBackendUrl()
    const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/sources`)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json()
    return data.sources ?? []
  }

  async function fetchQueueStatusForPolling(): Promise<QueueStatus> {
    const backendUrl = await getBackendUrl()
    const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/index/queue`)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    return response.json()
  }

  async function syncSource(sourceId: string): Promise<void> {
    const backendUrl = await getBackendUrl()
    const response = await fetchWithAuth(
      `${backendUrl}/api/analytics/codebase/sources/${sourceId}/sync`,
      { method: 'POST' }
    )
    if (!response.ok) {
      const text = await response.text()
      throw new Error(`HTTP ${response.status}: ${text}`)
    }
  }

  async function deleteSource(sourceId: string): Promise<void> {
    const backendUrl = await getBackendUrl()
    const response = await fetchWithAuth(
      `${backendUrl}/api/analytics/codebase/sources/${sourceId}`,
      { method: 'DELETE' }
    )
    if (!response.ok) {
      const text = await response.text()
      throw new Error(`HTTP ${response.status}: ${text}`)
    }
  }

  async function cancelQueueItem(sourceId: string): Promise<boolean> {
    const backendUrl = await getBackendUrl()
    const response = await fetchWithAuth(
      `${backendUrl}/api/analytics/codebase/index/queue/${sourceId}`,
      { method: 'DELETE' }
    )
    if (!response.ok) {
      logger.warn('Could not cancel queue item')
      return false
    }
    return true
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
