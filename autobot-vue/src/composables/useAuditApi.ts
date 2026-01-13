/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * Vue Composable for Audit Logging API
 * Issue #578 - Audit Logging Dashboard GUI Integration
 */

import { ref, computed, onUnmounted } from 'vue'
import { useApiWithState } from './useApi'
import { createLogger } from '@/utils/debugUtils'
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

const logger = createLogger('useAuditApi')

/**
 * Composable for audit logging API calls
 */
export function useAuditApi() {
  const { api, withErrorHandling } = useApiWithState()

  return {
    /**
     * Query audit logs with filters
     */
    async queryLogs(params?: AuditQueryParams): Promise<AuditQueryResponse | null> {
      return withErrorHandling(
        async () => {
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
          const url = `/api/audit/logs${queryString ? `?${queryString}` : ''}`
          const response = await api.get(url)
          return await response.json()
        },
        {
          errorMessage: 'Failed to load audit logs',
          fallbackValue: {
            success: false,
            total_returned: 0,
            has_more: false,
            entries: [],
            query: {}
          }
        }
      )
    },

    /**
     * Get audit statistics
     */
    async getStatistics(): Promise<AuditStatisticsResponse | null> {
      return withErrorHandling(
        async () => {
          const response = await api.get('/api/audit/statistics')
          return await response.json()
        },
        {
          errorMessage: 'Failed to load audit statistics',
          fallbackValue: null
        }
      )
    },

    /**
     * Get session audit trail
     */
    async getSessionAuditTrail(sessionId: string): Promise<AuditQueryResponse | null> {
      return withErrorHandling(
        async () => {
          const response = await api.get(`/api/audit/session/${sessionId}`)
          return await response.json()
        },
        {
          errorMessage: 'Failed to load session audit trail',
          fallbackValue: null
        }
      )
    },

    /**
     * Get user audit trail
     */
    async getUserAuditTrail(
      userId: string,
      days: number = 7
    ): Promise<AuditQueryResponse | null> {
      return withErrorHandling(
        async () => {
          const response = await api.get(`/api/audit/user/${userId}?days=${days}`)
          return await response.json()
        },
        {
          errorMessage: 'Failed to load user audit trail',
          fallbackValue: null
        }
      )
    },

    /**
     * Get failed operations
     */
    async getFailedOperations(
      hours: number = 24,
      resultFilter: AuditResult = 'denied'
    ): Promise<AuditQueryResponse | null> {
      return withErrorHandling(
        async () => {
          const response = await api.get(
            `/api/audit/failures?hours=${hours}&result_filter=${resultFilter}`
          )
          return await response.json()
        },
        {
          errorMessage: 'Failed to load failed operations',
          fallbackValue: null
        }
      )
    },

    /**
     * Cleanup old audit logs
     */
    async cleanupLogs(request: AuditCleanupRequest): Promise<AuditCleanupResponse | null> {
      return withErrorHandling(
        async () => {
          const response = await api.post('/api/audit/cleanup', request)
          return await response.json()
        },
        {
          errorMessage: 'Failed to cleanup audit logs'
        }
      )
    },

    /**
     * Get available operation types
     */
    async getOperationTypes(): Promise<AuditOperationsResponse | null> {
      return withErrorHandling(
        async () => {
          const response = await api.get('/api/audit/operations')
          return await response.json()
        },
        {
          errorMessage: 'Failed to load operation types',
          fallbackValue: {
            success: false,
            categories: {},
            total_operations: 0
          }
        }
      )
    }
  }
}

/**
 * Composable with reactive state management for audit logs
 */
