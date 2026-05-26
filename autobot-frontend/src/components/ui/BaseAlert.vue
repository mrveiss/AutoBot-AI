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
        <component :is="defaultIcon" :class="iconSizeClass" />
      </slot>
    </div>

    <!-- Content -->
    <div class="alert-content">
      <!-- title is suppressed in compact size -->
      <div v-if="title && size !== 'compact'" class="alert-title">{{ title }}</div>
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
        :aria-label="t('ui.alert.dismissAlert')"
      >
        <XMarkIcon class="h-4 w-4" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watchEffect } from 'vue'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/debugUtils'
import {
  CheckCircleIcon,
  InformationCircleIcon,
  ExclamationTriangleIcon,
  XCircleIcon,
  XMarkIcon
} from '@heroicons/vue/24/outline'

const ALERT_VARIANTS = ['success', 'info', 'warning', 'error', 'critical'] as const
const ALERT_SIZES = ['default', 'compact'] as const

const logger = createLogger('BaseAlert')

export interface BaseAlertProps {
  variant?: 'success' | 'info' | 'warning' | 'error' | 'critical'
  size?: 'default' | 'compact'
  title?: string
  message?: string
  icon?: boolean
  dismissible?: boolean
  bordered?: boolean
  autoDismiss?: number // milliseconds
}

const props = withDefaults(defineProps<BaseAlertProps>(), {
  variant: 'info',
  size: 'default',
  message: '',
  icon: true,
  dismissible: false,
  bordered: false,
  autoDismiss: 0
})

const emit = defineEmits<{
  dismiss: []
}>()

const { t } = useI18n()

const dismissed = ref(false)

const showIcon = computed(() => props.icon !== false)

// role="alert" is a static attribute on the root element.
// Screen readers announce on DOM insertion (mount). No JS re-trigger needed.
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

// compact: 16px (h-4 w-4); default: 20px (h-5 w-5)
const iconSizeClass = computed(() => (props.size === 'compact' ? 'h-4 w-4' : 'h-5 w-5'))

const alertClasses = computed(() => {
  const classes = [`alert-${props.variant}`]
  if (props.bordered) {
    classes.push('alert-bordered')
  }
  if (props.size === 'compact') {
    classes.push('alert-compact')
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

if (import.meta.env.DEV) {
  watchEffect(() => {
    if (props.variant !== undefined && !(ALERT_VARIANTS as readonly string[]).includes(props.variant)) {
      logger.warn(`Invalid "variant" prop: "${props.variant}". Expected: ${ALERT_VARIANTS.join(' | ')}`)
    }
    if (props.size !== undefined && !(ALERT_SIZES as readonly string[]).includes(props.size)) {
      logger.warn(`Invalid "size" prop: "${props.size}". Expected: ${ALERT_SIZES.join(' | ')}`)
    }
  })
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.base-alert {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-3);
  padding: var(--spacing-3) var(--spacing-4);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  line-height: 1.25rem;
  transition: all var(--duration-200) var(--ease-out);
}

/* compact size: single-line layout, reduced padding (--spacing-2), smaller icon (16px) */
.alert-compact {
  align-items: center;
  padding: var(--spacing-2);
  gap: var(--spacing-2);
}

.alert-compact .alert-message {
  line-height: 1.25rem;
}

.alert-icon {
  flex-shrink: 0;
  margin-top: var(--spacing-0-5);
}

.alert-compact .alert-icon {
  margin-top: 0;
}

.alert-content {
  flex: 1;
  min-width: 0;
}

.alert-title {
  font-weight: 600;
  margin-bottom: var(--spacing-1);
}

.alert-message {
  line-height: 1.5;
}

.alert-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  flex-shrink: 0;
  margin-left: auto;
}

.alert-dismiss {
  padding: var(--spacing-1);
  border-radius: var(--radius-default);
  transition: background-color var(--duration-200) var(--ease-out);
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
}
.alert-dismiss:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
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
