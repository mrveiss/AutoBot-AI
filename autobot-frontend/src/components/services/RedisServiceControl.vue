<template>
  <div class="redis-service-control bg-autobot-bg-card rounded-lg shadow-md overflow-hidden">
    <!-- Service Header -->
    <div class="flex items-center justify-between px-6 py-4 border-b bg-gradient-to-r from-red-50 to-red-100">
      <div class="flex items-center space-x-3">
        <i class="fas fa-database text-2xl text-red-600"></i>
        <div>
          <h3 class="text-lg font-semibold text-autobot-text-primary">{{ $t('redis.title') }}</h3>
          <p class="text-sm text-autobot-text-secondary">VM3: {{ serviceStatus.vm_info?.host || NetworkConstants.REDIS_VM_IP }}</p>
        </div>
      </div>

      <!-- Status Badge -->
      <div class="flex items-center space-x-3">
        <span class="text-xs text-autobot-text-muted">
          {{ $t('redis.lastCheck') }} {{ formatLastCheck(serviceStatus.last_check) }}
        </span>
        <StatusBadge :variant="statusVariant" class="inline-flex items-center">
          <span
            class="w-2 h-2 rounded-full mr-2 animate-pulse"
            :class="getStatusDotClass(serviceStatus.status)"
          ></span>
          {{ (serviceStatus.status || 'unknown').toUpperCase() }}
        </StatusBadge>
      </div>
    </div>

    <!-- Service Details (when running) -->
    <div
      v-if="serviceStatus.status === 'running'"
      class="grid grid-cols-1 md:grid-cols-4 gap-4 px-6 py-4 bg-autobot-bg-secondary border-b"
    >
      <div class="detail-item">
        <span class="text-xs text-autobot-text-muted uppercase tracking-wide">{{ $t('redis.uptime') }}</span>
        <span class="text-lg font-semibold text-autobot-text-primary">{{ formatUptime(serviceStatus.uptime_seconds) }}</span>
      </div>
      <div class="detail-item">
        <span class="text-xs text-autobot-text-muted uppercase tracking-wide">{{ $t('redis.memory') }}</span>
        <span class="text-lg font-semibold text-autobot-text-primary">{{ serviceStatus.memory_mb || 0 }} MB</span>
      </div>
      <div class="detail-item">
        <span class="text-xs text-autobot-text-muted uppercase tracking-wide">{{ $t('redis.connections') }}</span>
        <span class="text-lg font-semibold text-autobot-text-primary">{{ serviceStatus.connections || 0 }}</span>
      </div>
      <div class="detail-item">
        <span class="text-xs text-autobot-text-muted uppercase tracking-wide">{{ $t('redis.pid') }}</span>
        <span class="text-lg font-semibold text-autobot-text-primary">{{ serviceStatus.pid || 'N/A' }}</span>
      </div>
    </div>

    <!-- Control Buttons -->
    <div class="px-6 py-4 border-b">
      <div class="flex items-center justify-between">
        <div class="flex space-x-3">
          <BaseButton
            variant="success"
            @click="handleStartService"
            :disabled="serviceStatus.status === 'running' || loading"
            class="flex items-center space-x-2 px-4 py-2"
          >
            <i class="fas fa-play"></i>
            <span>{{ $t('redis.start') }}</span>
          </BaseButton>

          <BaseButton
            variant="warning"
            @click="handleRestartService"
            :disabled="serviceStatus.status !== 'running' || loading"
            class="flex items-center space-x-2 px-4 py-2"
          >
            <i class="fas fa-sync"></i>
            <span>{{ $t('redis.restart') }}</span>
          </BaseButton>

          <BaseButton
            variant="danger"
            @click="handleStopService"
            :disabled="serviceStatus.status !== 'running' || loading"
            class="flex items-center space-x-2 px-4 py-2"
          >
            <i class="fas fa-stop"></i>
            <span>{{ $t('redis.stop') }}</span>
          </BaseButton>
        </div>

        <BaseButton
          variant="secondary"
          @click="refreshStatus"
          :loading="loading"
          class="flex items-center space-x-2 px-4 py-2"
        >
          <i class="fas fa-sync-alt"></i>
          <span>{{ $t('common.refresh') }}</span>
        </BaseButton>
      </div>
    </div>

    <!-- Health Status Section -->
    <div v-if="healthStatus" class="px-6 py-4">
      <h4 class="text-md font-semibold text-autobot-text-primary mb-3">{{ $t('redis.healthStatus') }}</h4>

      <!-- Overall Health Indicator -->
      <StatusBadge :variant="healthVariant" size="medium" class="font-semibold mb-4">
        {{ (healthStatus?.overall_status || 'unknown').toUpperCase() }}
      </StatusBadge>

      <!-- Health Checks -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        <div
          v-for="(check, name) in healthStatus.health_checks"
          :key="name"
          class="health-check-card p-4 rounded-lg border"
          :class="getHealthCheckCardClass(check.status)"
        >
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm font-medium text-autobot-text-secondary capitalize">{{ name }}</span>
            <StatusBadge :variant="getHealthCheckVariant(check.status)" size="small" class="font-bold">
              {{ check.status }}
            </StatusBadge>
          </div>
          <p class="text-xs text-autobot-text-secondary mb-1">{{ check.message }}</p>
          <p class="text-xs text-autobot-text-muted">{{ check.duration_ms }}ms</p>
        </div>
      </div>

      <!-- Recommendations -->
      <div
        v-if="healthStatus.recommendations && healthStatus.recommendations.length > 0"
        class="recommendations p-4 bg-yellow-50 border-l-4 border-yellow-400 rounded"
      >
        <h5 class="text-sm font-semibold text-yellow-800 mb-2">
          <i class="fas fa-lightbulb mr-1"></i>
          {{ $t('redis.recommendations') }}
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
        <h5 class="text-sm font-semibold text-blue-900 mb-2">{{ $t('redis.autoRecoveryStatus') }}</h5>
        <div class="grid grid-cols-2 gap-3 text-sm">
          <div>
            <span class="text-blue-700">{{ $t('redis.enabled') }}</span>
            <span class="ml-2 font-medium">{{ healthStatus.auto_recovery.enabled ? $t('common.yes') : $t('common.no') }}</span>
          </div>
          <div v-if="healthStatus.auto_recovery.recent_recoveries > 0">
            <span class="text-blue-700">{{ $t('redis.recentRecoveries') }}</span>
            <span class="ml-2 font-medium text-yellow-600">{{ healthStatus.auto_recovery.recent_recoveries }}</span>
          </div>
        </div>
        <div
          v-if="healthStatus.auto_recovery.requires_manual_intervention"
          class="mt-3 p-3 bg-red-100 border border-red-300 rounded text-sm text-red-800"
        >
          <i class="fas fa-exclamation-triangle mr-1"></i>
          <strong>{{ $t('redis.manualInterventionTitle') }}</strong> {{ $t('redis.manualInterventionMsg') }}
        </div>
      </div>
    </div>

    <!-- Loading Overlay -->
    <div v-if="loading" class="absolute inset-0 bg-autobot-bg-card bg-opacity-75 flex items-center justify-center">
      <div class="text-center">
        <i class="fas fa-spinner fa-spin text-4xl text-blue-600 mb-2"></i>
        <p class="text-sm text-autobot-text-secondary">{{ $t('redis.processing') }}</p>
      </div>
    </div>

    <!-- Confirmation Dialog -->
    <BaseModal
      v-model="showConfirmDialog"
      :title="confirmDialog.title"
      size="medium"
    >
      <p class="text-sm text-autobot-text-secondary mb-4">{{ confirmDialog.message }}</p>
      <div
        v-if="confirmDialog.warning"
        class="p-3 bg-yellow-50 border-l-4 border-yellow-400 rounded"
      >
        <p class="text-sm text-yellow-800">
          <i class="fas fa-exclamation-triangle mr-1"></i>
          {{ confirmDialog.warning }}
        </p>
      </div>

      <template #actions>
        <BaseButton
          variant="secondary"
          @click="showConfirmDialog = false"
        >
          {{ $t('common.cancel') }}
        </BaseButton>
        <BaseButton
          :variant="confirmDialog.type === 'danger' ? 'danger' : 'primary'"
          @click="confirmDialog.onConfirm"
        >
          {{ $t('common.confirm') }}
        </BaseButton>
      </template>
    </BaseModal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useServiceManagement } from '@/composables/useServiceManagement'
