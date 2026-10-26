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
        class="fixed bottom-4 right-4 max-w-md w-full bg-autobot-bg-card shadow-lg rounded-lg pointer-events-auto ring-1 ring-black/5 overflow-hidden z-9999"
      >
        <div class="p-4">
          <div class="flex items-start">
            <div class="shrink-0">
              <component
                :is="statusIcon"
                :class="[
                  'h-5 w-5',
                  tone(severity).text
                ]"
              />
            </div>
            <div class="ml-3 w-0 flex-1 pt-0.5">
              <p class="text-sm font-medium text-autobot-text-primary">{{ notificationData.title }}</p>
              <p class="mt-1 text-sm text-autobot-text-muted">{{ notificationData.message }}</p>
            </div>
            <div class="ml-4 shrink-0 flex">
              <button
                @click="dismissNotification"
                class="bg-autobot-bg-card rounded-md inline-flex text-autobot-text-muted hover:text-autobot-text-secondary focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-autobot-primary"
                :title="t('ui.systemStatus.dismissNotification')"
              >
                <span class="sr-only">{{ t('ui.systemStatus.close') }}</span>
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
        class="fixed inset-0 z-9999 bg-black/25 backdrop-blur-xs flex items-center justify-center p-4"
        @click.self="dismissNotification"
      >
        <div class="bg-autobot-bg-card rounded-lg shadow-xl max-w-md w-full mx-auto border border-autobot-border overflow-hidden">
          <!-- Header -->
          <div :class="[
            'px-4 py-3 border-b border-autobot-border',
            tone(notificationData.severity).header
          ]">
            <div class="flex items-center justify-between">
              <div class="flex items-center">
                <component
                  :is="statusIcon"
                  :class="[
                    'h-6 w-6 mr-2',
                    tone(notificationData.severity).text
                  ]"
                />
                <h3 :class="[
                  'text-lg font-semibold',
                  tone(notificationData.severity).text
                ]">
                  {{ notificationData.title }}
                </h3>
              </div>
              <button
                @click="dismissNotification"
                :class="[
                  'text-autobot-text-muted hover:text-autobot-text-secondary transition-colors',
                  tone(notificationData.severity).hover
                ]"
                :aria-label="t('ui.systemStatus.closeNotification')"
                :title="t('ui.systemStatus.dismissNotification')"
              >
                <XMarkIcon class="w-5 h-5" />
              </button>
            </div>
          </div>

          <!-- Content -->
          <div class="p-4">
            <p class="text-sm text-autobot-text-secondary mb-4">
              {{ notificationData.message }}
            </p>

            <!-- Status Details -->
            <div v-if="notificationData.statusDetails && notificationData.showDetails" class="space-y-3">
              <div class="bg-autobot-bg-secondary rounded-lg p-3">
                <h4 class="text-sm font-medium text-autobot-text-primary mb-2">
                  {{ t('ui.systemStatus.systemDetails') }}
                </h4>
                <dl class="space-y-1">
                  <div class="flex justify-between text-sm">
                    <dt class="text-autobot-text-secondary">{{ t('ui.systemStatus.status') }}</dt>
                    <dd :class="['font-medium', stateTone(notificationData.statusDetails.status)]">
                      {{ stateLabel(notificationData.statusDetails.status) }}
                    </dd>
                  </div>
                  <div class="flex justify-between text-sm">
                    <dt class="text-autobot-text-secondary">{{ t('ui.systemStatus.lastCheck') }}</dt>
                    <dd class="text-autobot-text-primary font-medium">
                      {{ formatTimestamp(notificationData.statusDetails.lastCheck) }}
                    </dd>
                  </div>
                  <div v-if="notificationData.statusDetails.consecutiveFailures" class="flex justify-between text-sm">
                    <dt class="text-autobot-text-secondary">{{ t('ui.systemStatus.consecutiveFailures') }}</dt>
                    <dd class="text-autobot-pill-bad-fg font-medium">
                      {{ notificationData.statusDetails.consecutiveFailures }}
                    </dd>
                  </div>
                  <div v-if="notificationData.statusDetails.error" class="mt-2">
                    <dt class="text-sm text-autobot-text-secondary mb-1">{{ t('ui.systemStatus.errorDetails') }}</dt>
                    <dd class="text-xs text-autobot-pill-bad-fg bg-autobot-pill-bad-bg p-2 rounded font-mono">
                      {{ notificationData.statusDetails.error }}
                    </dd>
                  </div>
                </dl>
              </div>
            </div>
          </div>

          <!-- Actions -->
          <div class="px-4 py-3 bg-autobot-bg-secondary flex justify-end">
            <button
              @click="dismissNotification"
              :class="[
                'px-4 py-2 text-sm font-medium rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2',
                tone(notificationData.severity).button
              ]"
            >
              {{ t('ui.systemStatus.dismiss') }}
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
import { useI18n } from 'vue-i18n'

