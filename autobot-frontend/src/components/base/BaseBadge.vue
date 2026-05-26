<template>
  <span :class="badgeClasses" class="base-badge">
    <slot name="icon" v-if="$slots.icon"></slot>
    <span class="badge-text"><slot>{{ label }}</slot></span>
    <button
      v-if="removable"
      type="button"
      class="badge-remove"
      @click="handleRemove"
      :aria-label="t('base.badge.removeBadge')"
    >
      <svg class="remove-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
      </svg>
    </button>
  </span>
</template>

<script setup lang="ts">
import { computed, watchEffect } from 'vue'
import { useI18n } from 'vue-i18n'
import type { BadgeVariant } from '@/types/component-props'
import { createLogger } from '@/utils/debugUtils'

const BADGE_SIZES = ['xs', 'sm', 'md', 'lg'] as const
const BADGE_VARIANTS: BadgeVariant[] = ['default', 'primary', 'success', 'warning', 'error', 'info']

const logger = createLogger('BaseBadge')

interface Props {
  label?: string
  variant?: BadgeVariant
  size?: 'xs' | 'sm' | 'md' | 'lg'
  rounded?: boolean
  outline?: boolean
  removable?: boolean
  monospace?: boolean
}

const { t } = useI18n()

const props = withDefaults(defineProps<Props>(), {
  variant: 'default',
  size: 'sm',
  rounded: true,
  outline: false,
  removable: false,
  monospace: false
})

const emit = defineEmits<{
  remove: []
}>()

const badgeClasses = computed(() => [
  `badge-${props.variant}`,
  `badge-${props.size}`,
  {
    'badge-rounded': props.rounded,
    'badge-outline': props.outline,
    'badge-removable': props.removable,
    'badge-monospace': props.monospace
  }
])

const handleRemove = (event: MouseEvent) => {
  event.stopPropagation()
  emit('remove')
}

if (import.meta.env.DEV) {
  watchEffect(() => {
    if (props.size !== undefined && !(BADGE_SIZES as readonly string[]).includes(props.size)) {
      logger.warn(`Invalid "size" prop: "${props.size}". Expected: ${BADGE_SIZES.join(' | ')}`)
    }
    if (props.variant !== undefined && !BADGE_VARIANTS.includes(props.variant)) {
      logger.warn(`Invalid "variant" prop: "${props.variant}". Expected: ${BADGE_VARIANTS.join(' | ')}`)
    }
  })
}
</script>

<style scoped>
/* Issue #901: Technical Precision Badge Design */

.base-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  font-weight: 500;
  white-space: nowrap;
  transition: all var(--duration-150) var(--ease-out);
  line-height: 1;
  font-family: var(--font-sans);
}

.badge-monospace {
  font-family: var(--font-mono);
  font-weight: 400;
  letter-spacing: 0;
}

/* Size Variants */
.badge-xs {
  height: 16px;
  padding: var(--spacing-0) var(--spacing-1-5);
  font-size: var(--text-xs);
  border-radius: var(--radius-lg);
}

.badge-sm {
  height: 20px;
  padding: var(--spacing-0) var(--spacing-2);
  font-size: var(--text-xs);
  border-radius: var(--radius-xl);
}

.badge-md {
  height: 24px;
  padding: var(--spacing-0) var(--spacing-2-5);
  font-size: var(--text-xs);
  border-radius: var(--radius-xl);
}

.badge-lg {
  height: 28px;
  padding: var(--spacing-0) var(--spacing-3);
  font-size: var(--text-sm);
  border-radius: var(--radius-2xl);
}

/* Rounded Variants */
.badge-rounded.badge-xs {
  border-radius: var(--radius-xs);
}

.badge-rounded.badge-sm,
.badge-rounded.badge-md {
  border-radius: var(--radius-xs);
}

.badge-rounded.badge-lg {
  border-radius: var(--radius-default);
}

/* Color Variants - Solid */
.badge-default {
  background-color: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
}

.badge-primary {
  background-color: var(--color-info-bg);
  color: var(--color-info);
  border: 1px solid transparent;
}

.badge-success {
  background-color: var(--color-success-bg);
  color: var(--color-success-dark);
  border: 1px solid transparent;
}

.badge-warning {
  background-color: var(--color-warning-bg);
  color: var(--color-warning-dark);
  border: 1px solid transparent;
}

.badge-error {
  background-color: var(--color-error-bg);
  color: var(--color-error-dark);
  border: 1px solid transparent;
}

.badge-info {
  background-color: var(--color-info-bg);
  color: var(--color-info-dark);
  border: 1px solid transparent;
}

/* Outline Variants */
.badge-outline.badge-default {
  background-color: transparent;
  color: var(--text-primary);
  border-color: var(--border-default);
}

.badge-outline.badge-primary {
  background-color: transparent;
  color: var(--color-info);
  border-color: var(--color-info);
}

.badge-outline.badge-success {
  background-color: transparent;
  color: var(--color-success);
  border-color: var(--color-success);
}

.badge-outline.badge-warning {
  background-color: transparent;
  color: var(--color-warning);
  border-color: var(--color-warning);
}

.badge-outline.badge-error {
  background-color: transparent;
  color: var(--color-error);
  border-color: var(--color-error);
}

.badge-outline.badge-info {
  background-color: transparent;
  color: var(--color-info);
  border-color: var(--color-info);
}

/* Badge Text */
.badge-text {
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.badge-monospace .badge-text {
  text-transform: none;
  letter-spacing: 0;
}

/* Removable Badge */
.badge-removable {
  padding-right: var(--spacing-1);
}

.badge-remove {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-0-5);
  background: transparent;
  border: none;
  color: currentColor;
  cursor: pointer;
  border-radius: 50%;
  transition: all var(--duration-150) var(--ease-out);
  opacity: 0.6;
}

.badge-remove:hover {
  opacity: 1;
  background-color: rgba(0, 0, 0, 0.1);
}

.remove-icon {
  width: 10px;
  height: 10px;
  stroke-width: 2.5;
}

/* Icon Slot */
.base-badge :deep(.icon) {
  width: 12px;
  height: 12px;
}

.badge-xs :deep(.icon) {
  width: 10px;
  height: 10px;
}

.badge-lg :deep(.icon) {
  width: 14px;
  height: 14px;
}

/* Hover Effects (for interactive badges) */
.base-badge:has(button) {
  cursor: default;
}

/* Dark Mode Adjustments */
@media (prefers-color-scheme: dark) {
  .badge-default {
    background-color: var(--bg-tertiary);
    border-color: var(--border-default);
  }

  .badge-remove:hover {
    background-color: rgba(255, 255, 255, 0.15);
  }
}
</style>
