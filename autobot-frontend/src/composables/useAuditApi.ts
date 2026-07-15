// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * Vue Composable for Audit Logging API
 * Issue #578 - Audit Logging Dashboard GUI Integration
 */

import { ref, computed } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { showSubtleErrorNotification } from '@/utils/cacheManagement'
import { usePollingJob } from '@/composables/usePollingJob'
import { useLoadingState } from '@/composables/useLoadingState'
import type {
  AuditEntry,
  AuditQueryParams,
  AuditQueryResponse,
  AuditStatisticsResponse,
  AuditStatistics,
  AuditCleanupRequest,
  AuditCleanupResponse,
  AuditOperationsResponse,
  AuditFilter,
  AuditResult
} from '@/types/audit'
import { DEFAULT_AUDIT_FILTER, getDateRangeForFilter } from '@/types/audit'
import { getApiBase } from '@/config/ssot-config'

const logger = createLogger('useAuditApi')

export function useAuditApi() {
  const api = useApiClient()

  return {
    async queryLogs(params?: AuditQueryParams): Promise<AuditQueryResponse | null> {
      try {
        const searchParams = new URLSearchParams()
        if (params?.start_time) searchParams.append('start_time', params.start_time)
        if (params?.end_time) searchParams.append('end_time', params.end_time)
        if (params?.operation) searchParams.append('operation', params.operation)
        if (params?.user_id) searchParams.append('user_id', params.user_id)
        if (params?.session_id) searchParams.append('session_id', params.session_id)
        if (params?.vm_name) searchParams.append('vm_name', params.vm_name)
        if (params?.result) searchParams.append('result', params.result)
        if (params?.limit) searchParams.append('limit', params.limit.toString())
        if (params?.offset) searchParams.append('offset', params.offset.toString())
        const queryString = searchParams.toString()
        const url = `${getApiBase()}/audit/logs${queryString ? `?${queryString}` : ''}`
        return await api.get<AuditQueryResponse>(url)
      } catch (error: unknown) {
        logger.error('Failed to load audit logs', error)
        showSubtleErrorNotification('Error', 'Failed to load audit logs', 'error')
        return { success: false, total_returned: 0, has_more: false, entries: [], query: {} }
      }
    },

    async getStatistics(): Promise<AuditStatisticsResponse | null> {
      try {
        return await api.get<AuditStatisticsResponse>(`${getApiBase()}/audit/statistics`)
      } catch (error: unknown) {
        logger.error('Failed to load audit statistics', error)
        showSubtleErrorNotification('Error', 'Failed to load audit statistics', 'error')
        return null
      }
    },

    async getSessionAuditTrail(sessionId: string): Promise<AuditQueryResponse | null> {
      try {
        return await api.get<AuditQueryResponse>(`${getApiBase()}/audit/session/${sessionId}`)
      } catch (error: unknown) {
        logger.error('Failed to load session audit trail', error)
        showSubtleErrorNotification('Error', 'Failed to load session audit trail', 'error')
        return null
      }
    },

    async getUserAuditTrail(userId: string, days: number = 7): Promise<AuditQueryResponse | null> {
      try {
        return await api.get<AuditQueryResponse>(`${getApiBase()}/audit/user/${userId}?days=${days}`)
      } catch (error: unknown) {
        logger.error('Failed to load user audit trail', error)
        showSubtleErrorNotification('Error', 'Failed to load user audit trail', 'error')
        return null
      }
    },

    async getFailedOperations(hours: number = 24, resultFilter: AuditResult = 'denied'): Promise<AuditQueryResponse | null> {
      try {
        return await api.get<AuditQueryResponse>(
          `${getApiBase()}/audit/failures?hours=${hours}&result_filter=${resultFilter}`
        )
      } catch (error: unknown) {
        logger.error('Failed to load failed operations', error)
        showSubtleErrorNotification('Error', 'Failed to load failed operations', 'error')
        return null
      }
    },

    async cleanupLogs(request: AuditCleanupRequest): Promise<AuditCleanupResponse | null> {
      try {
        return await api.post<AuditCleanupResponse>(`${getApiBase()}/audit/cleanup`, request)
      } catch (error: unknown) {
        logger.error('Failed to cleanup audit logs', error)
        showSubtleErrorNotification('Error', 'Failed to cleanup audit logs', 'error')
        return null
      }
    },

    async getOperationTypes(): Promise<AuditOperationsResponse | null> {
      try {
        return await api.get<AuditOperationsResponse>(`${getApiBase()}/audit/operations`)
      } catch (error: unknown) {
        logger.error('Failed to load operation types', error)
        showSubtleErrorNotification('Error', 'Failed to load operation types', 'error')
        return { success: false, categories: {}, total_operations: 0 }
      }
    }
  }
}