// Now using wrapper div to avoid fragment root issues

import XMarkIcon from '@heroicons/vue/24/outline/XMarkIcon'
import ExclamationTriangleIcon from '@heroicons/vue/24/outline/ExclamationTriangleIcon'
import InformationCircleIcon from '@heroicons/vue/24/outline/InformationCircleIcon'
import XCircleIcon from '@heroicons/vue/24/outline/XCircleIcon'
import CheckCircleIcon from '@heroicons/vue/24/outline/CheckCircleIcon'
import type { SystemStatusDetails } from '@/types/system'

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
  autoHide: 0 // 0 = use canonical severity-based durations
})

const emit = defineEmits<{
  dismiss: []
  expired: []
  hide: []
  remove: []
}>()

const { t } = useI18n()

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

const TOAST_AUTO_HIDE: Record<string, number> = {
  error: 0,      // persistent — system errors require explicit dismissal
  warning: 6000, // canonical
  info: 4000,    // canonical
  success: 4000, // canonical
}

const setupAutoHide = () => {
  const canonical = TOAST_AUTO_HIDE[notificationData.value.severity] ?? 4000
  const hideDelay = notificationData.value.autoHide > 0
    ? notificationData.value.autoHide
    : canonical

  clearAutoHide()
  if (hideDelay > 0) {
    autoHideTimer.value = setTimeout(() => {
      showNotification.value = false
      emit('expired')
    }, hideDelay)
  }
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

// The monitor's states (#16253): a translated label and a token tone, never the raw value.
const STATE_TONE: Record<string, string> = {
  healthy: 'text-autobot-pill-ok-fg',
  degraded: 'text-autobot-pill-warn-fg',
  critical: 'text-autobot-pill-bad-fg',
}
const stateTone = (state: string): string => STATE_TONE[state] ?? 'text-autobot-text-secondary'
const stateLabel = (state: string): string =>
  state in STATE_TONE || state === 'unknown' ? t(`ui.systemStatus.states.${state}`) : state

// Severity colours are the theme's status pill pairs (#16253): each text/background pair is
// AA in every theme, which the plain state colours were not as text on a light card.
// Spelled out in full: Tailwind generates only the class names it finds in source.
const TONES = {
  error: {
    text: 'text-autobot-pill-bad-fg',
    header: 'bg-autobot-pill-bad-bg border-autobot-pill-bad-fg',
    hover: 'hover:text-autobot-pill-bad-fg',
    button: 'bg-autobot-pill-bad-bg text-autobot-pill-bad-fg border border-autobot-pill-bad-fg hover:opacity-90 focus:ring-autobot-pill-bad-fg',
  },
  warning: {
    text: 'text-autobot-pill-warn-fg',
    header: 'bg-autobot-pill-warn-bg border-autobot-pill-warn-fg',
    hover: 'hover:text-autobot-pill-warn-fg',
    button: 'bg-autobot-pill-warn-bg text-autobot-pill-warn-fg border border-autobot-pill-warn-fg hover:opacity-90 focus:ring-autobot-pill-warn-fg',
  },
  info: {
    text: 'text-autobot-pill-info-fg',
    header: 'bg-autobot-pill-info-bg border-autobot-pill-info-fg',
    hover: 'hover:text-autobot-pill-info-fg',
    button: 'bg-autobot-pill-info-bg text-autobot-pill-info-fg border border-autobot-pill-info-fg hover:opacity-90 focus:ring-autobot-pill-info-fg',
  },
  success: {
    text: 'text-autobot-pill-ok-fg',
    header: 'bg-autobot-pill-ok-bg border-autobot-pill-ok-fg',
    hover: 'hover:text-autobot-pill-ok-fg',
    button: 'bg-autobot-pill-ok-bg text-autobot-pill-ok-fg border border-autobot-pill-ok-fg hover:opacity-90 focus:ring-autobot-pill-ok-fg',
  },
} as const
const tone = (severity: string | undefined) => TONES[severity as keyof typeof TONES] ?? TONES.success

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
