<template>
  <Teleport to="body">
    <div
      class="toast-container"
      role="region"
      aria-label="Notifications"
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
            aria-label="Dismiss notification"
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
  right: 20px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 400px;
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  pointer-events: auto;
  min-width: 300px;
  max-width: 400px;
  background: white;
}

.toast-info {
  border-left: 4px solid #3b82f6;
  border: 1px solid #93c5fd;
  border-left: 4px solid #3b82f6;
}

.toast-success {
  border: 1px solid #86efac;
  border-left: 4px solid #22c55e;
}

.toast-warning {
  border: 1px solid #fcd34d;
  border-left: 4px solid #f59e0b;
}

.toast-error {
  border: 1px solid #fca5a5;
  border-left: 4px solid #ef4444;
}

.toast-icon {
  flex-shrink: 0;
}

.toast-info .toast-icon { color: #3b82f6; }
.toast-success .toast-icon { color: #22c55e; }
.toast-warning .toast-icon { color: #f59e0b; }
.toast-error .toast-icon { color: #ef4444; }

.toast-content {
  flex: 1;
  min-width: 0;
}

.toast-message {
  font-size: 0.875rem;
  font-weight: 500;
  line-height: 1.5;
  word-break: break-word;
  color: #111827;
}

.toast-close {
  flex-shrink: 0;
  background: transparent;
  border: none;
  color: #6b7280;
  min-width: 32px;
  min-height: 32px;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, color 0.15s;
}

.toast-close:hover {
  background: #f3f4f6;
  color: #111827;
}

.toast-close:focus-visible {
  outline: 2px solid #3b82f6;
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
    left: 12px;
    right: 12px;
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