export function useAuditState() {
  const auditApi = useAuditApi()

  const entries = ref<AuditEntry[]>([])
  const statistics = ref<AuditStatistics | null>(null)
  const vmInfo = ref<{ vm_source: string; vm_name: string } | null>(null)
  const operationCategories = ref<Record<string, string[]>>({})
  const totalOperations = ref(0)
  const { isLoading: loading, wrap } = useLoadingState()
  const { isLoading: loadingStats, wrap: wrapStats } = useLoadingState()
  const { isLoading: loadingTrail, wrap: wrapTrail } = useLoadingState()
  const error = ref<string | null>(null)
  const hasMore = ref(false)
  const totalReturned = ref(0)

  const filter = ref<AuditFilter>({ ...DEFAULT_AUDIT_FILTER })
  const currentPage = ref(1)
  const pageSize = ref(100)
  const isPolling = ref(false)
  const pollingIntervalMs = ref(30000)
  const selectedEntry = ref<AuditEntry | null>(null)
  const selectedSessionId = ref<string | null>(null)
  const selectedUserId = ref<string | null>(null)
  const sessionTrail = ref<AuditEntry[]>([])
  const userTrail = ref<AuditEntry[]>([])

  const successEntries = computed(() => entries.value.filter((e) => e.result === 'success'))
  const failedEntries = computed(() => entries.value.filter((e) => e.result !== 'success'))
  const deniedEntries = computed(() => entries.value.filter((e) => e.result === 'denied'))

  const successRate = computed(() => {
    if (statistics.value) return statistics.value.success_rate
    if (entries.value.length === 0) return 0
    return Math.round((successEntries.value.length / entries.value.length) * 100)
  })

  const uniqueOperations = computed(() => {
    const ops = new Set(entries.value.map((e) => e.operation))
    return Array.from(ops).sort()
  })

  const uniqueUsers = computed(() => {
    const users = new Set(entries.value.map((e) => e.user_id).filter(Boolean))
    return Array.from(users).sort() as string[]
  })

  function buildQueryParams(): AuditQueryParams {
    const params: AuditQueryParams = {
      limit: filter.value.limit,
      offset: (currentPage.value - 1) * pageSize.value
    }
    if (filter.value.dateRange === 'custom') {
      if (filter.value.startDate) params.start_time = filter.value.startDate
      if (filter.value.endDate) params.end_time = filter.value.endDate
    } else {
      const { start, end } = getDateRangeForFilter(filter.value.dateRange)
      params.start_time = start.toISOString()
      params.end_time = end.toISOString()
    }
    if (filter.value.operation) params.operation = filter.value.operation
    if (filter.value.userId) params.user_id = filter.value.userId
    if (filter.value.sessionId) params.session_id = filter.value.sessionId
    if (filter.value.vmName) params.vm_name = filter.value.vmName
    if (filter.value.result) params.result = filter.value.result
    return params
  }

  async function loadLogs() {
    error.value = null
    await wrap(async () => {
      try {
        const params = buildQueryParams()
        const result = await auditApi.queryLogs(params)
        if (result && result.success) {
          entries.value = result.entries
          hasMore.value = result.has_more
          totalReturned.value = result.total_returned
        }
      } catch (e) {
        error.value = e instanceof Error ? e.message : 'Unknown error'
        logger.error('Failed to load audit logs:', e)
      }
    })
  }

  async function loadStatistics() {
    await wrapStats(async () => {
      try {
        const result = await auditApi.getStatistics()
        if (result && result.success) {
          statistics.value = result.statistics
          vmInfo.value = result.vm_info
        }
      } catch (e) {
        logger.error('Failed to load audit statistics:', e)
      }
    })
  }

  async function loadOperationCategories() {
    try {
      const result = await auditApi.getOperationTypes()
      if (result && result.success) {
        operationCategories.value = result.categories
        totalOperations.value = result.total_operations
      }
    } catch (e) {
      logger.error('Failed to load operation categories:', e)
    }
  }

  async function loadSessionTrail(sessionId: string) {
    selectedSessionId.value = sessionId
    await wrapTrail(async () => {
      try {
        const result = await auditApi.getSessionAuditTrail(sessionId)
        if (result && result.success) {
          sessionTrail.value = result.entries
        }
      } catch (e) {
        logger.error('Failed to load session trail:', e)
      }
    })
  }

  async function loadUserTrail(userId: string, days: number = 7) {
    selectedUserId.value = userId
    await wrapTrail(async () => {
      try {
        const result = await auditApi.getUserAuditTrail(userId, days)
        if (result && result.success) {
          userTrail.value = result.entries
        }
      } catch (e) {
        logger.error('Failed to load user trail:', e)
      }
    })
  }

  async function loadFailedOperations(hours: number = 24) {
    await wrap(async () => {
      try {
        const result = await auditApi.getFailedOperations(hours)
        if (result && result.success) {
          entries.value = result.entries
          totalReturned.value = result.total_returned
        }
      } catch (e) {
        logger.error('Failed to load failed operations:', e)
      }
    })
  }

  async function cleanupLogs(daysToKeep: number, confirm: boolean = false) {
    if (!confirm) {
      return { success: false, message: 'Confirmation required' }
    }
    try {
      const result = await auditApi.cleanupLogs({ days_to_keep: daysToKeep, confirm: true })
      if (result && result.success) {
        await loadLogs()
        await loadStatistics()
      }
      return result
    } catch (e) {
      logger.error('Failed to cleanup logs:', e)
      return { success: false, message: 'Cleanup failed' }
    }
  }

  async function setFilter(newFilter: Partial<AuditFilter>) {
    filter.value = { ...filter.value, ...newFilter }
    currentPage.value = 1
    await loadLogs()
  }

  async function resetFilter() {
    filter.value = { ...DEFAULT_AUDIT_FILTER }
    currentPage.value = 1
    await loadLogs()
  }

  async function nextPage() {
    if (hasMore.value) {
      currentPage.value++
      await loadLogs()
    }
  }

  async function prevPage() {
    if (currentPage.value > 1) {
      currentPage.value--
      await loadLogs()
    }
  }

  function selectEntry(entry: AuditEntry | null) {
    selectedEntry.value = entry
  }

  let _stopAuditPoller: (() => void) | null = null

  function startPolling(intervalMs = 30000) {
    if (_stopAuditPoller) _stopAuditPoller()
    pollingIntervalMs.value = intervalMs
    isPolling.value = true
    logger.debug(`Started polling every ${intervalMs}ms`)
    const poller = usePollingJob<void>(
      async () => {
        logger.debug('Polling for audit log updates...')
        await loadLogs()
        await loadStatistics()
      },
      { intervalMs }
    )
    _stopAuditPoller = poller.stop
    poller.start('')
  }

  function stopPolling() {
    if (_stopAuditPoller) _stopAuditPoller()
    _stopAuditPoller = null
    isPolling.value = false
    logger.debug('Stopped polling')
  }

  async function initialize() {
    await Promise.all([loadLogs(), loadStatistics(), loadOperationCategories()])
  }

  function exportToJson(): string {
    return JSON.stringify(entries.value, null, 2)
  }

  function escapeCsvField(field: string | null | undefined): string {
    if (!field) return '""'
    let escaped = field
    if (/^[=+\-@]/.test(escaped)) {
      escaped = "'" + escaped
    }
    if (/[",\n\r]/.test(escaped)) {
      return '"' + escaped.replace(/"/g, '""') + '"'
    }
    return escaped
  }

  function exportToCsv(): string {
    const headers = ['Timestamp', 'Operation', 'Result', 'User ID', 'Session ID', 'VM Name', 'IP Address', 'Error Message']
    const rows = entries.value.map((entry) => [
      escapeCsvField(entry.timestamp),
      escapeCsvField(entry.operation),
      escapeCsvField(entry.result),
      escapeCsvField(entry.user_id),
      escapeCsvField(entry.session_id),
      escapeCsvField(entry.vm_name),
      escapeCsvField(entry.ip_address),
      escapeCsvField(entry.error_message)
    ])
    return [headers.join(','), ...rows.map((row) => row.join(','))].join('\n')
  }

  function downloadExport(format: 'json' | 'csv') {
    const content = format === 'json' ? exportToJson() : exportToCsv()
    const mimeType = format === 'json' ? 'application/json' : 'text/csv'
    const filename = `audit-logs-${new Date().toISOString().split('T')[0]}.${format}`
    const blob = new Blob([content], { type: mimeType })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  // usePollingJob handles cleanup via its own onScopeDispose hook.

  return {
    entries, statistics, vmInfo, operationCategories, totalOperations,
    loading, loadingStats, error, hasMore, totalReturned,
    filter, currentPage, pageSize, isPolling, pollingIntervalMs,
    selectedEntry, selectedSessionId, selectedUserId, sessionTrail, userTrail, loadingTrail,
    successEntries, failedEntries, deniedEntries, successRate, uniqueOperations, uniqueUsers,
    loadLogs, loadStatistics, loadOperationCategories, loadSessionTrail, loadUserTrail,
    loadFailedOperations, cleanupLogs, setFilter, resetFilter, nextPage, prevPage,
    selectEntry, startPolling, stopPolling, initialize, exportToJson, exportToCsv, downloadExport
  }
}
