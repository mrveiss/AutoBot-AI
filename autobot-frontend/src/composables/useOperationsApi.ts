// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * Vue Composable for Long-Running Operations API
 * Issue #591 - Long-Running Operations Tracker
 */

import { ref, computed } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { showSubtleErrorNotification } from '@/utils/cacheManagement'
import { usePollingJob } from '@/composables/usePollingJob'
import { useLoadingState } from '@/composables/useLoadingState'
import type {
  Operation,
  OperationsListResponse,
  OperationsHealthResponse,
  OperationsFilter,
  CancelOperationResponse,
  ResumeOperationResponse,
  OperationStatus
} from '@/types/operations'
import { isTerminalStatus } from '@/types/operations'
import { getApiBase } from '@/config/ssot-config'
import { useProbeBackedHealth, probeStatusToLegacy } from '@/composables/useProbeBackedHealth'

const logger = createLogger('useOperationsApi')

export function useOperationsApi() {
  const api = useApiClient()

  return {
    async listOperations(filter?: OperationsFilter): Promise<OperationsListResponse | null> {
      try {
        const params = new URLSearchParams()
        if (filter?.status) params.append('status', filter.status)
        if (filter?.operation_type) params.append('operation_type', filter.operation_type)
        if (filter?.limit) params.append('limit', filter.limit.toString())
        const queryString = params.toString()
        const url = `${getApiBase()}/long-running/${queryString ? `?${queryString}` : ''}`
        return await api.get<any>(url)
      } catch (error: unknown) {
        logger.error('Failed to load operations', error)
        showSubtleErrorNotification('Error', 'Failed to load operations', 'error')
        return { operations: [], total_count: 0, active_count: 0, completed_count: 0, failed_count: 0 }
      }
    },

    async getOperation(operationId: string): Promise<Operation | null> {
      try {
        return await api.get<any>(`${getApiBase()}/long-running/${operationId}`)
      } catch (error: unknown) {
        logger.error('Failed to get operation status', error)
        showSubtleErrorNotification('Error', 'Failed to get operation status', 'error')
        return null
      }
    },

    async cancelOperation(operationId: string): Promise<CancelOperationResponse | null> {
      try {
        return await api.post<any>(`${getApiBase()}/long-running/${operationId}/cancel`)
      } catch (error: unknown) {
        logger.error('Failed to cancel operation', error)
        showSubtleErrorNotification('Error', 'Failed to cancel operation', 'error')
        return null
      }
    },

    async resumeOperation(operationId: string): Promise<ResumeOperationResponse | null> {
      try {
        return await api.post<any>(`${getApiBase()}/long-running/${operationId}/resume`)
      } catch (error: unknown) {
        logger.error('Failed to resume operation', error)
        showSubtleErrorNotification('Error', 'Failed to resume operation', 'error')
        return null
      }
    },

    /**
     * Get operations service health status.
     *
     * Issue #6902: migrated off the legacy /api/long-running/health (sunset
     * 2026-09-02) onto the canonical aggregator at /api/system/health. The
     * `long_running` probe populates `data` with the four diagnostic fields
     * the UI consumes.
     */
    getHealth: useProbeBackedHealth<OperationsHealthResponse>({
      probeName: 'long_running',
      buildHealthy: (probe, data) => ({
        status: probeStatusToLegacy(probe.status),
        active_operations: Number(data.active_operations ?? 0),
        total_operations: Number(data.total_operations ?? 0),
        redis_connected: Boolean(data.redis_connected),
        background_processor_running: Boolean(data.background_processor_running),
        message: probe.detail,
      }),
      buildUnavailable: (message) => ({
        status: 'unavailable' as const,
        active_operations: 0,
        total_operations: 0,
        redis_connected: false,
        background_processor_running: false,
        message,
      }),
      errorMessage: 'Failed to check operations health',
    }),
  }
}

