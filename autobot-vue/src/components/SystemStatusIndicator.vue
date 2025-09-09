<template>
  <div class="relative flex items-center">
    <!-- Status Indicator Button -->
    <button
      @click="toggleDetails"
      :class="[
        'flex items-center px-2 py-1 rounded-md text-xs font-medium transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-white focus:ring-opacity-50',
        statusClasses,
        'hover:bg-white hover:bg-opacity-10'
      ]"
      :aria-label="`System status: ${indicator.text}. Click for details.`"
    >
      <!-- Status Icon -->
      <div :class="[
        'w-2 h-2 rounded-full mr-2 transition-all duration-200',
        indicator.pulse ? 'animate-pulse' : '',
        indicator.status === 'success' ? 'bg-green-400' :
        indicator.status === 'warning' ? 'bg-yellow-400' :
        indicator.status === 'error' ? 'bg-red-400' :
        'bg-gray-400'
      ]"></div>
      
      <!-- Status Text -->
      <span class="hidden sm:inline">{{ indicator.text }}</span>
      
      <!-- Notification Count Badge -->
      <div
        v-if="activeNotificationCount > 0"
        class="ml-1 flex items-center justify-center w-4 h-4 text-xs font-bold text-white bg-red-500 rounded-full animate-pulse"
      >
        {{ activeNotificationCount > 99 ? '99+' : activeNotificationCount }}
      </div>
    </button>

    <!-- Dropdown Details Panel -->
    <Teleport to="body">
      <div
        v-if="showDetails"
        class="fixed inset-0 z-50 flex items-start justify-center pt-4 px-4"
        @click="showDetails = false"
      >
        <!-- Backdrop -->
        <div class="absolute inset-0 bg-black bg-opacity-25 backdrop-blur-sm"></div>
        
        <!-- Panel -->
        <div
          class="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-auto border border-gray-200 dark:border-gray-600 max-h-96 overflow-y-auto"
          @click.stop
        >
          <!-- Header -->
          <div class="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-600">
            <div class="flex items-center">
              <!-- Status Icon Large -->
              <div :class="[
                'w-3 h-3 rounded-full mr-3 transition-all duration-200',
                indicator.pulse ? 'animate-pulse' : '',
                indicator.status === 'success' ? 'bg-green-400' :
                indicator.status === 'warning' ? 'bg-yellow-400' :
                indicator.status === 'error' ? 'bg-red-400' :
                'bg-gray-400'
              ]"></div>
              <h3 class="text-lg font-semibold text-gray-900 dark:text-white">
                System Status
              </h3>
            </div>
            <button
              @click="showDetails = false"
              class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
              aria-label="Close details"
            >
              <XMarkIcon class="w-5 h-5" />
            </button>
          </div>

          <!-- Content -->
          <div class="p-4">
            <!-- Current Status -->
            <div class="mb-4">
              <div class="flex items-center mb-2">
                <component
                  :is="getStatusIcon(indicator.status)"
                  :class="[
                    'w-5 h-5 mr-2',
                    indicator.status === 'success' ? 'text-green-400' :
                    indicator.status === 'warning' ? 'text-yellow-400' :
                    indicator.status === 'error' ? 'text-red-400' :
                    'text-gray-400'
                  ]"
                />
                <span class="text-sm font-medium text-gray-900 dark:text-white">
                  {{ indicator.text }}
                </span>
              </div>
              <p class="text-sm text-gray-600 dark:text-gray-400 ml-7">
                {{ getStatusDescription(indicator.status) }}
              </p>
            </div>

            <!-- System Details -->
            <div class="space-y-3">
              <div v-for="detail in indicator.details" :key="detail.label" class="flex justify-between">
                <span class="text-sm text-gray-600 dark:text-gray-400">{{ detail.label }}:</span>
                <span :class="[
                  'text-sm font-medium',
                  detail.status === 'success' ? 'text-green-600 dark:text-green-400' :
                  detail.status === 'warning' ? 'text-yellow-600 dark:text-yellow-400' :
                  detail.status === 'error' ? 'text-red-600 dark:text-red-400' :
                  'text-gray-900 dark:text-white'
                ]">
                  {{ detail.value }}
                </span>
              </div>
            </div>

            <!-- Active Notifications -->
            <div v-if="activeNotificationCount > 0" class="mt-4 pt-4 border-t border-gray-200 dark:border-gray-600">
              <h4 class="text-sm font-medium text-gray-900 dark:text-white mb-2">
                Active Notifications ({{ activeNotificationCount }})
              </h4>
              <div class="space-y-2">
                <div 
                  v-for="notification in (activeNotifications || []).slice(0, 3)" 
                  :key="notification.id"
                  class="flex items-start p-2 bg-gray-50 dark:bg-gray-700 rounded"
                >
                  <component
                    :is="getNotificationIcon(notification.type)"
                    :class="[
                      'w-4 h-4 mr-2 mt-0.5 flex-shrink-0',
                      notification.type === 'success' ? 'text-green-500' :
                      notification.type === 'warning' ? 'text-yellow-500' :
                      notification.type === 'error' ? 'text-red-500' :
                      'text-blue-500'
                    ]"
                  />
                  <div class="flex-1 min-w-0">
                    <p class="text-sm text-gray-900 dark:text-white truncate">
                      {{ notification.title }}
                    </p>
                    <p class="text-xs text-gray-600 dark:text-gray-400">
                      {{ formatTime(notification.timestamp) }}
                    </p>
                  </div>
                </div>
                <div v-if="activeNotificationCount > 3" class="text-xs text-gray-500 dark:text-gray-400 text-center">
                  ... and {{ activeNotificationCount - 3 }} more
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
import { ref, computed } from 'vue'
import { useAppStore } from '@/stores/useAppStore'
import XMarkIcon from '@heroicons/vue/24/outline/XMarkIcon'
import ExclamationTriangleIcon from '@heroicons/vue/24/outline/ExclamationTriangleIcon'
import InformationCircleIcon from '@heroicons/vue/24/outline/InformationCircleIcon'
import XCircleIcon from '@heroicons/vue/24/outline/XCircleIcon'
import CheckCircleIcon from '@heroicons/vue/24/outline/CheckCircleIcon'

