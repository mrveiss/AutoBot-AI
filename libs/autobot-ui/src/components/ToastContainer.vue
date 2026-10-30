<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ToastContainer -- the one toast host for both apps (#19903). It replaces the
  main app's ui/ToastContainer and the SLM's common/ToastContainer, which had
  drifted into two renderings of the same `useToast` stack. This is the union:

    - SLM: an inline SVG icon per status, tinted with the status token.
    - Main app: safe-area insets, a 44px dismiss target (WCAG 2.5.5), a
      full-width layout on narrow screens, reduced-motion support.

  Token-only styling and inline SVG (the kit has no icon dependency). The kit
  holds no text, so the region name and the dismiss button's accessible name
  are the caller's translated `label` and `dismissLabel`. Render it once, in
  the app shell, after `provideToast()`.
-->
<script setup lang="ts">
import { useToast, type ToastType } from '../composables/useToast'

export interface ToastContainerProps {
  /** Accessible name of the notifications region. */
  label: string
  /** Accessible name of each toast's dismiss button. */
  dismissLabel: string
}

defineProps<ToastContainerProps>()

const { toasts, removeToast } = useToast()

const ICON_PATHS: Record<ToastType, string> = {
  success: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',
  error: 'M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z',
  warning:
    'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z',
  info: 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
}
const CLOSE_PATH = 'M6 18L18 6M6 6l12 12'
</script>

<template>
  <Teleport to="body">
    <div class="aui-toasts" role="region" :aria-label="label" aria-live="polite">
      <TransitionGroup name="aui-toast">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          :class="['aui-toast', `aui-toast--${toast.type}`]"
          role="alert"
          :aria-atomic="true"
        >
          <svg
            class="aui-toast__icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path :d="ICON_PATHS[toast.type] ?? ICON_PATHS.info" />
          </svg>
          <span class="aui-toast__message">{{ toast.message }}</span>
          <button
            type="button"
            class="aui-toast__close"
            :aria-label="dismissLabel"
            @click="removeToast(toast.id)"
          >
            <svg
              class="aui-toast__close-icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <path :d="CLOSE_PATH" />
            </svg>
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.aui-toasts {
  position: fixed;
  top: calc(5rem + env(safe-area-inset-top, 0px));
  right: calc(var(--aui-space-5) + env(safe-area-inset-right, 0px));
  z-index: var(--aui-z-toast, calc(var(--aui-z-tooltip) + 100));
  display: flex;
  flex-direction: column;
  gap: var(--aui-space-2);
  max-width: 25rem;
  pointer-events: none;
}

.aui-toast {
  --aui-toast-color: var(--aui-color-info);
  display: flex;
  align-items: center;
  gap: var(--aui-space-3);
  min-width: 18.75rem;
  max-width: 25rem;
  padding: var(--aui-space-3) var(--aui-space-4);
  border: 1px solid color-mix(in srgb, var(--aui-toast-color) 45%, var(--aui-color-surface));
  border-inline-start: 4px solid var(--aui-toast-color);
  border-radius: var(--aui-radius-lg);
  background: var(--aui-color-surface);
  color: var(--aui-color-text);
  box-shadow: var(--aui-shadow-lg);
  font-family: var(--aui-font-sans);
  pointer-events: auto;
}

.aui-toast--info {
  --aui-toast-color: var(--aui-color-info);
}
.aui-toast--success {
  --aui-toast-color: var(--aui-color-success);
}
.aui-toast--warning {
  --aui-toast-color: var(--aui-color-warning);
}
.aui-toast--error {
  --aui-toast-color: var(--aui-color-error);
}

.aui-toast__icon {
  flex-shrink: 0;
  width: 1.25rem;
  height: 1.25rem;
  color: var(--aui-toast-color);
}

.aui-toast__message {
  flex: 1;
  min-width: 0;
  font-size: var(--aui-text-sm);
  font-weight: var(--aui-font-weight-medium);
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.aui-toast__close {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  min-width: 2.75rem;
  min-height: 2.75rem;
  border: none;
  border-radius: var(--aui-radius-full);
  background: transparent;
  color: var(--aui-color-text-muted);
  cursor: pointer;
  transition:
    background var(--aui-transition-fast),
    color var(--aui-transition-fast);
}

.aui-toast__close:hover {
  background: var(--aui-color-surface-sunken);
  color: var(--aui-color-text);
}

.aui-toast__close:focus-visible {
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: 2px;
}

.aui-toast__close-icon {
  width: 1rem;
  height: 1rem;
}

.aui-toast-enter-active {
  animation: aui-toast-in var(--aui-transition) ease-out;
}
.aui-toast-leave-active {
  animation: aui-toast-out var(--aui-transition-fast) ease-in;
}
.aui-toast-move {
  transition: transform var(--aui-transition);
}

@keyframes aui-toast-in {
  from {
    opacity: 0;
    transform: translateX(100%);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

@keyframes aui-toast-out {
  from {
    opacity: 1;
    transform: translateX(0);
  }
  to {
    opacity: 0;
    transform: translateX(100%);
  }
}

@media (max-width: 480px) {
  .aui-toasts {
    right: calc(var(--aui-space-3) + env(safe-area-inset-right, 0px));
    left: calc(var(--aui-space-3) + env(safe-area-inset-left, 0px));
    max-width: none;
  }
  .aui-toast {
    min-width: 0;
    max-width: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .aui-toast-enter-active,
  .aui-toast-leave-active {
    animation: none;
    transition: opacity var(--aui-transition-fast);
  }
  .aui-toast-enter-from,
  .aui-toast-leave-to {
    opacity: 0;
  }
  .aui-toast-move {
    transition: none;
  }
}
</style>
