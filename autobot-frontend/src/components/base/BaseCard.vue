<template>
  <div class="base-card" :class="cardClasses">
    <!-- Card Header -->
    <div v-if="$slots.header || title" class="card-header" :class="headerClasses">
      <div class="header-content">
        <slot name="header">
          <h3 class="card-title">{{ title }}</h3>
          <p v-if="subtitle" class="card-subtitle">{{ subtitle }}</p>
        </slot>
      </div>
      <div v-if="$slots.actions" class="card-actions">
        <slot name="actions"></slot>
      </div>
    </div>

    <!-- Card Body -->
    <div class="card-body" :class="bodyClasses">
      <slot></slot>
    </div>

    <!-- Card Footer -->
    <div v-if="$slots.footer" class="card-footer" :class="footerClasses">
      <slot name="footer"></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watchEffect } from 'vue'
import { createLogger } from '@/utils/debugUtils'

const CARD_SIZES = ['sm', 'md', 'lg'] as const
const CARD_VARIANTS = ['default', 'bordered', 'elevated', 'flat'] as const

const logger = createLogger('BaseCard')

interface Props {
  title?: string
  subtitle?: string
  variant?: 'default' | 'bordered' | 'elevated' | 'flat'
  size?: 'sm' | 'md' | 'lg'
  hoverable?: boolean
  loading?: boolean
  noPadding?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'default',
  size: 'md',
  hoverable: false,
  loading: false,
  noPadding: false
})

const cardClasses = computed(() => [
  `card-${props.variant}`,
  `card-${props.size}`,
  {
    'card-hoverable': props.hoverable,
    'card-loading': props.loading
  }
])

const headerClasses = computed(() => ({
  'header-no-padding': props.noPadding
}))

const bodyClasses = computed(() => ({
  'body-no-padding': props.noPadding
}))

const footerClasses = computed(() => ({
  'footer-no-padding': props.noPadding
}))

if (import.meta.env.DEV) {
  watchEffect(() => {
    if (props.size !== undefined && !(CARD_SIZES as readonly string[]).includes(props.size)) {
      logger.warn(`Invalid "size" prop: "${props.size}". Expected: ${CARD_SIZES.join(' | ')}`)
    }
    if (props.variant !== undefined && !(CARD_VARIANTS as readonly string[]).includes(props.variant)) {
      logger.warn(`Invalid "variant" prop: "${props.variant}". Expected: ${CARD_VARIANTS.join(' | ')}`)
    }
  })
}
</script>

<style scoped>
/* Issue #901: Technical Precision Card Design */
/* Issue #4005: Added CSS containment for performance optimization */

.base-card {
  background-color: var(--bg-card);
  transition: all var(--duration-150) var(--ease-in-out);
  position: relative;
  overflow: hidden;
  contain: layout style;
}

/* Variant Styles */
.card-default {
  border: 1px solid var(--border-default);
  border-radius: var(--radius-default);
}

.card-bordered {
  border: 2px solid var(--border-strong);
  border-radius: var(--radius-default);
}

.card-elevated {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-default);
  box-shadow: var(--shadow-md);
}

.card-flat {
  background-color: var(--bg-secondary);
  border-radius: var(--radius-default);
}

/* Hover Effect */
.card-hoverable {
  cursor: pointer;
}

.card-hoverable:hover {
  border-color: var(--border-strong);
  box-shadow: var(--shadow-lg);
  transform: translateY(-1px);
}

/* Size Variants */
.card-sm {
  font-size: var(--text-sm);
}

.card-md {
  font-size: var(--text-sm);
}

.card-lg {
  font-size: var(--text-base);
}

/* Card Header */
.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: var(--spacing-4);
  border-bottom: 1px solid var(--border-default);
  background-color: var(--bg-card);
}

.header-no-padding {
  padding: var(--spacing-0);
  border-bottom: none;
}

.header-content {
  flex: 1;
  min-width: 0;
}

.card-title {
  margin: var(--spacing-0);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-sans);
  line-height: 1.5;
}

.card-subtitle {
  margin: var(--spacing-1) var(--spacing-0) var(--spacing-0) var(--spacing-0);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: 1.4;
}

.card-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-left: var(--spacing-3);
}

/* Card Body */
.card-body {
  padding: var(--spacing-4);
  color: var(--text-primary);
}

.body-no-padding {
  padding: var(--spacing-0);
}

/* Card Footer */
.card-footer {
  padding: var(--spacing-3) var(--spacing-4);
  border-top: 1px solid var(--border-default);
  background-color: var(--bg-secondary);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-3);
}

.footer-no-padding {
  padding: var(--spacing-0);
  border-top: none;
  background-color: transparent;
}

/* Loading State */
.card-loading {
  pointer-events: none;
}

.card-loading::after {
  content: '';
  position: absolute;
  inset: 0;
  background-color: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(1px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
}

/* Dark Mode Loading Overlay */
@media (prefers-color-scheme: dark) {
  .card-loading::after {
    background-color: rgba(0, 0, 0, 0.6);
  }
}

/* Responsive Adjustments */
@media (max-width: 640px) {
  .card-header {
    flex-direction: column;
    align-items: stretch;
    gap: var(--spacing-3);
  }

  .card-actions {
    margin-left: var(--spacing-0);
    margin-top: var(--spacing-2);
  }

  .card-body {
    padding: var(--spacing-3);
  }

  .card-footer {
    padding: var(--spacing-2-5) var(--spacing-3);
    flex-wrap: wrap;
  }
}
</style>
