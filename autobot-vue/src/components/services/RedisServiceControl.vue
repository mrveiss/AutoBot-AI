<template>
  <div class="redis-service-control bg-white rounded-lg shadow-md overflow-hidden">
    <!-- Service Header -->
    <div class="flex items-center justify-between px-6 py-4 border-b bg-gradient-to-r from-red-50 to-red-100">
      <div class="flex items-center space-x-3">
        <i class="fas fa-database text-2xl text-red-600"></i>
        <div>
          <h3 class="text-lg font-semibold text-gray-900">Redis Service</h3>
          <p class="text-sm text-gray-600">VM3: {{ serviceStatus.vm_info?.host || NetworkConstants.REDIS_VM_IP }}</p>
        </div>
      </div>

      <!-- Status Badge -->
      <div class="flex items-center space-x-3">
        <span class="text-xs text-gray-500">
          Last check: {{ formatLastCheck(serviceStatus.last_check) }}
        </span>
        <span
          class="inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium"
          :class="getStatusBadgeClass(serviceStatus.status)"
        >
          <span
            class="w-2 h-2 rounded-full mr-2 animate-pulse"
            :class="getStatusDotClass(serviceStatus.status)"
          ></span>
          {{ serviceStatus.status.toUpperCase() }}
        </span>
      </div>
    </div>

    <!-- Service Details (when running) -->
    <div
      v-if="serviceStatus.status === 'running'"
      class="grid grid-cols-1 md:grid-cols-4 gap-4 px-6 py-4 bg-gray-50 border-b"
    >
      <div class="detail-item">
        <span class="text-xs text-gray-500 uppercase tracking-wide">Uptime</span>
        <span class="text-lg font-semibold text-gray-900">{{ formatUptime(serviceStatus.uptime_seconds) }}</span>
      </div>
      <div class="detail-item">
        <span class="text-xs text-gray-500 uppercase tracking-wide">Memory</span>
        <span class="text-lg font-semibold text-gray-900">{{ serviceStatus.memory_mb || 0 }} MB</span>
      </div>
      <div class="detail-item">
        <span class="text-xs text-gray-500 uppercase tracking-wide">Connections</span>
        <span class="text-lg font-semibold text-gray-900">{{ serviceStatus.connections || 0 }}</span>
      </div>
      <div class="detail-item">
        <span class="text-xs text-gray-500 uppercase tracking-wide">PID</span>
        <span class="text-lg font-semibold text-gray-900">{{ serviceStatus.pid || 'N/A' }}</span>
      </div>
    </div>

    <!-- Control Buttons -->
    <div class="px-6 py-4 border-b">
      <div class="flex items-center justify-between">
        <div class="flex space-x-3">
          <button
            @click="handleStartService"
            :disabled="serviceStatus.status === 'running' || loading"
            class="btn btn-success flex items-center space-x-2 px-4 py-2 rounded-lg font-medium transition-colors"
            :class="serviceStatus.status === 'running' || loading ? 'opacity-50 cursor-not-allowed' : 'hover:bg-green-600'"
          >
            <i class="fas fa-play"></i>
            <span>Start</span>
          </button>

          <button
            @click="handleRestartService"
            :disabled="serviceStatus.status !== 'running' || loading"
            class="btn btn-warning flex items-center space-x-2 px-4 py-2 rounded-lg font-medium transition-colors"
            :class="serviceStatus.status !== 'running' || loading ? 'opacity-50 cursor-not-allowed' : 'hover:bg-yellow-600'"
          >
            <i class="fas fa-sync"></i>
            <span>Restart</span>
          </button>

          <button
            @click="handleStopService"
            :disabled="serviceStatus.status !== 'running' || loading"
            class="btn btn-danger flex items-center space-x-2 px-4 py-2 rounded-lg font-medium transition-colors"
            :class="serviceStatus.status !== 'running' || loading ? 'opacity-50 cursor-not-allowed' : 'hover:bg-red-700'"
          >
            <i class="fas fa-stop"></i>
            <span>Stop</span>
          </button>
        </div>

        <button
          @click="refreshStatus"
          :disabled="loading"
          class="btn btn-secondary flex items-center space-x-2 px-4 py-2 rounded-lg font-medium transition-colors hover:bg-gray-300"
        >
          <i :class="loading ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
          <span>Refresh</span>
        </button>
      </div>
    </div>

    <!-- Health Status Section -->
    <div v-if="healthStatus" class="px-6 py-4">
      <h4 class="text-md font-semibold text-gray-900 mb-3">Health Status</h4>

      <!-- Overall Health Indicator -->
      <div
        class="inline-flex items-center px-4 py-2 rounded-lg font-semibold mb-4"
        :class="getHealthIndicatorClass(healthStatus.overall_status)"
      >
        {{ healthStatus.overall_status.toUpperCase() }}
      </div>

      <!-- Health Checks -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        <div
          v-for="(check, name) in healthStatus.health_checks"
          :key="name"
          class="health-check-card p-4 rounded-lg border"
          :class="getHealthCheckCardClass(check.status)"
        >
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm font-medium text-gray-700 capitalize">{{ name }}</span>
            <span
              class="text-xs font-bold px-2 py-1 rounded"
              :class="getHealthCheckBadgeClass(check.status)"
            >
              {{ check.status }}
            </span>
          </div>
          <p class="text-xs text-gray-600 mb-1">{{ check.message }}</p>
          <p class="text-xs text-gray-500">{{ check.duration_ms }}ms</p>
        </div>
      </div>

      <!-- Recommendations -->
      <div
        v-if="healthStatus.recommendations && healthStatus.recommendations.length > 0"
        class="recommendations p-4 bg-yellow-50 border-l-4 border-yellow-400 rounded"
      >
        <h5 class="text-sm font-semibold text-yellow-800 mb-2">
          <i class="fas fa-lightbulb mr-1"></i>
          Recommendations
        </h5>
        <ul class="list-disc list-inside space-y-1">
          <li
            v-for="(rec, idx) in healthStatus.recommendations"
            :key="idx"
            class="text-sm text-yellow-700"
          >
            {{ rec }}
          </li>
        </ul>
      </div>

      <!-- Auto-Recovery Status -->
      <div
        v-if="healthStatus.auto_recovery"
        class="auto-recovery mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg"
      >
        <h5 class="text-sm font-semibold text-blue-900 mb-2">Auto-Recovery Status</h5>
        <div class="grid grid-cols-2 gap-3 text-sm">
          <div>
            <span class="text-blue-700">Enabled:</span>
            <span class="ml-2 font-medium">{{ healthStatus.auto_recovery.enabled ? 'Yes' : 'No' }}</span>
          </div>
          <div v-if="healthStatus.auto_recovery.recent_recoveries > 0">
            <span class="text-blue-700">Recent Recoveries:</span>
            <span class="ml-2 font-medium text-yellow-600">{{ healthStatus.auto_recovery.recent_recoveries }}</span>
          </div>
        </div>
        <div
          v-if="healthStatus.auto_recovery.requires_manual_intervention"
          class="mt-3 p-3 bg-red-100 border border-red-300 rounded text-sm text-red-800"
        >
          <i class="fas fa-exclamation-triangle mr-1"></i>
          <strong>Manual Intervention Required:</strong> Auto-recovery has failed. Please check service logs.
        </div>
      </div>
    </div>

    <!-- Loading Overlay -->
    <div v-if="loading" class="absolute inset-0 bg-white bg-opacity-75 flex items-center justify-center">
      <div class="text-center">
        <i class="fas fa-spinner fa-spin text-4xl text-blue-600 mb-2"></i>
        <p class="text-sm text-gray-600">Processing...</p>
      </div>
    </div>

    <!-- Confirmation Dialog -->
    <div
      v-if="showConfirmDialog"
      class="fixed inset-0 z-50 overflow-y-auto"
      @click.self="showConfirmDialog = false"
    >
      <div class="flex items-center justify-center min-h-screen px-4">
        <div class="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity"></div>

        <div class="relative bg-white rounded-lg max-w-md w-full shadow-xl">
          <div class="px-6 py-4 border-b">
            <h3 class="text-lg font-semibold text-gray-900">
              {{ confirmDialog.title }}
            </h3>
          </div>

          <div class="p-6">
            <p class="text-sm text-gray-700 mb-4">{{ confirmDialog.message }}</p>
            <div
              v-if="confirmDialog.warning"
              class="p-3 bg-yellow-50 border-l-4 border-yellow-400 rounded"
            >
              <p class="text-sm text-yellow-800">
                <i class="fas fa-exclamation-triangle mr-1"></i>
                {{ confirmDialog.warning }}
              </p>
            </div>
          </div>

          <div class="px-6 py-4 border-t flex justify-end space-x-3">
            <button
              @click="showConfirmDialog = false"
              class="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors"
            >
              Cancel
            </button>
            <button
              @click="confirmDialog.onConfirm"
              class="px-4 py-2 rounded-lg font-medium transition-colors"
              :class="confirmDialog.type === 'danger' ? 'bg-red-600 text-white hover:bg-red-700' : 'bg-blue-600 text-white hover:bg-blue-700'"
            >
              Confirm
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useServiceManagement } from '@/composables/useServiceManagement'
import { NetworkConstants } from '@/constants/network-constants.js'

