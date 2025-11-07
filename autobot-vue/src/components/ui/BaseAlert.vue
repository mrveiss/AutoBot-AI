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
  background-color: rgba(0, 0, 0, 0.1);
}

.alert-dismiss:focus {
  outline: none;
  ring: 2px;
  ring-offset: 2px;
}

/* Success variant */
.alert-success {
  background-color: #d1fae5;
  color: #065f46;
}

.alert-success .alert-icon {
  color: #10b981;
}

.alert-success.alert-bordered {
  border: 1px solid #a7f3d0;
  border-left-width: 4px;
  border-left-color: #10b981;
}

/* Info variant */
.alert-info {
  background-color: #dbeafe;
  color: #1e40af;
}

.alert-info .alert-icon {
  color: #3b82f6;
}

.alert-info.alert-bordered {
  border: 1px solid #bfdbfe;
  border-left-width: 4px;
  border-left-color: #3b82f6;
}

/* Warning variant */
.alert-warning {
  background-color: #fef3c7;
  color: #92400e;
}

.alert-warning .alert-icon {
  color: #f59e0b;
}

.alert-warning.alert-bordered {
  border: 1px solid #fde68a;
  border-left-width: 4px;
  border-left-color: #f59e0b;
}

/* Error variant */
.alert-error {
  background-color: #fee2e2;
  color: #991b1b;
}

.alert-error .alert-icon {
  color: #ef4444;
}

.alert-error.alert-bordered {
  border: 1px solid #fecaca;
  border-left-width: 4px;
  border-left-color: #ef4444;
}

/* Critical variant (more severe than error) */
.alert-critical {
  background-color: #fef2f2;
  color: #7f1d1d;
}

.alert-critical .alert-icon {
  color: #dc2626;
}

.alert-critical.alert-bordered {
  border: 1px solid #fecaca;
  border-left-width: 4px;
  border-left-color: #dc2626;
}

/* Dark mode support */
@media (prefers-color-scheme: dark) {
  .alert-success {
    background-color: rgba(16, 185, 129, 0.1);
    color: #6ee7b7;
  }

  .alert-info {
    background-color: rgba(59, 130, 246, 0.1);
    color: #93c5fd;
  }

  .alert-warning {
    background-color: rgba(245, 158, 11, 0.1);
    color: #fcd34d;
  }

  .alert-error {
    background-color: rgba(239, 68, 68, 0.1);
    color: #fca5a5;
  }

  .alert-critical {
    background-color: rgba(220, 38, 38, 0.1);
    color: #f87171;
  }

  .alert-dismiss:hover {
    background-color: rgba(255, 255, 255, 0.1);
  }
}

.dark .alert-success {
  background-color: rgba(16, 185, 129, 0.1);
  color: #6ee7b7;
}

.dark .alert-info {
  background-color: rgba(59, 130, 246, 0.1);
  color: #93c5fd;
}

.dark .alert-warning {
  background-color: rgba(245, 158, 11, 0.1);
  color: #fcd34d;
}

.dark .alert-error {
  background-color: rgba(239, 68, 68, 0.1);
  color: #fca5a5;
}

.dark .alert-critical {
  background-color: rgba(220, 38, 38, 0.1);
  color: #f87171;
}

.dark .alert-dismiss:hover {
  background-color: rgba(255, 255, 255, 0.1);
}
</style>
