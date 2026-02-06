/**
 * Service Management Composable
 *
 * Reusable composable for Redis service lifecycle management
 * Provides reactive state, API integration, and WebSocket real-time updates
 */

import { ref, onMounted, onUnmounted } from 'vue'
import { NetworkConstants } from '@/constants/network'
import redisServiceAPI from '@/services/RedisServiceAPI'
import { showSubtleErrorNotification } from '@/utils/cacheManagement'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for useServiceManagement
const logger = createLogger('useServiceManagement')

/**
 * Service management composable
 * @param {string} serviceName - Name of the service (e.g., 'redis')
 * @returns {Object} Service management interface
 */
export function useServiceManagement(serviceName = 'redis') {
  // Reactive state
  const serviceStatus = ref({
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
      ssh_accessible: null
    }
  })

  const healthStatus = ref(null)
  const loading = ref(false)
  const error = ref(null)

  // WebSocket subscription reference
  let wsUnsubscribe = null

  /**
   * Refresh service status and health
   */
  const refreshStatus = async () => {
    try {
      loading.value = true
      error.value = null

      // Fetch both status and health in parallel
      const [statusData, healthData] = await Promise.all([
        redisServiceAPI.getStatus(),
        redisServiceAPI.getHealth()
      ])

      serviceStatus.value = statusData
      healthStatus.value = healthData
    } catch (err) {
      logger.error('Failed to refresh status:', err)
      error.value = err.message || 'Failed to refresh service status'

      showSubtleErrorNotification(
        'Service Status Error',
        'Failed to refresh Redis service status',
        'warning'
      )
    } finally {
      loading.value = false
    }
  }

  /**
   * Start service
   */
  const startService = async () => {
    try {
      loading.value = true
      error.value = null

      const result = await redisServiceAPI.startService()

      if (result.success) {
        // Refresh status after successful start
        await refreshStatus()
        return result
      } else {
        throw new Error(result.message || 'Failed to start service')
      }
    } catch (err) {
      logger.error('Start service failed:', err)
      error.value = err.message || 'Failed to start service'

      showSubtleErrorNotification(
        'Service Start Failed',
        err.message || 'Failed to start Redis service',
        'error'
      )

      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Stop service (requires confirmation)
   */
  const stopService = async (confirmation = true) => {
    try {
      loading.value = true
      error.value = null

      const result = await redisServiceAPI.stopService(confirmation)

      if (result.success) {
        // Refresh status after successful stop
        await refreshStatus()
        return result
      } else {
        throw new Error(result.message || 'Failed to stop service')
      }
    } catch (err) {
      logger.error('Stop service failed:', err)
      error.value = err.message || 'Failed to stop service'

      showSubtleErrorNotification(
        'Service Stop Failed',
        err.message || 'Failed to stop Redis service',
        'error'
      )

      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Restart service
   */
  const restartService = async () => {
    try {
      loading.value = true
      error.value = null

      const result = await redisServiceAPI.restartService()

      if (result.success) {
        // Refresh status after successful restart
        await refreshStatus()
        return result
      } else {
        throw new Error(result.message || 'Failed to restart service')
      }
    } catch (err) {
      logger.error('Restart service failed:', err)
      error.value = err.message || 'Failed to restart service'

      showSubtleErrorNotification(
        'Service Restart Failed',
        err.message || 'Failed to restart Redis service',
        'error'
      )

      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Subscribe to WebSocket status updates
   * @param {Function} callback - Callback function for status updates
   */
  const subscribeToStatusUpdates = (callback) => {
    try {
      // Import WebSocket service dynamically to avoid circular dependencies
      import('@/services/GlobalWebSocketService.js').then((module) => {
        const wsService = module.default

        if (!wsService) {
          logger.warn('WebSocket service not available')
          return
        }

        // Subscribe to service status updates
        const topic = `/ws/services/${serviceName}/status`

        wsUnsubscribe = wsService.subscribe(topic, (message) => {
          try {
            // Handle different message types
            if (message.type === 'service_status') {
              // Update service status from WebSocket
              serviceStatus.value = {
                ...serviceStatus.value,
                ...message.details,
                status: message.status,
                last_check: message.timestamp
              }
            } else if (message.type === 'service_event') {
              // Service operation event (start, stop, restart)

              // Refresh status after operation
              refreshStatus()
            } else if (message.type === 'auto_recovery') {
              // Auto-recovery event

              showSubtleErrorNotification(
                'Auto-Recovery',
                message.message || 'Redis service recovery attempted',
                message.status === 'success' ? 'warning' : 'error'
              )

              // Refresh status after recovery
              refreshStatus()
            }

            // Call user callback if provided
            if (callback) {
              callback(message)
            }
          } catch (err) {
            logger.error('WebSocket message handling error:', err)
          }
        })
      })
    } catch (err) {
      logger.error('Failed to subscribe to WebSocket:', err)
    }
  }

  /**
   * Unsubscribe from WebSocket updates
   */
  const unsubscribeFromUpdates = () => {
    if (wsUnsubscribe) {
      try {
        wsUnsubscribe()
        wsUnsubscribe = null
      } catch (err) {
        logger.error('Failed to unsubscribe from WebSocket:', err)
      }
    }
  }

  // Lifecycle hooks
  onMounted(() => {
    // Initial status fetch
    refreshStatus()
  })

  onUnmounted(() => {
    // Cleanup WebSocket subscriptions
    unsubscribeFromUpdates()
  })

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
    unsubscribeFromUpdates
  }
}
