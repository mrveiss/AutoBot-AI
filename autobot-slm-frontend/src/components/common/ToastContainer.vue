<template>
  <Teleport to="body">
    <div
      class="toast-container"
      role="region"
      :aria-label="$t('common.toastContainer.notifications')"
      aria-live="polite"
    >
      <TransitionGroup name="toast">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          :class="['toast', `toast-${toast.type}`]"
          role="alert"
          :aria-atomic="true"
        >
          <div class="toast-icon">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="getIconPath(toast.type)" />
            </svg>
          </div>
          <div class="toast-content">
            <span class="toast-message">{{ toast.message }}</span>
          </div>
          <button
            class="toast-close"
            @click="removeToast(toast.id)"
            :aria-label="$t('common.toastContainer.dismissNotification')"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { useToast } from '@/composables/useToast'

const { toasts, removeToast } = useToast()

const getIconPath = (type: string): string => {
  switch (type) {
    case 'success':
      return 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z'
    case 'error':
      return 'M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z'
    case 'warning':
      return 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z'
    default:
      return 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z'
  }
}
</script>

<style scoped>
.toast-container {
  position: fixed;
  top: 80px;
  right: var(--spacing-5);
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
  max-width: 400px;
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3) var(--spacing-4);
  border-radius: var(--radius-lg);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  pointer-events: auto;
  min-width: 300px;
  max-width: 400px;
  background: var(--a11y-bg-surface);
}

/* #11515 Task 4: status colors → tokens. Light full-border is a theme-aware
 * tint of the status hue over the surface; the bold left edge + icon use the
 * status -500 token. */
.toast-info {
  border: 1px solid color-mix(in srgb, var(--color-primary-500) 45%, var(--a11y-bg-surface));
  border-left: 4px solid var(--color-primary-500);
}

.toast-success {
  border: 1px solid color-mix(in srgb, var(--color-success-500) 45%, var(--a11y-bg-surface));
  border-left: 4px solid var(--color-success-500);
}

.toast-warning {
  border: 1px solid color-mix(in srgb, var(--color-warning-500) 45%, var(--a11y-bg-surface));
  border-left: 4px solid var(--color-warning-500);
}

.toast-error {
  border: 1px solid color-mix(in srgb, var(--color-danger-500) 45%, var(--a11y-bg-surface));
  border-left: 4px solid var(--color-danger-500);
}

.toast-icon {
  flex-shrink: 0;
}

.toast-info .toast-icon { color: var(--color-primary-500); }
.toast-success .toast-icon { color: var(--color-success-500); }
.toast-warning .toast-icon { color: var(--color-warning-500); }
.toast-error .toast-icon { color: var(--color-danger-500); }

.toast-content {
  flex: 1;
  min-width: 0;
}

.toast-message {
  font-size: 0.875rem;
  font-weight: 500;
  line-height: 1.5;
  word-break: break-word;
  color: var(--a11y-text);
}

.toast-close {
  flex-shrink: 0;
  background: transparent;
  border: none;
  color: var(--a11y-text-muted);
  min-width: var(--spacing-8);
  min-height: var(--spacing-8);
  border-radius: var(--radius-md);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, color 0.15s;
}

.toast-close:hover {
  background: var(--a11y-bg-muted);
  color: var(--a11y-text);
}

.toast-close:focus-visible {
  outline: 2px solid var(--a11y-focus-ring);
  outline-offset: 2px;
}

.toast-enter-active {
  animation: slideIn 0.3s ease-out;
}

.toast-leave-active {
  animation: slideOut 0.2s ease-in;
}

.toast-move {
  transition: transform 0.3s ease-in-out;
}

@keyframes slideIn {
  from { opacity: 0; transform: translateX(100%); }
  to { opacity: 1; transform: translateX(0); }
}

@keyframes slideOut {
  from { opacity: 1; transform: translateX(0); }
  to { opacity: 0; transform: translateX(100%); }
}

@media (max-width: 480px) {
  .toast-container {
    left: var(--spacing-3);
    right: var(--spacing-3);
    top: 70px;
    max-width: none;
  }
  .toast { min-width: unset; max-width: none; }
}

@media (prefers-reduced-motion: reduce) {
  .toast-enter-active,
  .toast-leave-active {
    animation: none;
    transition: opacity 0.15s ease-in-out;
  }
  .toast-enter-from,
  .toast-leave-to { opacity: 0; }
  .toast-move { transition: none; }
}
</style>
