<template>
  <div class="base-panel" :class="panelClasses">
    <div class="panel-header" v-if="$slots.header || title">
      <slot name="header">
        <h3 class="panel-title">{{ title }}</h3>
      </slot>
      <div class="panel-actions" v-if="$slots.actions">
        <slot name="actions"></slot>
      </div>
    </div>

    <div class="panel-content" :class="contentClasses">
      <slot></slot>
    </div>

    <div class="panel-footer" v-if="$slots.footer">
      <slot name="footer"></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  title?: string
  variant?: 'default' | 'bordered' | 'elevated' | 'flat' | 'dark'
  size?: 'small' | 'medium' | 'large'
  loading?: boolean
  collapsible?: boolean
  collapsed?: boolean
  maxHeight?: string
  scrollable?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'default',
  size: 'medium',
  loading: false,
  collapsible: false,
  collapsed: false,
  scrollable: true
})

const emit = defineEmits<{
  toggle: [collapsed: boolean]
}>()

const panelClasses = computed(() => [
  `panel-${props.variant}`,
  `panel-${props.size}`,
  {
    'panel-loading': props.loading,
    'panel-collapsible': props.collapsible,
    'panel-collapsed': props.collapsed
  }
])

const contentClasses = computed(() => [
  {
    'content-scrollable': props.scrollable,
    'content-collapsed': props.collapsed
  }
])

const toggleCollapse = () => {
  if (props.collapsible) {
    emit('toggle', !props.collapsed)
  }
}
</script>

<style scoped>
/** Issue #704: Migrated to design tokens */
.base-panel {
  background-color: var(--bg-primary);
  transition: all var(--duration-200) ease;
}

.panel-default {
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
}

.panel-bordered {
  border: 2px solid var(--border-strong);
  border-radius: var(--radius-lg);
}

.panel-elevated {
  box-shadow: var(--shadow-lg);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-subtle);
}

.panel-flat {
  background-color: var(--bg-secondary);
}

.panel-dark {
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
}

.panel-dark .panel-header {
  border-bottom-color: var(--border-default);
}

.panel-dark .panel-title {
  color: var(--text-primary);
}

.panel-dark .panel-footer {
  border-top-color: var(--border-default);
  background-color: var(--bg-tertiary);
}

.panel-small {
  font-size: var(--text-sm);
}

.panel-medium {
  font-size: var(--text-base);
}

.panel-large {
  font-size: var(--text-lg);
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-4);
  border-bottom: 1px solid var(--border-default);
}

.panel-title {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0;
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.panel-content {
  padding: var(--spacing-4);
  max-height: v-bind('props.maxHeight || "none"');
}

.content-scrollable {
  overflow-y: auto;
}

.content-collapsed {
  display: none;
}

.panel-footer {
  padding: var(--spacing-4);
  border-top: 1px solid var(--border-default);
  background-color: var(--bg-secondary);
}

.panel-loading {
  opacity: 0.75;
  pointer-events: none;
}

.panel-loading::after {
  content: '';
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  background-color: var(--overlay-backdrop);
  background-image: url("data:image/svg+xml,%3Csvg width='40' height='40' viewBox='0 0 40 40' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg transform='translate(1 1)' stroke='%23666' stroke-width='2'%3E%3Ccircle stroke-opacity='.25' cx='18' cy='18' r='18'/%3E%3Cpath d='m36 18c0-9.94-8.06-18-18-18'%3E%3CanimateTransform attributeName='transform' type='rotate' from='0 18 18' to='360 18 18' dur='1s' repeatCount='indefinite'/%3E%3C/path%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: center;
  background-size: 40px 40px;
}

/* Responsive adjustments */
@media (max-width: 768px) {
  .panel-header {
    padding: var(--spacing-3);
  }

  .panel-content {
    padding: var(--spacing-3);
  }

  .panel-footer {
    padding: var(--spacing-3);
  }

  .panel-title {
    font-size: var(--text-base);
  }
}
</style>
