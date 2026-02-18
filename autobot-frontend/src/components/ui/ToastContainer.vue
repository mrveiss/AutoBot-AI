<template>
  <Teleport to="body">
    <div class="toast-container" role="region" aria-label="Notifications" aria-live="polite">
      <TransitionGroup name="toast">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          :class="['toast', `toast-${toast.type}`]"
          role="alert"
          :aria-atomic="true"
        >
          <div class="toast-icon">
            <i :class="getIcon(toast.type)"></i>
          </div>
          <div class="toast-content">
            <span class="toast-message">{{ toast.message }}</span>
          </div>
          <button
            class="toast-close"
            @click="removeToast(toast.id)"
            aria-label="Dismiss notification"
          >
            <i class="fas fa-times"></i>
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
/**
 * ToastContainer - Global toast notification container
 *
 * Renders toast notifications from the useToast composable.
 * Should be included once in App.vue.
 *
 * @author mrveiss
 * @copyright 2025 mrveiss
 */
import { useToast } from '@/composables/useToast'

const { toasts, removeToast } = useToast()

const getIcon = (type: string): string => {
  switch (type) {
    case 'success':
      return 'fas fa-check-circle'
    case 'error':
      return 'fas fa-exclamation-circle'
    case 'warning':
      return 'fas fa-exclamation-triangle'
    case 'info':
    default:
      return 'fas fa-info-circle'
  }
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.toast-container {
  position: fixed;
  top: 80px;
  right: 20px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
  max-width: 400px;
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3-5) var(--spacing-4);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  pointer-events: auto;
  min-width: 300px;
  max-width: 400px;
}

.toast-info {
  background: var(--bg-card);
  color: var(--text-primary);
  border-left: 4px solid var(--color-primary);
  border: 1px solid var(--color-primary);
  border-left: 4px solid var(--color-primary);
}

.toast-success {
  background: var(--bg-card);
  color: var(--text-primary);
  border: 1px solid var(--color-success-border);
  border-left: 4px solid var(--color-success);
}

.toast-warning {
  background: var(--bg-card);
  color: var(--text-primary);
  border: 1px solid var(--color-warning-border);
  border-left: 4px solid var(--color-warning);
}

.toast-error {
  background: var(--bg-card);
  color: var(--text-primary);
  border: 1px solid var(--color-error-border);
  border-left: 4px solid var(--color-error);
}

.toast-icon {
  flex-shrink: 0;
  font-size: 1.2em;
}

.toast-content {
  flex: 1;
  min-width: 0;
}

.toast-message {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  line-height: var(--leading-normal);
  word-break: break-word;
}

.toast-close {
  flex-shrink: 0;
  background: var(--bg-hover);
  border: none;
  color: var(--text-secondary);
  width: 24px;
  height: 24px;
  border-radius: var(--radius-full);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background var(--duration-200) var(--ease-in-out);
}

.toast-close:hover {
  background: var(--bg-active);
  color: var(--text-primary);
}

.toast-close:focus {
  outline: 2px solid var(--color-primary-bg);
  outline-offset: 2px;
}

/* Transition animations */
.toast-enter-active {
  animation: slideIn var(--duration-300) var(--ease-out);
}

.toast-leave-active {
  animation: slideOut var(--duration-200) var(--ease-in);
}

.toast-move {
  transition: transform var(--duration-300) var(--ease-in-out);
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateX(100%);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

@keyframes slideOut {
  from {
    opacity: 1;
    transform: translateX(0);
  }
  to {
    opacity: 0;
    transform: translateX(100%);
  }
}

/* Responsive adjustments */
@media (max-width: 480px) {
  .toast-container {
    left: var(--spacing-3);
    right: var(--spacing-3);
    top: 70px;
    max-width: none;
  }

  .toast {
    min-width: unset;
    max-width: none;
  }
}

/* Reduced motion support */
@media (prefers-reduced-motion: reduce) {
  .toast-enter-active,
  .toast-leave-active {
    animation: none;
    transition: opacity var(--duration-150) var(--ease-in-out);
  }

  .toast-enter-from,
  .toast-leave-to {
    opacity: 0;
  }

  .toast-move {
    transition: none;
  }
}
</style>
