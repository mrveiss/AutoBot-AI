<template>
  <div class="fixed top-4 left-4 z-30 lg:left-auto lg:right-4">
    <!-- Main status indicator -->
    <BaseButton
      @click="toggleDetails"
      :class="statusClasses"
      class="relative px-3 py-2 rounded-lg shadow-lg flex items-center space-x-2 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-all duration-200"
      :title="getStatusDescription(indicator.status)"
      variant="primary"
    >
      <!-- Status icon -->
      <component
        :is="getStatusIcon(indicator.status)"
        class="h-4 w-4"
      />

      <!-- Status text -->
      <span>{{ indicator.text }}</span>

      <!-- Pulse animation for warning/error states -->
      <div
        v-if="indicator.pulse"
        class="absolute -top-1 -right-1 w-3 h-3 bg-red-400 rounded-full animate-ping"
      ></div>

      <!-- Notification count badge -->
      <span
        v-if="activeNotificationCount > 0"
        class="inline-flex items-center justify-center px-2 py-1 text-xs font-bold leading-none text-red-100 bg-red-600 rounded-full"
      >
        {{ activeNotificationCount }}
      </span>
    </BaseButton>

    <!-- Details dropdown -->
    <Teleport to="body">
      <div
        v-show="showDetails"
        class="fixed inset-0 z-30"
        @click="showDetails = false"
      >
        <div class="fixed top-16 left-4 lg:left-auto lg:right-4 z-40 w-80 bg-white dark:bg-gray-800 rounded-lg shadow-xl border dark:border-gray-700 max-h-96 overflow-hidden"
             @click.stop>
          <!-- Header -->
          <div class="flex items-center justify-between p-4 border-b dark:border-gray-700">
            <h3 class="font-medium text-gray-900 dark:text-white">System Status</h3>
            <BaseButton
              variant="ghost"
              size="sm"
              @click="showDetails = false"
              class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded-md p-1 transition-colors duration-200"
            >
              <XMarkIcon class="h-5 w-5" />
            </BaseButton>
          </div>
          
          <!-- Status details -->
          <div class="p-4">
            <div class="flex items-center space-x-3 mb-4">
              <component 
                :is="getStatusIcon(indicator.status)" 
                :class="[
                  'h-6 w-6 flex-shrink-0',
                  indicator.status === 'success' ? 'text-green-500' :
                  indicator.status === 'warning' ? 'text-yellow-500' :
                  indicator.status === 'error' ? 'text-red-500' :
                  'text-gray-500'
                ]" 
              />
              <div class="flex-1 min-w-0">
                <p class="font-medium text-gray-900 dark:text-white">
                  {{ indicator.text }}
                </p>
                <p class="text-sm text-gray-600 dark:text-gray-400">
                  {{ getStatusDescription(indicator.status) }}
                </p>
              </div>
            </div>
            
            <!-- Service details -->
            <div 
              v-if="indicator.statusDetails"
              class="bg-gray-50 dark:bg-gray-700 rounded p-3 mb-4"
            >
              <div class="flex items-center justify-between text-sm">
                <span class="text-gray-600 dark:text-gray-400">Last Check:</span>
                <span class="text-gray-900 dark:text-white">
                  {{ formatTime(new Date(indicator.statusDetails.lastCheck)) }}
                </span>
              </div>
              <div 
                v-if="indicator.statusDetails.consecutiveFailures"
                class="flex items-center justify-between text-sm mt-1"
              >
                <span class="text-gray-600 dark:text-gray-400">Failures:</span>
                <span class="text-red-600">{{ indicator.statusDetails.consecutiveFailures }}</span>
              </div>
              <div 
                v-if="indicator.statusDetails.error"
                class="mt-2 text-xs text-red-600 dark:text-red-400 break-words"
              >
                {{ indicator.statusDetails.error }}
              </div>
            </div>

            <!-- Quick Actions -->
            <div class="flex items-center justify-between border-t dark:border-gray-700 pt-4 mt-4">
              <BaseButton
                variant="primary"
                size="xs"
                @click="refreshStatus"
                class="px-3 py-1 text-xs font-medium text-blue-600 hover:text-blue-700 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-900 rounded-md transition-colors duration-200"
              >
                Refresh
              </BaseButton>
              <BaseButton
                v-if="activeNotificationCount > 0"
                variant="danger"
                size="xs"
                @click="clearAllNotifications"
                class="px-3 py-1 text-xs font-medium text-red-600 hover:text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900 rounded-md transition-colors duration-200"
              >
                Clear All
              </BaseButton>
            </div>
          </div>
          
          <!-- Notifications -->
          <div v-if="activeNotificationCount > 0" class="border-t dark:border-gray-700">
            <div class="p-4">
              <h4 class="font-medium text-gray-900 dark:text-white mb-3">
                Active Notifications ({{ activeNotificationCount }})
              </h4>
              <div class="space-y-2 max-h-40 overflow-y-auto">
                <div 
                  v-for="notification in (activeNotifications || []).slice(0, 5)" 
                  :key="notification.id"
                  class="flex items-start p-2 bg-gray-50 dark:bg-gray-700 rounded hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors duration-200"
                >
                  <component
                    :is="getNotificationIcon(notification.severity)"
                    :class="[
                      'w-4 h-4 mr-2 mt-0.5 flex-shrink-0',
                      notification.severity === 'success' ? 'text-green-500' :
                      notification.severity === 'warning' ? 'text-yellow-500' :
                      notification.severity === 'error' ? 'text-red-500' :
                      notification.severity === 'info' ? 'text-blue-500' :
                      'text-gray-500'
                    ]"
                  />
                  <div class="flex-1 min-w-0">
                    <p class="text-sm text-gray-900 dark:text-white truncate">
                      {{ notification.title }}
                    </p>
                    <p class="text-xs text-gray-600 dark:text-gray-400 truncate">
                      {{ notification.message }}
                    </p>
                    <p class="text-xs text-gray-500 dark:text-gray-500">
                      {{ formatTime(new Date(notification.timestamp)) }}
                    </p>
                  </div>
                  <BaseButton
                    variant="ghost"
                    size="xs"
                    @click="hideNotification(notification.id)"
                    class="ml-2 p-1"
                  >
                    <XMarkIcon class="h-3 w-3" />
                  </BaseButton>
                </div>
                <div v-if="activeNotificationCount > 5" class="text-xs text-gray-500 dark:text-gray-400 text-center pt-2">
                  ... and {{ activeNotificationCount - 5 }} more
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import type { SystemSeverity } from '@/types/system'