const appStore = useAppStore()

// Local state
const showDetails = ref(false)

// Computed properties
const indicator = computed(() => appStore.systemStatusIndicator)

const statusClasses = computed(() => {
  const baseClasses = 'transition-colors duration-200'
  switch (indicator.value.status) {
    case 'success':
      return `${baseClasses} bg-green-600 hover:bg-green-700 text-white`
    case 'warning':
      return `${baseClasses} bg-yellow-600 hover:bg-yellow-700 text-white`
    case 'error':
      return `${baseClasses} bg-red-600 hover:bg-red-700 text-white`
    default:
      return `${baseClasses} bg-gray-600 hover:bg-gray-700 text-white`
  }
})

const activeNotifications = computed(() => 
  appStore.systemNotifications.filter(n => !n.dismissed)
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

const getNotificationIcon = (type: string) => {
  switch (type) {
    case 'success': return CheckCircleIcon
    case 'warning': return ExclamationTriangleIcon
    case 'error': return XCircleIcon
    default: return InformationCircleIcon
  }
}

const getStatusDescription = (status: string): string => {
  switch (status) {
    case 'success':
      return 'All systems operational'
    case 'warning':
      return 'Some systems experiencing issues'
    case 'error':
      return 'System errors detected'
    default:
      return 'System status unknown'
  }
}

const formatTime = (timestamp: Date): string => {
  if (!timestamp || !(timestamp instanceof Date)) {
    return new Date().toLocaleTimeString(undefined, { 
      hour: '2-digit', 
      minute: '2-digit' 
    })
  }
  return timestamp.toLocaleTimeString(undefined, { 
    hour: '2-digit', 
    minute: '2-digit' 
  })
}
</script>