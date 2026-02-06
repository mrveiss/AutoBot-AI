<template>
  <!-- Wrapper div to avoid fragment root issues -->
  <div>
    <Teleport to="body">
      <!-- Subtle Toast Notifications (Bottom-Right) -->
    <Transition
      enter-active-class="transition duration-300 ease-out"
      enter-from-class="translate-y-2 opacity-0"
      enter-to-class="translate-y-0 opacity-100"
      leave-active-class="transition duration-200 ease-in"
      leave-from-class="translate-y-0 opacity-100"
      leave-to-class="translate-y-2 opacity-0"
    >
      <div
        v-show="showNotification && notificationLevel === 'toast'"
        class="fixed bottom-4 right-4 max-w-md w-full bg-white dark:bg-gray-800 shadow-lg rounded-lg pointer-events-auto ring-1 ring-black ring-opacity-5 overflow-hidden z-[9999]"
      >
        <div class="p-4">
          <div class="flex items-start">
            <div class="flex-shrink-0">
              <component
                :is="statusIcon"
                :class="[
                  'h-5 w-5',
                  severity === 'info' ? 'text-blue-400' :
                  severity === 'warning' ? 'text-yellow-400' :
                  severity === 'error' ? 'text-red-400' :
                  'text-green-400'
                ]"
              />
            </div>
            <div class="ml-3 w-0 flex-1 pt-0.5">
              <p class="text-sm font-medium text-gray-900 dark:text-white">{{ notificationData.title }}</p>
              <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">{{ notificationData.message }}</p>
            </div>
            <div class="ml-4 flex-shrink-0 flex">
              <button
                @click="dismissNotification"
                class="bg-white dark:bg-gray-800 rounded-md inline-flex text-gray-400 hover:text-gray-500 dark:hover:text-gray-300 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                title="Dismiss notification"
              >
                <span class="sr-only">Close</span>
                <XMarkIcon class="h-5 w-5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>

    <!-- Critical Error Overlay (Only for Critical System Errors) -->
    <Transition
      enter-active-class="transition duration-300 ease-out"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition duration-200 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-show="showNotification && notificationLevel === 'overlay'"
        class="fixed inset-0 z-[9999] bg-black bg-opacity-25 backdrop-blur-sm flex items-center justify-center p-4"
        @click.self="dismissNotification"
      >
        <div class="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-auto border border-gray-200 dark:border-gray-600 overflow-hidden">
          <!-- Header -->
          <div :class="[
            'px-4 py-3 border-b border-gray-200 dark:border-gray-600',
            notificationData.severity === 'error' ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800' :
            notificationData.severity === 'warning' ? 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800' :
            notificationData.severity === 'info' ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800' :
            'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
          ]">
            <div class="flex items-center justify-between">
              <div class="flex items-center">
                <component
                  :is="statusIcon"
                  :class="[
                    'h-6 w-6 mr-2',
                    notificationData.severity === 'error' ? 'text-red-600 dark:text-red-400' :
                    notificationData.severity === 'warning' ? 'text-yellow-600 dark:text-yellow-400' :
                    notificationData.severity === 'info' ? 'text-blue-600 dark:text-blue-400' :
                    'text-green-600 dark:text-green-400'
                  ]"
                />
                <h3 :class="[
                  'text-lg font-semibold',
                  notificationData.severity === 'error' ? 'text-red-900 dark:text-red-100' :
                  notificationData.severity === 'warning' ? 'text-yellow-900 dark:text-yellow-100' :
                  notificationData.severity === 'info' ? 'text-blue-900 dark:text-blue-100' :
                  'text-green-900 dark:text-green-100'
                ]">
                  {{ notificationData.title }}
                </h3>
              </div>
              <button
                @click="dismissNotification"
                :class="[
                  'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors',
                  notificationData.severity === 'error' ? 'hover:text-red-700 dark:hover:text-red-300' :
                  notificationData.severity === 'warning' ? 'hover:text-yellow-700 dark:hover:text-yellow-300' :
                  notificationData.severity === 'info' ? 'hover:text-blue-700 dark:hover:text-blue-300' :
                  'hover:text-green-700 dark:hover:text-green-300'
                ]"
                aria-label="Close notification"
                title="Dismiss notification"
              >
                <XMarkIcon class="w-5 h-5" />
              </button>
            </div>
          </div>

          <!-- Content -->
          <div class="p-4">
            <p class="text-sm text-gray-700 dark:text-gray-300 mb-4">
              {{ notificationData.message }}
            </p>

            <!-- Status Details -->
            <div v-if="notificationData.statusDetails && notificationData.showDetails" class="space-y-3">
              <div class="bg-gray-50 dark:bg-gray-700 rounded-lg p-3">
                <h4 class="text-sm font-medium text-gray-900 dark:text-white mb-2">
                  System Details
                </h4>
                <dl class="space-y-1">
                  <div class="flex justify-between text-sm">
                    <dt class="text-gray-600 dark:text-gray-400">Status:</dt>
                    <dd :class="[
                      'font-medium',
                      notificationData.statusDetails.status === 'online' ? 'text-green-600 dark:text-green-400' :
                      notificationData.statusDetails.status === 'degraded' ? 'text-yellow-600 dark:text-yellow-400' :
                      'text-red-600 dark:text-red-400'
                    ]">
                      {{ notificationData.statusDetails.status }}
                    </dd>
                  </div>
                  <div class="flex justify-between text-sm">
                    <dt class="text-gray-600 dark:text-gray-400">Last Check:</dt>
                    <dd class="text-gray-900 dark:text-white font-medium">
                      {{ formatTimestamp(notificationData.statusDetails.lastCheck) }}
                    </dd>
                  </div>
                  <div v-if="notificationData.statusDetails.consecutiveFailures" class="flex justify-between text-sm">
                    <dt class="text-gray-600 dark:text-gray-400">Consecutive Failures:</dt>
                    <dd class="text-red-600 dark:text-red-400 font-medium">
                      {{ notificationData.statusDetails.consecutiveFailures }}
                    </dd>
                  </div>
                  <div v-if="notificationData.statusDetails.error" class="mt-2">
                    <dt class="text-sm text-gray-600 dark:text-gray-400 mb-1">Error Details:</dt>
                    <dd class="text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 p-2 rounded font-mono">
                      {{ notificationData.statusDetails.error }}
                    </dd>
                  </div>
                </dl>
              </div>
            </div>
          </div>

          <!-- Actions -->
          <div class="px-4 py-3 bg-gray-50 dark:bg-gray-700 flex justify-end">
            <button
              @click="dismissNotification"
              :class="[
                'px-4 py-2 text-sm font-medium rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2',
                notificationData.severity === 'error' ? 'bg-red-600 hover:bg-red-700 text-white focus:ring-red-500' :
                notificationData.severity === 'warning' ? 'bg-yellow-600 hover:bg-yellow-700 text-white focus:ring-yellow-500' :
                notificationData.severity === 'info' ? 'bg-blue-600 hover:bg-blue-700 text-white focus:ring-blue-500' :
                'bg-green-600 hover:bg-green-700 text-white focus:ring-green-500'
              ]"
            >
              Dismiss
            </button>
          </div>
        </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { useAppStore } from '@/stores/useAppStore'