const logger = createLogger('SystemStatusIndicator')
import { useAppStore } from '@/stores/useAppStore'
import XMarkIcon from '@heroicons/vue/24/outline/XMarkIcon'
import ExclamationTriangleIcon from '@heroicons/vue/24/outline/ExclamationTriangleIcon'
import InformationCircleIcon from '@heroicons/vue/24/outline/InformationCircleIcon'
import XCircleIcon from '@heroicons/vue/24/outline/XCircleIcon'
import { formatTime } from '@/utils/formatHelpers'
import CheckCircleIcon from '@heroicons/vue/24/outline/CheckCircleIcon'
import BaseButton from '@/components/base/BaseButton.vue'

const appStore = useAppStore()

// Local state
const showDetails = ref(false)

// Computed properties
const indicator = computed(() => appStore.systemStatusIndicator)

const statusClasses = computed(() => {
  const baseClasses = 'transition-all duration-200 hover:shadow-xl'
  switch (indicator.value.status) {
    case 'success':
      return `${baseClasses} bg-green-600 hover:bg-green-700 text-white`
    case 'warning':
      return `${baseClasses} bg-yellow-600 hover:bg-yellow-700 text-white`
    case 'error':
      return `${baseClasses} bg-red-600 hover:bg-red-700 text-white animate-pulse`
    default:
      return `${baseClasses} bg-gray-600 hover:bg-gray-700 text-white`
  }
})

const activeNotifications = computed(() => 
  appStore.systemNotifications.filter(n => n.visible)
)

const activeNotificationCount = computed(() => activeNotifications.value.length)

// Methods
const toggleDetails = () => {
  showDetails.value = !showDetails.value
}

const getStatusIcon = (status: string) => {
  switch (status) {
    case 'success': return CheckCircleIcon
    case 'warning': return ExclamationTriangleIcon
    case 'error': return XCircleIcon
    default: return InformationCircleIcon
  }
}

const getNotificationIcon = (severity: SystemSeverity) => {
  switch (severity) {
    case 'success': return CheckCircleIcon
    case 'warning': return ExclamationTriangleIcon
    case 'error': return XCircleIcon
    case 'info': return InformationCircleIcon
    default: return InformationCircleIcon
  }
}

const getStatusDescription = (status: string): string => {
  switch (status) {
    case 'success':
      return ''  // No redundant text for success state
    case 'warning':
      return 'Some systems experiencing issues'
    case 'error':
      return 'System errors detected - click for details'
    default:
      return 'System status unknown'
  }
}


const refreshStatus = async () => {
  try {
    // Trigger a manual health check
    const response = await fetch('/api/health')
    if (response.ok) {
      appStore.setBackendStatus({
        text: 'Connected',
        class: 'success'
      })
    } else {
      throw new Error(`Health check failed: ${response.status}`)
    }
  } catch (error) {
    logger.error('Manual health check failed:', error)
    appStore.setBackendStatus({
      text: 'Connection Error',
      class: 'error'
    })
  }
}

const clearAllNotifications = () => {
  appStore.clearAllNotifications()
}

const hideNotification = (id: string) => {
  appStore.hideSystemNotification(id)
}

// Cleanup on unmount to prevent teleport accumulation
onUnmounted(() => {
  showDetails.value = false
})
</script>

<style scoped>
@keyframes pulse {
  0%, 100% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.1);
    opacity: 0.7;
  }
}

.animate-ping {
  animation: pulse 1s cubic-bezier(0, 0, 0.2, 1) infinite;
}

/* Custom scrollbar for notification area */
.overflow-y-auto::-webkit-scrollbar {
  width: 4px;
}

.overflow-y-auto::-webkit-scrollbar-track {
  background: transparent;
}

.overflow-y-auto::-webkit-scrollbar-thumb {
  background-color: rgba(156, 163, 175, 0.5);
  border-radius: 2px;
}

.overflow-y-auto::-webkit-scrollbar-thumb:hover {
  background-color: rgba(156, 163, 175, 0.8);
}

/* Ensure error state is highly visible */
.bg-red-600.animate-pulse {
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}
</style>