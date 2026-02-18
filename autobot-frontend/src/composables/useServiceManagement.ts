// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Service Management Composable
 *
 * Reusable composable for Redis service lifecycle management.
 * Provides reactive state, API integration, and WebSocket real-time updates.
 *
 * TypeScript migration of useServiceManagement.js (#819).
 */

import { ref, onMounted, onUnmounted, type Ref } from 'vue'
import { NetworkConstants } from '@/constants/network'
import redisServiceAPI, {
  type ServiceOperationResult,
  type ServiceStatus,
  type ServiceHealth,
} from '@/services/RedisServiceAPI'
import { showSubtleErrorNotification } from '@/utils/cacheManagement'
import { createLogger } from '@/utils/debugUtils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface VmInfo {
  host: string
  name: string
  ssh_accessible: boolean | null
}

interface ExtendedServiceStatus extends ServiceStatus {
  vm_info?: VmInfo
}

/** Shape of messages arriving over the service-status WebSocket topic. */
interface ServiceWsMessage {
  type: string
  status?: string
  details?: Partial<ServiceStatus>
  timestamp?: string
  message?: string
}

type StatusUpdateCallback = (message: ServiceWsMessage) => void

export interface UseServiceManagementReturn {
  // State
  serviceStatus: Ref<ExtendedServiceStatus>
  healthStatus: Ref<ServiceHealth | null>
  loading: Ref<boolean>
  error: Ref<string | null>

  // Actions
  startService: () => Promise<ServiceOperationResult>
  stopService: (confirmation?: boolean) => Promise<ServiceOperationResult>
  restartService: () => Promise<ServiceOperationResult>
  refreshStatus: () => Promise<void>

  // WebSocket
  subscribeToStatusUpdates: (callback?: StatusUpdateCallback) => void
  unsubscribeFromUpdates: () => void
}

// ---------------------------------------------------------------------------
// Logger
// ---------------------------------------------------------------------------

const logger = createLogger('useServiceManagement')

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useServiceManagement(
  serviceName: string = 'redis',
): UseServiceManagementReturn {
  // ---- Reactive state ----

  const serviceStatus = ref<ExtendedServiceStatus>({
    status: 'unknown',
    pid: null,
    uptime_seconds: null,
    memory_mb: null,
    connections: null,
    commands_processed: null,
    last_check: null,
    vm_info: {
      host: NetworkConstants.REDIS_VM_IP,
      name: 'Redis VM',
      ssh_accessible: null,
    },
  })

  const healthStatus = ref<ServiceHealth | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // WebSocket subscription teardown function
  let wsUnsubscribe: (() => void) | null = null

  // ---- Actions ----

  const refreshStatus = async (): Promise<void> => {
    try {
      loading.value = true
      error.value = null

      const [statusData, healthData] = await Promise.all([
        redisServiceAPI.getStatus(),
        redisServiceAPI.getHealth(),
      ])

      serviceStatus.value = statusData as ExtendedServiceStatus
      healthStatus.value = healthData
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      logger.error('Failed to refresh status:', err)
      error.value = msg || 'Failed to refresh service status'

      showSubtleErrorNotification(
        'Service Status Error',
        'Failed to refresh Redis service status',
        'warning',
      )
    } finally {
      loading.value = false
    }
  }

  const startService = async (): Promise<ServiceOperationResult> => {
    try {
      loading.value = true
      error.value = null

      const result = await redisServiceAPI.startService()

      if (result.success) {
        await refreshStatus()
        return result
      }
      throw new Error(result.message || 'Failed to start service')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      logger.error('Start service failed:', err)
      error.value = msg || 'Failed to start service'

      showSubtleErrorNotification(
        'Service Start Failed',
        msg || 'Failed to start Redis service',
        'error',
      )

      throw err
    } finally {
      loading.value = false
    }
  }

  const stopService = async (
    confirmation: boolean = true,
  ): Promise<ServiceOperationResult> => {
    try {
      loading.value = true
      error.value = null

      const result = await redisServiceAPI.stopService(confirmation)

      if (result.success) {
        await refreshStatus()
        return result
      }
      throw new Error(result.message || 'Failed to stop service')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      logger.error('Stop service failed:', err)
      error.value = msg || 'Failed to stop service'

      showSubtleErrorNotification(
        'Service Stop Failed',
        msg || 'Failed to stop Redis service',
        'error',
      )

      throw err
    } finally {
      loading.value = false
    }
  }

  const restartService = async (): Promise<ServiceOperationResult> => {
    try {
      loading.value = true
      error.value = null

      const result = await redisServiceAPI.restartService()

      if (result.success) {
        await refreshStatus()
        return result
      }
      throw new Error(result.message || 'Failed to restart service')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      logger.error('Restart service failed:', err)
      error.value = msg || 'Failed to restart service'

      showSubtleErrorNotification(
        'Service Restart Failed',
        msg || 'Failed to restart Redis service',
        'error',
      )

      throw err
    } finally {
      loading.value = false
    }
  }

  // ---- WebSocket ----

  /**
   * Handle an incoming WebSocket message for this service.
   *
   * Helper for subscribeToStatusUpdates (#819).
   */
  function handleWsMessage(
    message: ServiceWsMessage,
    callback?: StatusUpdateCallback,
  ): void {
    try {
      if (message.type === 'service_status') {
        serviceStatus.value = {
          ...serviceStatus.value,
          ...message.details,
          status: message.status || serviceStatus.value.status,
          last_check: message.timestamp || serviceStatus.value.last_check,
        }
      } else if (message.type === 'service_event') {
        refreshStatus()
      } else if (message.type === 'auto_recovery') {
        showSubtleErrorNotification(
          'Auto-Recovery',
          message.message || 'Redis service recovery attempted',
          message.status === 'success' ? 'warning' : 'error',
        )
        refreshStatus()
      }

      if (callback) {
        callback(message)
      }
    } catch (err: unknown) {
      logger.error('WebSocket message handling error:', err)
    }
  }

  const subscribeToStatusUpdates = (
    callback?: StatusUpdateCallback,
  ): void => {
    try {
      import('@/services/GlobalWebSocketService').then((module) => {
        const wsService = module.default

        if (!wsService) {
          logger.warn('WebSocket service not available')
          return
        }

        const topic = `/ws/services/${serviceName}/status`

        wsUnsubscribe = wsService.subscribe(
          topic,
          (message: unknown) =>
            handleWsMessage(message as ServiceWsMessage, callback),
        )
      })
    } catch (err: unknown) {
      logger.error('Failed to subscribe to WebSocket:', err)
    }
  }

  const unsubscribeFromUpdates = (): void => {
    if (wsUnsubscribe) {
      try {
        wsUnsubscribe()
        wsUnsubscribe = null
      } catch (err: unknown) {
        logger.error('Failed to unsubscribe from WebSocket:', err)
      }
    }
  }

  // ---- Lifecycle hooks ----

  onMounted(() => {
    refreshStatus()
  })

  onUnmounted(() => {
    unsubscribeFromUpdates()
  })

  // ---- Public API ----

  return {
    // State
    serviceStatus,
    healthStatus,
    loading,
    error,

    // Actions
    startService,
    stopService,
    restartService,
    refreshStatus,

    // WebSocket
    subscribeToStatusUpdates,
    unsubscribeFromUpdates,
  }
}