export function useOperationsState() {
  const operationsApi = useOperationsApi()

  const operations = ref<Operation[]>([])
  const totalCount = ref(0)
  const activeCount = ref(0)
  const completedCount = ref(0)
  const failedCount = ref(0)
  const { isLoading: loading, wrap } = useLoadingState()
  const errors = ref<string[]>([])
  const error = computed<string | null>(() =>
    errors.value.length > 0 ? errors.value.join('; ') : null,
  )
  const selectedOperation = ref<Operation | null>(null)
  const healthStatus = ref<OperationsHealthResponse | null>(null)

  const filter = ref<OperationsFilter>({ status: undefined, operation_type: undefined, limit: 50 })
  const isPolling = ref(false)
  const pollingIntervalMs = ref(5000)

  const activeOperations = computed(() =>
    operations.value.filter((op) => op.status === 'running' || op.status === 'pending')
  )
  const completedOperations = computed(() => operations.value.filter((op) => op.status === 'completed'))
  const failedOperations = computed(() =>
    operations.value.filter((op) => op.status === 'failed' || op.status === 'timeout')
  )
  const hasActiveOperations = computed(() => activeOperations.value.length > 0)
  const isServiceHealthy = computed(() => healthStatus.value?.status === 'healthy')

  async function loadOperations() {
    errors.value = []
    await wrap(async () => {
      try {
        const result = await operationsApi.listOperations(filter.value)
        if (result) {
          operations.value = result.operations
          totalCount.value = result.total_count
          activeCount.value = result.active_count
          completedCount.value = result.completed_count
          failedCount.value = result.failed_count
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Unknown error'
        errors.value = [...errors.value, msg]
        logger.error('Failed to load operations:', e)
      }
    })
  }

  async function refreshOperation(operationId: string) {
    const result = await operationsApi.getOperation(operationId)
    if (result) {
      const index = operations.value.findIndex((op) => op.operation_id === operationId)
      if (index !== -1) operations.value[index] = result
      if (selectedOperation.value?.operation_id === operationId) selectedOperation.value = result
    }
    return result
  }

  async function cancelOperation(operationId: string) {
    const result = await operationsApi.cancelOperation(operationId)
    if (result) await refreshOperation(operationId)
    return result
  }

  async function resumeOperation(operationId: string) {
    const result = await operationsApi.resumeOperation(operationId)
    if (result) await loadOperations()
    return result
  }

  async function checkHealth() {
    healthStatus.value = await operationsApi.getHealth()
    return healthStatus.value
  }

  async function setFilter(newFilter: Partial<OperationsFilter>) {
    filter.value = { ...filter.value, ...newFilter }
    await loadOperations()
  }

  async function clearFilter() {
    filter.value = { status: undefined, operation_type: undefined, limit: 50 }
    await loadOperations()
  }

  function selectOperation(operation: Operation | null) {
    selectedOperation.value = operation
  }

  let _stopOperationsPoller: (() => void) | null = null

  function startPolling(intervalMs = 5000) {
    if (_stopOperationsPoller) _stopOperationsPoller()
    pollingIntervalMs.value = intervalMs
    isPolling.value = true
    logger.debug(`Started polling every ${intervalMs}ms`)
    const poller = usePollingJob<void>(
      async () => {
        if (hasActiveOperations.value) {
          logger.debug('Polling for operation updates...')
          await loadOperations()
          if (selectedOperation.value && !isTerminalStatus(selectedOperation.value.status)) {
            await refreshOperation(selectedOperation.value.operation_id)
          }
        }
      },
      { intervalMs }
    )
    _stopOperationsPoller = poller.stop
    poller.start('')
  }

  function stopPolling() {
    if (_stopOperationsPoller) _stopOperationsPoller()
    _stopOperationsPoller = null
    isPolling.value = false
    logger.debug('Stopped polling')
  }

  function getOperationsByStatus(status: OperationStatus): Operation[] {
    return operations.value.filter((op) => op.status === status)
  }

  // usePollingJob handles cleanup via its own onScopeDispose hook.

  return {
    operations, totalCount, activeCount, completedCount, failedCount,
    loading, error, selectedOperation, healthStatus, filter, isPolling, pollingIntervalMs,
    activeOperations, completedOperations, failedOperations, hasActiveOperations, isServiceHealthy,
    loadOperations, refreshOperation, cancelOperation, resumeOperation, checkHealth,
    setFilter, clearFilter, selectOperation, startPolling, stopPolling, getOperationsByStatus
  }
}
