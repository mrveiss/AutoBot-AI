/**
 * Secrets Audit Log API Composable
 *
 * Issue #3988: Fetch real audit logs from backend instead of using hardcoded mock data
 *
 * Provides API access to security audit logs for secret operations.
 * Handles filtering by operation type, user, and date range.
 */

import { ref } from 'vue'
import { useApiClient } from '@/plugins/api'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'
import { showSubtleErrorNotification } from '@/utils/cacheManagement'
import { useLoadingState } from '@/composables/useLoadingState'

const logger = createLogger('SecretsAuditApi')

export interface AuditLogEntry {
  id: string
  timestamp: string
  operation: string
  user_id: string
  session_id?: string
  vm_name?: string
  resource?: string
  result: 'success' | 'failure'
  details?: string
  ip_address?: string
  metadata?: Record<string, unknown>
}

interface AuditQueryResponse {
  success: boolean
  total_returned: number
  has_more: boolean
  entries: AuditLogEntry[]
  query: Record<string, unknown>
}

export function useSecretsAuditApi() {
  const api = useApiClient()

  const { isLoading: loading, wrap } = useLoadingState()
  const error = ref<string | null>(null)
  const entries = ref<AuditLogEntry[]>([])
  const hasMore = ref(false)
  const totalCount = ref(0)

  const fetchAuditLogs = async (options?: {
    operationFilter?: string
    userIdFilter?: string
    startTime?: string
    endTime?: string
    limit?: number
    offset?: number
  }) => {
    error.value = null

    const params = new URLSearchParams()

    if (options?.operationFilter && options.operationFilter !== 'all') {
      const operationMap: Record<string, string> = {
        'access': 'secrets.access',
        'inject': 'secrets.inject',
        'copy': 'secrets.copy',
        'reveal': 'secrets.reveal',
        'create': 'secrets.create',
        'read': 'secrets.read',
        'update': 'secrets.update',
        'delete': 'secrets.delete'
      }
      const backendOp = operationMap[options.operationFilter] || options.operationFilter
      params.append('operation', backendOp)
    }

    if (options?.userIdFilter && options.userIdFilter !== 'all') {
      params.append('user_id', options.userIdFilter)
    }

    if (options?.startTime) params.append('start_time', options.startTime)
    if (options?.endTime) params.append('end_time', options.endTime)

    const limit = options?.limit ?? 100
    const offset = options?.offset ?? 0
    params.append('limit', String(limit))
    params.append('offset', String(offset))

    return wrap(async () => {
      try {
        const data = await api.get<AuditQueryResponse>(
          `${getApiBase()}/audit/logs?${params.toString()}`
        )

        if (!data.success) {
          throw new Error('Failed to fetch audit logs')
        }

        entries.value = data.entries
        hasMore.value = data.has_more
        totalCount.value = data.total_returned

        return data
      } catch (err: unknown) {
        logger.error('Failed to fetch audit logs', err)
        showSubtleErrorNotification('Error', 'Failed to fetch audit logs', 'error')
        return null
      }
    })
  }

  const clearCache = () => {
    entries.value = []
    hasMore.value = false
    totalCount.value = 0
    error.value = null
  }

  return {
    loading,
    error,
    entries,
    hasMore,
    totalCount,
    fetchAuditLogs,
    clearCache
  }
}