// Service management composable
const {
  serviceStatus,
  healthStatus,
  loading,
  error,
  startService,
  stopService,
  restartService,
  refreshStatus,
  subscribeToStatusUpdates
} = useServiceManagement('redis')

// Confirmation dialog state
const showConfirmDialog = ref(false)
const confirmDialog = ref({
  title: '',
  message: '',
  warning: '',
  type: 'info',
  onConfirm: () => {}
})

/**
 * Lifecycle: Subscribe to WebSocket updates on mount
 */
onMounted(() => {
  subscribeToStatusUpdates((message) => {
    console.log('[RedisServiceControl] WebSocket update:', message)
  })
})

/**
 * Handle start service button click
 */
const handleStartService = async () => {
  try {
    await startService()
    console.log('[RedisServiceControl] Service started successfully')
  } catch (err) {
    console.error('[RedisServiceControl] Failed to start service:', err)
  }
}

/**
 * Handle restart service button click
 */
const handleRestartService = () => {
  showConfirmDialog.value = true
  confirmDialog.value = {
    title: 'Restart Redis Service',
    message: 'This will temporarily interrupt Redis service. Active connections will be dropped.',
    warning: 'All connected clients will be disconnected during restart.',
    type: 'warning',
    onConfirm: async () => {
      showConfirmDialog.value = false
      try {
        await restartService()
        console.log('[RedisServiceControl] Service restarted successfully')
      } catch (err) {
        console.error('[RedisServiceControl] Failed to restart service:', err)
      }
    }
  }
}