export function useAuditState() {
  const auditApi = useAuditApi()

  // Reactive state
  const entries = ref<AuditEntry[]>([])
  const statistics = ref<AuditStatistics | null>(null)
  const vmInfo = ref<{ vm_source: string; vm_name: string } | null>(null)
  const operationCategories = ref<Record<string, string[]>>({})
  const totalOperations = ref(0)
  const loading = ref(false)
  const loadingStats = ref(false)
  const error = ref<string | null>(null)
  const hasMore = ref(false)
  const totalReturned = ref(0)

  // Filter state
  const filter = ref<AuditFilter>({ ...DEFAULT_AUDIT_FILTER })

  // Pagination
  const currentPage = ref(1)
  const pageSize = ref(100)

  // Polling state
  let pollingInterval: ReturnType<typeof setInterval> | null = null
  const isPolling = ref(false)
  const pollingIntervalMs = ref(30000)

  // Selected entries for detail view
  const selectedEntry = ref<AuditEntry | null>(null)
  const selectedSessionId = ref<string | null>(null)
  const selectedUserId = ref<string | null>(null)

  // Session/User trail data
  const sessionTrail = ref<AuditEntry[]>([])
  const userTrail = ref<AuditEntry[]>([])
  const loadingTrail = ref(false)

  // Computed
  const successEntries = computed(() =>
    entries.value.filter((e) => e.result === 'success')
  )

  const failedEntries = computed(() =>
    entries.value.filter((e) => e.result !== 'success')
  )

  const deniedEntries = computed(() =>
    entries.value.filter((e) => e.result === 'denied')
  )

  const successRate = computed(() => {
    if (statistics.value) {
      return statistics.value.success_rate
    }
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

  /**
   * Build query params from filter state
   */
  function buildQueryParams(): AuditQueryParams {
    const params: AuditQueryParams = {
      limit: filter.value.limit,
      offset: (currentPage.value - 1) * pageSize.value
    }

    // Date range
    if (filter.value.dateRange === 'custom') {
      if (filter.value.startDate) params.start_time = filter.value.startDate
      if (filter.value.endDate) params.end_time = filter.value.endDate
    } else {
      const { start, end } = getDateRangeForFilter(filter.value.dateRange)
      params.start_time = start.toISOString()
      params.end_time = end.toISOString()
    }

    // Other filters
    if (filter.value.operation) params.operation = filter.value.operation
    if (filter.value.userId) params.user_id = filter.value.userId
    if (filter.value.sessionId) params.session_id = filter.value.sessionId
    if (filter.value.vmName) params.vm_name = filter.value.vmName
    if (filter.value.result) params.result = filter.value.result

    return params
  }

  /**
   * Load audit logs with current filter
   */
  async function loadLogs() {
    loading.value = true
    error.value = null

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
    } finally {
      loading.value = false
    }
  }

  /**
   * Load audit statistics
   */
  async function loadStatistics() {
    loadingStats.value = true

    try {
      const result = await auditApi.getStatistics()
      if (result && result.success) {
        statistics.value = result.statistics
        vmInfo.value = result.vm_info
      }
    } catch (e) {
      logger.error('Failed to load audit statistics:', e)
    } finally {
      loadingStats.value = false
    }
  }

  /**
   * Load operation categories
   */
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

  /**
   * Load session audit trail
   */
  async function loadSessionTrail(sessionId: string) {
    selectedSessionId.value = sessionId
    loadingTrail.value = true

    try {
      const result = await auditApi.getSessionAuditTrail(sessionId)
      if (result && result.success) {
        sessionTrail.value = result.entries
      }
    } catch (e) {
      logger.error('Failed to load session trail:', e)
    } finally {
      loadingTrail.value = false
    }
  }

  /**
   * Load user audit trail
   */
  async function loadUserTrail(userId: string, days: number = 7) {
    selectedUserId.value = userId
    loadingTrail.value = true

    try {
      const result = await auditApi.getUserAuditTrail(userId, days)
      if (result && result.success) {
        userTrail.value = result.entries
      }
    } catch (e) {
      logger.error('Failed to load user trail:', e)
    } finally {
      loadingTrail.value = false
    }
  }

  /**
   * Load failed operations for security monitoring
   */
  async function loadFailedOperations(hours: number = 24) {
    loading.value = true

    try {
      const result = await auditApi.getFailedOperations(hours)
      if (result && result.success) {
        entries.value = result.entries
        totalReturned.value = result.total_returned
      }
    } catch (e) {
      logger.error('Failed to load failed operations:', e)
    } finally {
      loading.value = false
    }
  }

  /**
   * Cleanup old audit logs
   */
  async function cleanupLogs(daysToKeep: number, confirm: boolean = false) {
    if (!confirm) {
      return { success: false, message: 'Confirmation required' }
    }

    try {
      const result = await auditApi.cleanupLogs({
        days_to_keep: daysToKeep,
        confirm: true
      })
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

  /**
   * Update filter and reload
   */
  async function setFilter(newFilter: Partial<AuditFilter>) {
    filter.value = { ...filter.value, ...newFilter }
    currentPage.value = 1
    await loadLogs()
  }

  /**
   * Reset filter to defaults
   */
  async function resetFilter() {
    filter.value = { ...DEFAULT_AUDIT_FILTER }
    currentPage.value = 1
    await loadLogs()
  }

  /**
   * Go to next page
   */
  async function nextPage() {
    if (hasMore.value) {
      currentPage.value++
      await loadLogs()
    }
  }

  /**
   * Go to previous page
   */
  async function prevPage() {
    if (currentPage.value > 1) {
      currentPage.value--
      await loadLogs()
    }
  }

  /**
   * Select entry for detail view
   */
  function selectEntry(entry: AuditEntry | null) {
    selectedEntry.value = entry
  }

  /**
   * Start polling for updates
   */
  function startPolling(intervalMs = 30000) {
    if (pollingInterval) {
      stopPolling()
    }

    pollingIntervalMs.value = intervalMs
    isPolling.value = true

    pollingInterval = setInterval(async () => {
      logger.debug('Polling for audit log updates...')
      await loadLogs()
      await loadStatistics()
    }, intervalMs)

    logger.debug(`Started polling every ${intervalMs}ms`)
  }

  /**
   * Stop polling
   */
  function stopPolling() {
    if (pollingInterval) {
      clearInterval(pollingInterval)
      pollingInterval = null
    }
    isPolling.value = false
    logger.debug('Stopped polling')
  }

  /**
   * Initialize - load all data
   */
  async function initialize() {
    await Promise.all([loadLogs(), loadStatistics(), loadOperationCategories()])
  }

  /**
   * Export logs to JSON
   */
  function exportToJson(): string {
    return JSON.stringify(entries.value, null, 2)
  }

  /**
   * Escape CSV field to prevent formula injection and handle special characters
   * Issue #578: Security fix for CSV export
   */
  function escapeCsvField(field: string | null | undefined): string {
    if (!field) return '""'
    let escaped = field
    // Escape fields that could be interpreted as formulas in Excel
    if (/^[=+\-@]/.test(escaped)) {
      escaped = "'" + escaped
    }
    // Quote fields containing special characters
    if (/[",\n\r]/.test(escaped)) {
      return '"' + escaped.replace(/"/g, '""') + '"'
    }
    return escaped
  }

  /**
   * Export logs to CSV
   */
  function exportToCsv(): string {
    const headers = [
      'Timestamp',
      'Operation',
      'Result',
      'User ID',
      'Session ID',
      'VM Name',
      'IP Address',
      'Error Message'
    ]

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

    const csvContent = [headers.join(','), ...rows.map((row) => row.join(','))].join(
      '\n'
    )

    return csvContent
  }

  /**
   * Download export file
   */
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

  // Cleanup on unmount
  onUnmounted(() => {
    stopPolling()
  })

  return {
    // State
    entries,
    statistics,
    vmInfo,
    operationCategories,
    totalOperations,
    loading,
    loadingStats,
    error,
    hasMore,
    totalReturned,
    filter,
    currentPage,
    pageSize,
    isPolling,
    pollingIntervalMs,
    selectedEntry,
    selectedSessionId,
    selectedUserId,
    sessionTrail,
    userTrail,
    loadingTrail,

    // Computed
    successEntries,
    failedEntries,
    deniedEntries,
    successRate,
    uniqueOperations,
    uniqueUsers,

    // Methods
    loadLogs,
    loadStatistics,
    loadOperationCategories,
    loadSessionTrail,
    loadUserTrail,
    loadFailedOperations,
    cleanupLogs,
    setFilter,
    resetFilter,
    nextPage,
    prevPage,
    selectEntry,
    startPolling,
    stopPolling,
    initialize,
    exportToJson,
    exportToCsv,
    downloadExport
  }
}
