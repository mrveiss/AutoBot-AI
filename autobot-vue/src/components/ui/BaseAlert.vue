<template>
  <div
    v-if="!dismissed"
    :class="alertClasses"
    class="base-alert"
    role="alert"
  >
    <!-- Icon -->
    <div v-if="showIcon" class="alert-icon">
      <slot name="icon">
        <component :is="defaultIcon" class="h-5 w-5" />
      </slot>
    </div>

    <!-- Content -->
    <div class="alert-content">
      <div v-if="title" class="alert-title">{{ title }}</div>
      <div class="alert-message">
        <slot>{{ message }}</slot>
      </div>
    </div>

    <!-- Actions -->
    <div v-if="$slots.actions || dismissible" class="alert-actions">
      <slot name="actions"></slot>
      <button
        v-if="dismissible"
        @click="dismiss"
        class="alert-dismiss"
        aria-label="Dismiss alert"
      >
        <XMarkIcon class="h-4 w-4" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  CheckCircleIcon,
  InformationCircleIcon,
  ExclamationTriangleIcon,
  XCircleIcon,
  XMarkIcon
} from '@heroicons/vue/24/outline'

export interface BaseAlertProps {
  variant?: 'success' | 'info' | 'warning' | 'error' | 'critical'
  title?: string
  message?: string
  icon?: boolean
  dismissible?: boolean
  bordered?: boolean
  autoDismiss?: number // milliseconds
}

const props = withDefaults(defineProps<BaseAlertProps>(), {
  variant: 'info',
  message: '',
  icon: true,
  dismissible: false,
  bordered: false,
  autoDismiss: 0
})

const emit = defineEmits<{
  dismiss: []
}>()

const dismissed = ref(false)

const showIcon = computed(() => props.icon !== false)

const defaultIcon = computed(() => {
  switch (props.variant) {
    case 'success':
      return CheckCircleIcon
    case 'warning':
      return ExclamationTriangleIcon
    case 'error':
    case 'critical':
      return XCircleIcon
    case 'info':
    default:
      return InformationCircleIcon
  }
})

const alertClasses = computed(() => {
  const classes = [`alert-${props.variant}`]
  if (props.bordered) {
    classes.push('alert-bordered')
  }
  return classes
})

const dismiss = () => {
  dismissed.value = true
  emit('dismiss')
}

// Auto-dismiss logic
onMounted(() => {
  if (props.autoDismiss && props.autoDismiss > 0) {
    setTimeout(() => {
      dismiss()
    }, props.autoDismiss)
  }
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.base-alert {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  border-radius: 0.5rem;
  font-size: 0.875rem;
  line-height: 1.25rem;
  transition: all 0.2s ease;
}

.alert-icon {
  flex-shrink: 0;
  margin-top: 0.125rem;
}

.alert-content {
  flex: 1;
  min-width: 0;
}

.alert-title {
  font-weight: 600;
  margin-bottom: 0.25rem;
}

.alert-message {
  line-height: 1.5;
}

.alert-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
  margin-left: auto;
}

.alert-dismiss {
  padding: 0.25rem;
  border-radius: 0.25rem;
  transition: background-color 0.2s ease;
  background: transparent;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.alert-dismiss:hover {
  background-color: var(--bg-hover-alpha-10);
}

.alert-dismiss:focus {
  outline: none;
  ring: 2px;
  ring-offset: 2px;
}

/* Success variant */
.alert-success {
  background-color: var(--color-success-bg);
  color: var(--color-success-dark);
}

.alert-success .alert-icon {
  color: var(--color-success);
}

.alert-success.alert-bordered {
  border: 1px solid var(--color-success-light);
  border-left-width: 4px;
  border-left-color: var(--color-success);
}

/* Info variant */
.alert-info {
  background-color: var(--color-info-bg);
  color: var(--color-info-dark);
}

.alert-info .alert-icon {
  color: var(--color-primary);
}

.alert-info.alert-bordered {
  border: 1px solid var(--color-info-light);
  border-left-width: 4px;
  border-left-color: var(--color-primary);
}

/* Warning variant */
.alert-warning {
  background-color: var(--color-warning-bg);
  color: var(--color-warning-darker);
}

.alert-warning .alert-icon {
  color: var(--color-warning);
}

.alert-warning.alert-bordered {
  border: 1px solid var(--color-warning-light);
  border-left-width: 4px;
  border-left-color: var(--color-warning);
}

/* Error variant */
.alert-error {
  background-color: var(--color-error-bg);
  color: var(--color-error-dark);
}

.alert-error .alert-icon {
  color: var(--color-error);
}

.alert-error.alert-bordered {
  border: 1px solid var(--color-error-light);
  border-left-width: 4px;
  border-left-color: var(--color-error);
}

/* Critical variant (more severe than error) */
.alert-critical {
  background-color: var(--color-error-bg);
  color: var(--color-error-darker);
}

.alert-critical .alert-icon {
  color: var(--color-error-dark);
}

.alert-critical.alert-bordered {
  border: 1px solid var(--color-error-light);
  border-left-width: 4px;
  border-left-color: var(--color-error-dark);
}

/* Note: Dark mode is handled automatically by CSS custom properties */
</style>
