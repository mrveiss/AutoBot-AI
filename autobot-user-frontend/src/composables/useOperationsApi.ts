/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * Vue Composable for Long-Running Operations API
 * Issue #591 - Long-Running Operations Tracker
 */

import { ref, computed, onUnmounted } from 'vue'
import { useApiWithState } from './useApi'
import { createLogger } from '@/utils/debugUtils'
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

const logger = createLogger('useOperationsApi')

/**
 * Composable for long-running operations API calls
 */
export function useOperationsApi() {
  const { api, withErrorHandling } = useApiWithState()

  return {
    /**
     * List all operations with optional filtering
     */
    async listOperations(filter?: OperationsFilter): Promise<OperationsListResponse | null> {
      return withErrorHandling(
        async () => {
          const params = new URLSearchParams()
          if (filter?.status) params.append('status', filter.status)
          if (filter?.operation_type) params.append('operation_type', filter.operation_type)
          if (filter?.limit) params.append('limit', filter.limit.toString())

          const queryString = params.toString()
          const url = `/api/long-running/${queryString ? `?${queryString}` : ''}`
          const response = await api.get(url)
          return await response.json()
        },
        {
          errorMessage: 'Failed to load operations',
          fallbackValue: {
            operations: [],
            total_count: 0,
            active_count: 0,
            completed_count: 0,
            failed_count: 0
          }
        }
      )
    },

    /**
     * Get single operation status
     */
    async getOperation(operationId: string): Promise<Operation | null> {
      return withErrorHandling(
        async () => {
          const response = await api.get(`/api/long-running/${operationId}`)
          return await response.json()
        },
        {
          errorMessage: 'Failed to get operation status',
          fallbackValue: null
        }
      )
    },

    /**
     * Cancel a running operation
     */
    async cancelOperation(operationId: string): Promise<CancelOperationResponse | null> {
      return withErrorHandling(
        async () => {
          const response = await api.post(`/api/long-running/${operationId}/cancel`)
          return await response.json()
        },
        {
          errorMessage: 'Failed to cancel operation'
        }
      )
    },

    /**
     * Resume a failed/paused operation from checkpoint
     */
    async resumeOperation(operationId: string): Promise<ResumeOperationResponse | null> {
      return withErrorHandling(
        async () => {
          const response = await api.post(`/api/long-running/${operationId}/resume`)
          return await response.json()
        },
        {
          errorMessage: 'Failed to resume operation'
        }
      )
    },

    /**
     * Get operations service health status
     */
    async getHealth(): Promise<OperationsHealthResponse | null> {
      return withErrorHandling(
        async () => {
          const response = await api.get('/api/long-running/health')
          return await response.json()
        },
        {
          errorMessage: 'Failed to check operations health',
          fallbackValue: {
            status: 'unavailable',
            active_operations: 0,
            total_operations: 0,
            redis_connected: false,
            background_processor_running: false,
            message: 'Service unavailable'
          },
          silent: true
        }
      )
    }
  }
}

/**
 * Composable with reactive state management for operations
 */
export function useOperationsState() {
  const operationsApi = useOperationsApi()

  // Reactive state
  const operations = ref<Operation[]>([])
  const totalCount = ref(0)
  const activeCount = ref(0)
  const completedCount = ref(0)
  const failedCount = ref(0)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const selectedOperation = ref<Operation | null>(null)
  const healthStatus = ref<OperationsHealthResponse | null>(null)

  // Filter state
  const filter = ref<OperationsFilter>({
    status: undefined,
    operation_type: undefined,
    limit: 50
  })

  // Polling state
  let pollingInterval: ReturnType<typeof setInterval> | null = null
  const isPolling = ref(false)
  const pollingIntervalMs = ref(5000)

  // Computed
  const activeOperations = computed(() =>
    operations.value.filter((op) => op.status === 'running' || op.status === 'pending')
  )

  const completedOperations = computed(() =>
    operations.value.filter((op) => op.status === 'completed')
  )

  const failedOperations = computed(() =>
    operations.value.filter((op) => op.status === 'failed' || op.status === 'timeout')
  )

  const hasActiveOperations = computed(() => activeOperations.value.length > 0)

  const isServiceHealthy = computed(
    () => healthStatus.value?.status === 'healthy'
  )

  /**
   * Load operations list
   */
  async function loadOperations() {
    loading.value = true
    error.value = null

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
      error.value = e instanceof Error ? e.message : 'Unknown error'
      logger.error('Failed to load operations:', e)
    } finally {
      loading.value = false
    }
  }

  /**
   * Refresh single operation
   */
  async function refreshOperation(operationId: string) {
    const result = await operationsApi.getOperation(operationId)
    if (result) {
      // Update in operations list
      const index = operations.value.findIndex((op) => op.operation_id === operationId)
      if (index !== -1) {
        operations.value[index] = result
      }
      // Update selected if matches
      if (selectedOperation.value?.operation_id === operationId) {
        selectedOperation.value = result
      }
    }
    return result
  }

  /**
   * Cancel an operation
   */
  async function cancelOperation(operationId: string) {
    const result = await operationsApi.cancelOperation(operationId)
    if (result) {
      // Refresh the operation to get updated status
      await refreshOperation(operationId)
    }
    return result
  }

  /**
   * Resume an operation
   */
  async function resumeOperation(operationId: string) {
    const result = await operationsApi.resumeOperation(operationId)
    if (result) {
      // Reload all operations as a new one was created
      await loadOperations()
    }
    return result
  }

  /**
   * Check service health
   */
  async function checkHealth() {
    healthStatus.value = await operationsApi.getHealth()
    return healthStatus.value
  }

  /**
   * Set filter and reload
   */
  async function setFilter(newFilter: Partial<OperationsFilter>) {
    filter.value = { ...filter.value, ...newFilter }
    await loadOperations()
  }

  /**
   * Clear filter and reload
   */
  async function clearFilter() {
    filter.value = {
      status: undefined,
      operation_type: undefined,
      limit: 50
    }
    await loadOperations()
  }

  /**
   * Select an operation for detail view
   */
  function selectOperation(operation: Operation | null) {
    selectedOperation.value = operation
  }

  /**
   * Start polling for updates
   */
  function startPolling(intervalMs = 5000) {
    if (pollingInterval) {
      stopPolling()
    }

    pollingIntervalMs.value = intervalMs
    isPolling.value = true

    pollingInterval = setInterval(async () => {
      // Only poll if we have active operations
      if (hasActiveOperations.value) {
        logger.debug('Polling for operation updates...')
        await loadOperations()

        // Check if selected operation needs refresh
        if (selectedOperation.value && !isTerminalStatus(selectedOperation.value.status)) {
          await refreshOperation(selectedOperation.value.operation_id)
        }
      }
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
   * Get operations grouped by status
   */
  function getOperationsByStatus(status: OperationStatus): Operation[] {
    return operations.value.filter((op) => op.status === status)
  }

  // Cleanup on unmount
  onUnmounted(() => {
    stopPolling()
  })

  return {
    // State
    operations,
    totalCount,
    activeCount,
    completedCount,
    failedCount,
    loading,
    error,
    selectedOperation,
    healthStatus,
    filter,
    isPolling,
    pollingIntervalMs,

    // Computed
    activeOperations,
    completedOperations,
    failedOperations,
    hasActiveOperations,
    isServiceHealthy,

    // Methods
    loadOperations,
    refreshOperation,
    cancelOperation,
    resumeOperation,
    checkHealth,
    setFilter,
    clearFilter,
    selectOperation,
    startPolling,
    stopPolling,
    getOperationsByStatus
  }
}
