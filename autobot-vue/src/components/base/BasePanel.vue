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
.base-panel {
  background-color: white;
  transition: all 0.2s ease;
}

.panel-default {
  border: 1px solid var(--blue-gray-200);
  border-radius: 0.5rem;
}

.panel-bordered {
  border: 2px solid var(--blue-gray-300);
  border-radius: 0.5rem;
}

.panel-elevated {
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
  border-radius: 0.5rem;
  border: 1px solid var(--blue-gray-100);
}

.panel-flat {
  background-color: var(--blue-gray-50);
}

.panel-dark {
  background-color: #1a1a2e;
  border: 1px solid #2a2a3e;
  border-radius: 0.5rem;
}

.panel-dark .panel-header {
  border-bottom-color: #2a2a3e;
}

.panel-dark .panel-title {
  color: #f9fafb;
}

.panel-dark .panel-footer {
  border-top-color: #2a2a3e;
  background-color: #111827;
}

.panel-small {
  font-size: 0.875rem;
}

.panel-medium {
  font-size: 1rem;
}

.panel-large {
  font-size: 1.125rem;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem;
  border-bottom: 1px solid var(--blue-gray-200);
}

.panel-title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--blue-gray-900);
  margin: 0;
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.panel-content {
  padding: 1rem;
  max-height: v-bind('props.maxHeight || "none"');
}

.content-scrollable {
  overflow-y: auto;
}

.content-collapsed {
  display: none;
}

.panel-footer {
  padding: 1rem;
  border-top: 1px solid var(--blue-gray-200);
  background-color: var(--blue-gray-50);
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
  background-color: rgba(255, 255, 255, 0.5);
  background-image: url("data:image/svg+xml,%3Csvg width='40' height='40' viewBox='0 0 40 40' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg transform='translate(1 1)' stroke='%23666' stroke-width='2'%3E%3Ccircle stroke-opacity='.25' cx='18' cy='18' r='18'/%3E%3Cpath d='m36 18c0-9.94-8.06-18-18-18'%3E%3CanimateTransform attributeName='transform' type='rotate' from='0 18 18' to='360 18 18' dur='1s' repeatCount='indefinite'/%3E%3C/path%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: center;
  background-size: 40px 40px;
}

/* Responsive adjustments */
@media (max-width: 768px) {
  .panel-header {
    padding: 0.75rem;
  }

  .panel-content {
    padding: 0.75rem;
  }

  .panel-footer {
    padding: 0.75rem;
  }

  .panel-title {
    font-size: 1rem;
  }
}
</style>