// Now using wrapper div to avoid fragment root issues

import XMarkIcon from '@heroicons/vue/24/outline/XMarkIcon'
import ExclamationTriangleIcon from '@heroicons/vue/24/outline/ExclamationTriangleIcon'
import InformationCircleIcon from '@heroicons/vue/24/outline/InformationCircleIcon'
import XCircleIcon from '@heroicons/vue/24/outline/XCircleIcon'
import CheckCircleIcon from '@heroicons/vue/24/outline/CheckCircleIcon'

export interface SystemStatusDetails {
  status: string
  lastCheck: number
  consecutiveFailures?: number
  error?: string
}

export interface SystemStatusNotificationProps {
  visible?: boolean
  severity?: 'info' | 'warning' | 'error' | 'success'
  title?: string
  message?: string
  statusDetails?: SystemStatusDetails
  allowDismiss?: boolean
  showDetails?: boolean
  autoHide?: number // Auto hide after X milliseconds
}

const props = withDefaults(defineProps<SystemStatusNotificationProps>(), {
  visible: true,
  severity: 'info',
  title: '',
  message: '',
  allowDismiss: true, // Always dismissible now
  showDetails: false,
  autoHide: 10000 // Auto-hide after 10 seconds by default
})

const emit = defineEmits<{
  dismiss: []
  expired: []
  hide: []
  remove: []
}>()

const appStore = useAppStore()

// Computed properties for notification data
const notificationData = computed(() => {
  return {
    visible: props.visible,
    severity: props.severity,
    title: props.title,
    message: props.message,
    statusDetails: props.statusDetails,
    allowDismiss: props.allowDismiss,
    showDetails: props.showDetails,
    autoHide: props.autoHide
  }
})

// Local state
const showNotification = ref(notificationData.value.visible)
const autoHideTimer = ref<NodeJS.Timeout | null>(null)

// Computed properties
const statusIcon = computed(() => {
  switch (notificationData.value.severity) {
    case 'error':
      return XCircleIcon
    case 'warning':
      return ExclamationTriangleIcon
    case 'success':
      return CheckCircleIcon
    default:
      return InformationCircleIcon
  }
})

const notificationLevel = computed(() => {
  // ONLY show overlay for CRITICAL errors with multiple consecutive failures
  // Most errors should use subtle toast notification at bottom-right
  if (notificationData.value.severity === 'error' &&
      notificationData.value.statusDetails?.consecutiveFailures &&
      notificationData.value.statusDetails.consecutiveFailures > 5) {
    return 'overlay'
  }
  return 'toast' // Default to subtle toast notification
})

// Methods - Define before usage in watchers
const clearAutoHide = () => {
  if (autoHideTimer.value) {
    clearTimeout(autoHideTimer.value)
    autoHideTimer.value = null
  }
}

const setupAutoHide = () => {
  // Auto-hide based on severity (always auto-hide to prevent intrusive behavior)
  const hideDelay = notificationData.value.autoHide > 0
    ? notificationData.value.autoHide
    : (notificationData.value.severity === 'error' ? 12000 : 8000)

  clearAutoHide()
  autoHideTimer.value = setTimeout(() => {
    showNotification.value = false
    emit('expired')
  }, hideDelay)
}

const dismissNotification = () => {
  showNotification.value = false
  clearAutoHide()
  emit('dismiss')
  emit('hide')
  emit('remove')
}

// Watchers
watch(() => notificationData.value.visible, (newValue) => {
  showNotification.value = newValue

  if (newValue) {
    setupAutoHide()
  } else {
    clearAutoHide()
  }
}, { immediate: true })

const formatTimestamp = (timestamp: number): string => {
  return new Date(timestamp).toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

// Cleanup on unmount
onUnmounted(() => {
  clearAutoHide()
})
</script>
