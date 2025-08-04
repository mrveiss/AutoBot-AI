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
  variant?: 'default' | 'bordered' | 'elevated' | 'flat'
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
  @apply bg-white dark:bg-gray-800 transition-all duration-200;
}

.panel-default {
  @apply border border-gray-200 dark:border-gray-700 rounded-lg;
}

.panel-bordered {
  @apply border-2 border-gray-300 dark:border-gray-600 rounded-lg;
}

.panel-elevated {
  @apply shadow-lg rounded-lg border border-gray-100 dark:border-gray-700;
}

.panel-flat {
  @apply bg-gray-50 dark:bg-gray-900;
}

.panel-small {
  @apply text-sm;
}

.panel-medium {
  @apply text-base;
}

.panel-large {
  @apply text-lg;
}

.panel-header {
  @apply flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700;
}

.panel-title {
  @apply text-lg font-semibold text-gray-900 dark:text-gray-100 m-0;
}

.panel-actions {
  @apply flex items-center gap-2;
}

.panel-content {
  @apply p-4;
  max-height: v-bind('props.maxHeight || "none"');
}

.content-scrollable {
  @apply overflow-y-auto;
}

.content-collapsed {
  @apply hidden;
}

.panel-footer {
  @apply p-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-750;
}

.panel-loading {
  @apply opacity-75 pointer-events-none;
}

.panel-loading::after {
  content: '';
  @apply absolute inset-0 bg-white bg-opacity-50 dark:bg-gray-800 dark:bg-opacity-50;
  background-image: url("data:image/svg+xml,%3Csvg width='40' height='40' viewBox='0 0 40 40' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg transform='translate(1 1)' stroke='%23666' stroke-width='2'%3E%3Ccircle stroke-opacity='.25' cx='18' cy='18' r='18'/%3E%3Cpath d='m36 18c0-9.94-8.06-18-18-18'%3E%3CanimateTransform attributeName='transform' type='rotate' from='0 18 18' to='360 18 18' dur='1s' repeatCount='indefinite'/%3E%3C/path%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: center;
  background-size: 40px 40px;
}

/* Responsive adjustments */
@media (max-width: 768px) {
  .panel-header {
    @apply p-3;
  }

  .panel-content {
    @apply p-3;
  }

  .panel-footer {
    @apply p-3;
  }

  .panel-title {
    @apply text-base;
  }
}
</style>