import { NetworkConstants } from '@/constants/network'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('RedisServiceControl')
const { t } = useI18n()

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

// Map service status to StatusBadge variant
const statusVariant = computed(() => {
  const statusMap = {
    'running': 'success',
    'stopped': 'secondary',
    'failed': 'danger'
  }
  return statusMap[serviceStatus.value.status] || 'warning'
})

// Map health status to StatusBadge variant
const healthVariant = computed(() => {
  const healthMap = {
    'healthy': 'success',
    'degraded': 'warning',
    'critical': 'danger'
  }
  return healthMap[healthStatus.value?.overall_status] || 'secondary'
})

// Map health check status to StatusBadge variant
const getHealthCheckVariant = (status) => {
  const variantMap = {
    'pass': 'success',
    'warning': 'warning',
    'fail': 'danger'
  }
  return variantMap[status] || 'secondary'
}

/**
 * Lifecycle: Subscribe to WebSocket updates on mount
 */
onMounted(() => {
  subscribeToStatusUpdates((message) => {
  })
})

/**
 * Handle start service button click
 */
const handleStartService = async () => {
  try {
    await startService()
  } catch (err) {
    logger.error('Failed to start service:', err)
  }
}

/**
 * Handle restart service button click
 */
const handleRestartService = () => {
  showConfirmDialog.value = true
  confirmDialog.value = {
    title: t('redis.restartTitle'),
    message: t('redis.restartMsg'),
    warning: t('redis.restartWarning'),
    type: 'warning',
    onConfirm: async () => {
      showConfirmDialog.value = false
      try {
        await restartService()
      } catch (err) {
        logger.error('Failed to restart service:', err)
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
    title: t('redis.stopTitle'),
    message: t('redis.stopMsg'),
    warning: t('redis.stopWarning'),
    type: 'danger',
    onConfirm: async () => {
      showConfirmDialog.value = false
      try {
        await stopService(true)
      } catch (err) {
        logger.error('Failed to stop service:', err)
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
  if (!timestamp) return t('llm.never')

  try {
    const date = new Date(timestamp)
    return date.toLocaleTimeString()
  } catch {
    return 'Unknown'
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
      return 'bg-autobot-text-muted'
    case 'failed':
      return 'bg-red-500'
    default:
      return 'bg-yellow-500'
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
      return 'border-autobot-border bg-autobot-bg-tertiary'
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

.health-check-card {
  transition: transform 0.2s;
}

.health-check-card:hover {
  transform: translateY(-2px);
}
</style>
