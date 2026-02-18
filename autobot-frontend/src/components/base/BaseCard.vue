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
import { computed } from 'vue'

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
</script>

<style scoped>
/* Issue #901: Technical Precision Card Design */

.base-card {
  background-color: var(--bg-card);
  transition: all 150ms cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;
}

/* Variant Styles */
.card-default {
  border: 1px solid var(--border-default);
  border-radius: 4px;
}

.card-bordered {
  border: 2px solid var(--border-strong);
  border-radius: 4px;
}

.card-elevated {
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  box-shadow: var(--shadow-md);
}

.card-flat {
  background-color: var(--bg-secondary);
  border-radius: 4px;
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
  font-size: 13px;
}

.card-md {
  font-size: 14px;
}

.card-lg {
  font-size: 16px;
}

/* Card Header */
.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid var(--border-default);
  background-color: var(--bg-card);
}

.header-no-padding {
  padding: 0;
  border-bottom: none;
}

.header-content {
  flex: 1;
  min-width: 0;
}

.card-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-sans);
  line-height: 1.5;
}

.card-subtitle {
  margin: 4px 0 0 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.card-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: 12px;
}

/* Card Body */
.card-body {
  padding: 16px;
  color: var(--text-primary);
}

.body-no-padding {
  padding: 0;
}

/* Card Footer */
.card-footer {
  padding: 12px 16px;
  border-top: 1px solid var(--border-default);
  background-color: var(--bg-secondary);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.footer-no-padding {
  padding: 0;
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
    gap: 12px;
  }

  .card-actions {
    margin-left: 0;
    margin-top: 8px;
  }

  .card-body {
    padding: 12px;
  }

  .card-footer {
    padding: 10px 12px;
    flex-wrap: wrap;
  }
}
</style>