/**
 * Handle stop service button click
 */
const handleStopService = () => {
  showConfirmDialog.value = true
  confirmDialog.value = {
    title: 'Stop Redis Service',
    message: 'This will stop Redis service completely. All dependent services will be affected.',
    warning: 'WARNING: This action will affect system functionality. Only administrators can stop the service.',
    type: 'danger',
    onConfirm: async () => {
      showConfirmDialog.value = false
      try {
        await stopService(true)
        console.log('[RedisServiceControl] Service stopped successfully')
      } catch (err) {
        console.error('[RedisServiceControl] Failed to stop service:', err)
      }
    }
  }
}

/**
 * Format uptime from seconds
 */
const formatUptime = (seconds) => {
  if (!seconds) return 'N/A'

  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)

  if (days > 0) return `${days}d ${hours}h ${minutes}m`
  if (hours > 0) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

/**
 * Format last check timestamp
 */
const formatLastCheck = (timestamp) => {
  if (!timestamp) return 'Never'

  try {
    const date = new Date(timestamp)
    return date.toLocaleTimeString()
  } catch {
    return 'Unknown'
  }
}

/**
 * Get status badge CSS classes
 */
const getStatusBadgeClass = (status) => {
  switch (status) {
    case 'running':
      return 'bg-green-100 text-green-800'
    case 'stopped':
      return 'bg-gray-100 text-gray-800'
    case 'failed':
      return 'bg-red-100 text-red-800'
    default:
      return 'bg-yellow-100 text-yellow-800'
  }
}

/**
 * Get status dot CSS classes
 */
const getStatusDotClass = (status) => {
  switch (status) {
    case 'running':
      return 'bg-green-500'
    case 'stopped':
      return 'bg-gray-500'
    case 'failed':
      return 'bg-red-500'
    default:
      return 'bg-yellow-500'
  }
}

/**
 * Get health indicator CSS classes
 */
const getHealthIndicatorClass = (status) => {
  switch (status) {
    case 'healthy':
      return 'bg-green-100 text-green-800 border border-green-300'
    case 'degraded':
      return 'bg-yellow-100 text-yellow-800 border border-yellow-300'
    case 'critical':
      return 'bg-red-100 text-red-800 border border-red-300'
    default:
      return 'bg-gray-100 text-gray-800 border border-gray-300'
  }
}

/**
 * Get health check card CSS classes
 */
const getHealthCheckCardClass = (status) => {
  switch (status) {
    case 'pass':
      return 'border-green-300 bg-green-50'
    case 'warning':
      return 'border-yellow-300 bg-yellow-50'
    case 'fail':
      return 'border-red-300 bg-red-50'
    default:
      return 'border-gray-300 bg-gray-50'
  }
}

/**
 * Get health check badge CSS classes
 */
const getHealthCheckBadgeClass = (status) => {
  switch (status) {
    case 'pass':
      return 'bg-green-200 text-green-800'
    case 'warning':
      return 'bg-yellow-200 text-yellow-800'
    case 'fail':
      return 'bg-red-200 text-red-800'
    default:
      return 'bg-gray-200 text-gray-800'
  }
}
</script>

<style scoped>
.redis-service-control {
  position: relative;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  cursor: pointer;
}

.btn-success {
  background-color: #10b981;
  color: white;
}

.btn-warning {
  background-color: #f59e0b;
  color: white;
}

.btn-danger {
  background-color: #ef4444;
  color: white;
}

.btn-secondary {
  background-color: #e5e7eb;
  color: #374151;
}

.health-check-card {
  transition: transform 0.2s;
}

.health-check-card:hover {
  transform: translateY(-2px);
}
</style>
