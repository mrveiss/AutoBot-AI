<template>
  <Teleport to="body">
    <div
      v-if="notifications.length > 0"
      class="error-notifications-container"
      role="alert"
      aria-live="polite"
    >
      <TransitionGroup name="notification" tag="div">
        <div
          v-for="notification in notifications"
          :key="notification.id"
          class="notification"
          :class="[`notification-${notification.type}`]"
        >
          <div class="notification-icon">
            <component :is="getIcon(notification.type)" />
          </div>

          <div class="notification-content">
            <p class="notification-message">{{ notification.message }}</p>
            <div v-if="notification.stack && showDetails[notification.id]" class="notification-stack">
              <pre>{{ notification.stack }}</pre>
            </div>
          </div>

          <div class="notification-actions">
            <button
              v-if="notification.stack"
              @click="toggleDetails(notification.id)"
              class="notification-btn notification-btn-ghost"
              :aria-label="showDetails[notification.id] ? 'Hide details' : 'Show details'"
            >
              {{ showDetails[notification.id] ? '▼' : '▶' }}
            </button>

            <button
              v-if="notification.dismissible"
              @click="dismiss(notification.id)"
              class="notification-btn notification-btn-close"
              aria-label="Dismiss notification"
            >
              ✕
            </button>
          </div>
        </div>
      </TransitionGroup>

      <div v-if="notifications.length > 1" class="notification-actions-bar">
        <button @click="clearAll" class="notification-btn notification-btn-clear">
          Clear All ({{ notifications.length }})
        </button>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, inject, onMounted, onUnmounted } from 'vue'
import type { ErrorNotification } from '../plugins/errorHandler'

// Icons as simple text components
const ErrorIcon = () => '⚠️'
const WarningIcon = () => '⚠️'
const InfoIcon = () => 'ℹ️'

const notifications = ref<ErrorNotification[]>([])
const showDetails = ref<Record<string, boolean>>({})

// Inject error handler
const errorHandler = inject('errorHandler') as any

let unsubscribe: (() => void) | null = null

onMounted(() => {
  if (errorHandler) {
    // Subscribe to error notifications
    unsubscribe = errorHandler.subscribe((newNotifications: ErrorNotification[]) => {
      notifications.value = newNotifications
    })
  }
})

onUnmounted(() => {
  if (unsubscribe) {
    unsubscribe()
  }
})

const getIcon = (type: ErrorNotification['type']) => {
  switch (type) {
    case 'error': return ErrorIcon
    case 'warning': return WarningIcon
    case 'info': return InfoIcon
    default: return InfoIcon
  }
}

const dismiss = (id: string) => {
  if (errorHandler) {
    errorHandler.dismissNotification(id)
  }
  delete showDetails.value[id]
}

const clearAll = () => {
  if (errorHandler) {
    errorHandler.clearAllNotifications()
  }
  showDetails.value = {}
}

const toggleDetails = (id: string) => {
  showDetails.value[id] = !showDetails.value[id]
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.error-notifications-container {
  position: fixed;
  top: var(--spacing-4);
  right: var(--spacing-4);
  z-index: 9999;
  max-width: 420px;
  width: 100%;
}

@media (max-width: 640px) {
  .error-notifications-container {
    top: var(--spacing-2);
    right: var(--spacing-2);
    left: var(--spacing-2);
    max-width: none;
  }
}

.notification {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  margin-bottom: var(--spacing-2);
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  border-left: 4px solid var(--border-default);
  backdrop-filter: blur(10px);
}

.notification-error {
  border-left-color: var(--color-error);
  background: var(--color-error-bg);
}

.notification-warning {
  border-left-color: var(--color-warning);
  background: var(--color-warning-bg);
}

.notification-info {
  border-left-color: var(--color-info);
  background: var(--color-info-bg);
}

.notification-icon {
  font-size: var(--text-xl);
  flex-shrink: 0;
  margin-top: 0.125rem;
}

.notification-content {
  flex: 1;
  min-width: 0;
}

.notification-message {
  margin: 0;
  line-height: 1.4;
  color: var(--text-primary);
  font-weight: var(--font-medium);
}

.notification-stack {
  margin-top: var(--spacing-2);
  background: var(--bg-tertiary-transparent);
  border-radius: var(--radius-sm);
  padding: var(--spacing-2);
  max-height: 150px;
  overflow-y: auto;
}

.notification-stack pre {
  margin: 0;
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
}

.notification-actions {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-1);
  flex-shrink: 0;
}

.notification-btn {
  background: var(--bg-tertiary-transparent);
  border: none;
  border-radius: var(--radius-sm);
  padding: var(--spacing-1) var(--spacing-2);
  cursor: pointer;
  font-size: var(--text-xs);
  transition: all var(--duration-200) var(--ease-in-out);
  color: var(--text-secondary);
}

.notification-btn:hover {
  background: var(--bg-tertiary);
}

.notification-btn-close {
  background: var(--color-error-bg-transparent);
  color: var(--color-error);
}

.notification-btn-close:hover {
  background: var(--color-error-bg);
}

.notification-btn-ghost {
  background: transparent;
  padding: var(--spacing-1);
  min-width: 1.5rem;
}

.notification-actions-bar {
  display: flex;
  justify-content: center;
  padding: var(--spacing-2);
  background: var(--bg-primary-transparent);
  border-radius: var(--radius-lg);
  backdrop-filter: blur(10px);
  box-shadow: var(--shadow-md);
}

.notification-btn-clear {
  background: var(--color-info);
  color: var(--text-on-primary);
  padding: var(--spacing-2) var(--spacing-4);
  font-weight: var(--font-medium);
}

.notification-btn-clear:hover {
  background: var(--color-info-hover);
}

/* Transition animations */
.notification-enter-active,
.notification-leave-active {
  transition: all var(--duration-300) var(--ease-in-out);
}

.notification-enter-from {
  opacity: 0;
  transform: translateX(100%) scale(0.95);
}

.notification-leave-to {
  opacity: 0;
  transform: translateX(100%) scale(0.95);
}

.notification-move {
  transition: transform var(--duration-300) var(--ease-in-out);
}
</style>
