<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BaseAlert -- the one inline alert/banner for both apps (#18819). It replaces
  the main app's ErrorBanner and ui/BaseAlert and the error banner the SLM
  pasted inline in ~39 views. Token-only styling, no shadow, inline SVG icons
  (the kit has no icon dependency). The kit holds no text, so the dismiss
  button's accessible name is the caller's translated `dismissLabel`.

  error/critical announce assertively (role=alert); the rest politely
  (role=status). Dismissing hides the alert AND emits `dismiss`, so a caller
  that clears its own ref works as well as one that does not.
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, warn, watch, watchEffect } from 'vue'

export type AlertVariant = 'success' | 'info' | 'warning' | 'error' | 'critical'
export type AlertSize = 'default' | 'compact'

export interface BaseAlertProps {
  variant?: AlertVariant
  size?: AlertSize
  title?: string
  /** Text when no default slot is given. */
  message?: string | null
  /** Show the variant icon (the `icon` slot overrides it). */
  icon?: boolean
  /** Shows a dismiss button. Requires `dismissLabel`: the button is icon-only, so it is its only name. */
  dismissible?: boolean
  dismissLabel?: string
  bordered?: boolean
  /** Milliseconds until the alert dismisses itself; 0 keeps it. */
  autoDismiss?: number
}

const props = withDefaults(defineProps<BaseAlertProps>(), {
  variant: 'info',
  size: 'default',
  title: undefined,
  message: '',
  icon: true,
  dismissible: false,
  dismissLabel: undefined,
  bordered: false,
  autoDismiss: 0,
})

const emit = defineEmits<{ dismiss: [] }>()

const ICON_PATHS: Record<AlertVariant, string> = {
  success: 'M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
  info: 'M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z',
  warning:
    'M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z',
  error: 'M9.75 9.75l4.5 4.5m0-4.5l-4.5 4.5M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
  critical: 'M9.75 9.75l4.5 4.5m0-4.5l-4.5 4.5M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
}
const CLOSE_PATH = 'M6 18L18 6M6 6l12 12'

const dismissed = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined

function clearTimer(): void {
  if (timer !== undefined) clearTimeout(timer)
  timer = undefined
}

function startTimer(): void {
  clearTimer()
  timer = props.autoDismiss > 0 ? setTimeout(dismiss, props.autoDismiss) : undefined
}

// A new message is a new alert: it shows again after an earlier dismissal and gets
// its own full auto-dismiss delay, so the previous message's timer cannot cut it short.
watch(
  () => props.message,
  () => {
    dismissed.value = false
    startTimer()
  },
)

// A changed delay applies at once: 0 cancels a pending dismissal, a positive value starts one.
watch(() => props.autoDismiss, () => {
  if (!dismissed.value) startTimer()
})

watchEffect(() => {
  if (props.dismissible && !props.dismissLabel) {
    warn('BaseAlert: `dismissible` needs `dismissLabel`, or its icon-only dismiss button has no accessible name.')
  }
})

const assertive = computed(() => props.variant === 'error' || props.variant === 'critical')
const iconPath = computed(() => ICON_PATHS[props.variant] ?? ICON_PATHS.info)

function dismiss(): void {
  clearTimer() // a manual dismissal must not be followed by the timer's second `dismiss`
  dismissed.value = true
  emit('dismiss')
}

onMounted(startTimer)

onBeforeUnmount(clearTimer)
</script>

<template>
  <div
    v-if="!dismissed"
    :class="[
      'aui-alert',
      `aui-alert--${variant}`,
      `aui-alert--${size}`,
      { 'aui-alert--bordered': bordered },
    ]"
    :role="assertive ? 'alert' : 'status'"
    :aria-live="assertive ? 'assertive' : 'polite'"
  >
    <div v-if="icon" class="aui-alert__icon">
      <slot name="icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" :d="iconPath" />
        </svg>
      </slot>
    </div>
    <div class="aui-alert__content">
      <div v-if="$slots.title || (title && size !== 'compact')" class="aui-alert__title">
        <slot name="title">{{ title }}</slot>
      </div>
      <div class="aui-alert__message"><slot>{{ message }}</slot></div>
    </div>
    <div v-if="$slots.actions || dismissible" class="aui-alert__actions">
      <slot name="actions" />
      <button
        v-if="dismissible"
        type="button"
        class="aui-alert__dismiss"
        :aria-label="dismissLabel"
        @click="dismiss"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" :d="CLOSE_PATH" />
        </svg>
      </button>
    </div>
  </div>
</template>

<style scoped>
.aui-alert {
  --aui-alert-color: var(--aui-color-info);
  display: flex;
  align-items: flex-start;
  gap: var(--aui-space-3);
  padding: var(--aui-space-3) var(--aui-space-4);
  border: 1px solid transparent;
  border-radius: var(--aui-radius-md);
  background-color: color-mix(in srgb, var(--aui-alert-color) 12%, var(--aui-color-surface));
  color: color-mix(in srgb, var(--aui-alert-color) 70%, var(--aui-color-text));
  font-family: var(--aui-font-sans);
  font-size: var(--aui-text-sm);
  line-height: 1.5;
}

.aui-alert--compact {
  align-items: center;
  padding: var(--aui-space-2);
  gap: var(--aui-space-2);
}

.aui-alert--success {
  --aui-alert-color: var(--aui-color-success);
}
.aui-alert--info {
  --aui-alert-color: var(--aui-color-info);
}
.aui-alert--warning {
  --aui-alert-color: var(--aui-color-warning);
}
.aui-alert--error,
.aui-alert--critical {
  --aui-alert-color: var(--aui-color-error);
}
/* Critical is the more severe error: darker text. */
.aui-alert--critical {
  color: color-mix(in srgb, var(--aui-alert-color) 45%, var(--aui-color-text));
}

.aui-alert--bordered {
  border-color: color-mix(in srgb, var(--aui-alert-color) 40%, transparent);
  border-inline-start: 4px solid var(--aui-alert-color);
}

.aui-alert__icon {
  display: flex;
  flex-shrink: 0;
  color: var(--aui-alert-color);
}
.aui-alert__icon svg {
  width: 1.25rem;
  height: 1.25rem;
}
.aui-alert--compact .aui-alert__icon svg {
  width: 1rem;
  height: 1rem;
}

.aui-alert__content {
  flex: 1;
  min-width: 0;
}
.aui-alert__title {
  margin-bottom: var(--aui-space-1);
  font-weight: var(--aui-font-weight-medium);
}

.aui-alert__actions {
  display: flex;
  align-items: center;
  gap: var(--aui-space-2);
  flex-shrink: 0;
  margin-inline-start: auto;
}

.aui-alert__dismiss {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--aui-space-1);
  border: 0;
  border-radius: var(--aui-radius-sm);
  background: transparent;
  color: inherit;
  cursor: pointer;
}
.aui-alert__dismiss:hover {
  background-color: color-mix(in srgb, var(--aui-alert-color) 15%, transparent);
}
.aui-alert__dismiss:focus-visible {
  outline: 2px solid var(--aui-color-primary);
  outline-offset: 2px;
}
.aui-alert__dismiss svg {
  width: 1rem;
  height: 1rem;
}
</style>
