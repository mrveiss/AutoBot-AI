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
.error-notifications-container {
  position: fixed;
  top: 1rem;
  right: 1rem;
  z-index: 9999;
  max-width: 420px;
  width: 100%;
}

@media (max-width: 640px) {
  .error-notifications-container {
    top: 0.5rem;
    right: 0.5rem;
    left: 0.5rem;
    max-width: none;
  }
}

.notification {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 1rem;
  margin-bottom: 0.5rem;
  background: white;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  border-left: 4px solid #cbd5e0;
  backdrop-filter: blur(10px);
}

.notification-error {
  border-left-color: #f56565;
  background: linear-gradient(135deg, #fff5f5 0%, #fed7d7 50%);
}

.notification-warning {
  border-left-color: #ed8936;
  background: linear-gradient(135deg, #fffaf0 0%, #feebc8 50%);
}

.notification-info {
  border-left-color: #4299e1;
  background: linear-gradient(135deg, #ebf8ff 0%, #bee3f8 50%);
}

.notification-icon {
  font-size: 1.25rem;
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
  color: #1a202c;
  font-weight: 500;
}

.notification-stack {
  margin-top: 0.5rem;
  background: rgba(0, 0, 0, 0.05);
  border-radius: 4px;
  padding: 0.5rem;
  max-height: 150px;
  overflow-y: auto;
}

.notification-stack pre {
  margin: 0;
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 0.75rem;
  color: #4a5568;
  white-space: pre-wrap;
  word-break: break-all;
}

.notification-actions {
  display: flex;
  align-items: flex-start;
  gap: 0.25rem;
  flex-shrink: 0;
}

.notification-btn {
  background: rgba(0, 0, 0, 0.1);
  border: none;
  border-radius: 4px;
  padding: 0.25rem 0.5rem;
  cursor: pointer;
  font-size: 0.75rem;
  transition: all 0.2s;
  color: #4a5568;
}

.notification-btn:hover {
  background: rgba(0, 0, 0, 0.2);
}

.notification-btn-close {
  background: rgba(239, 68, 68, 0.1);
  color: #dc2626;
}

.notification-btn-close:hover {
  background: rgba(239, 68, 68, 0.2);
}

.notification-btn-ghost {
  background: transparent;
  padding: 0.25rem;
  min-width: 1.5rem;
}

.notification-actions-bar {
  display: flex;
  justify-content: center;
  padding: 0.5rem;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 8px;
  backdrop-filter: blur(10px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.notification-btn-clear {
  background: #4299e1;
  color: white;
  padding: 0.5rem 1rem;
  font-weight: 500;
}

.notification-btn-clear:hover {
  background: #3182ce;
}

/* Transition animations */
.notification-enter-active,
.notification-leave-active {
  transition: all 0.3s ease;
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
  transition: transform 0.3s ease;
}
</style>
