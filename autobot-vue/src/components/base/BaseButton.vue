<template>
  <component
    :is="tag"
    :class="buttonClasses"
    :disabled="disabled || loading"
    :type="htmlType"
    @click="handleClick"
  >
    <span v-if="loading" class="button-spinner"></span>
    <slot name="icon-left" v-if="$slots['icon-left'] && !loading"></slot>
    <span class="button-content" v-if="$slots.default || label">
      <slot>{{ label }}</slot>
    </span>
    <slot name="icon-right" v-if="$slots['icon-right'] && !loading"></slot>
  </component>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  variant?: 'primary' | 'secondary' | 'success' | 'danger' | 'warning' | 'info' | 'light' | 'dark' | 'outline' | 'ghost' | 'link'
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  disabled?: boolean
  loading?: boolean
  block?: boolean
  rounded?: boolean
  label?: string
  htmlType?: 'button' | 'submit' | 'reset'
  tag?: string
  to?: string | object
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'primary',
  size: 'md',
  disabled: false,
  loading: false,
  block: false,
  rounded: false,
  htmlType: 'button',
  tag: 'button'
})

const emit = defineEmits<{
  click: [event: MouseEvent]
}>()

const buttonClasses = computed(() => [
  'base-button',
  `btn-${props.variant}`,
  `btn-${props.size}`,
  {
    'btn-block': props.block,
    'btn-rounded': props.rounded,
    'btn-loading': props.loading,
    'btn-disabled': props.disabled
  }
])

const handleClick = (event: MouseEvent) => {
  if (!props.disabled && !props.loading) {
    emit('click', event)
  }
}
</script>

<style scoped>
.base-button {
  @apply inline-flex items-center justify-center font-medium transition-all duration-200
         focus:outline-none focus:ring-2 focus:ring-offset-2 active:scale-[0.98]
         border border-transparent cursor-pointer select-none;
}

/* Size variants */
.btn-xs {
  @apply px-2.5 py-1.5 text-xs rounded;
}

.btn-sm {
  @apply px-3 py-2 text-sm rounded;
}

.btn-md {
  @apply px-4 py-2 text-sm rounded-md;
}

.btn-lg {
  @apply px-6 py-3 text-base rounded-md;
}

.btn-xl {
  @apply px-8 py-4 text-lg rounded-lg;
}

/* Color variants */
.btn-primary {
  @apply bg-blue-600 text-white hover:bg-blue-700 focus:ring-blue-500
         dark:bg-blue-500 dark:hover:bg-blue-600;
}

.btn-secondary {
  @apply bg-gray-600 text-white hover:bg-gray-700 focus:ring-gray-500
         dark:bg-gray-500 dark:hover:bg-gray-600;
}

.btn-success {
  @apply bg-green-600 text-white hover:bg-green-700 focus:ring-green-500
         dark:bg-green-500 dark:hover:bg-green-600;
}

.btn-danger {
  @apply bg-red-600 text-white hover:bg-red-700 focus:ring-red-500
         dark:bg-red-500 dark:hover:bg-red-600;
}

.btn-warning {
  @apply bg-yellow-600 text-white hover:bg-yellow-700 focus:ring-yellow-500
         dark:bg-yellow-500 dark:hover:bg-yellow-600;
}

.btn-info {
  @apply bg-cyan-600 text-white hover:bg-cyan-700 focus:ring-cyan-500
         dark:bg-cyan-500 dark:hover:bg-cyan-600;
}

.btn-light {
  @apply bg-gray-100 text-gray-900 hover:bg-gray-200 focus:ring-gray-500
         dark:bg-gray-200 dark:text-gray-800 dark:hover:bg-gray-300;
}

.btn-dark {
  @apply bg-gray-800 text-white hover:bg-gray-900 focus:ring-gray-700
         dark:bg-gray-700 dark:hover:bg-gray-800;
}

.btn-outline {
  @apply bg-transparent border-current text-gray-700 hover:bg-gray-700 hover:text-white
         dark:text-gray-300 dark:hover:bg-gray-300 dark:hover:text-gray-800;
}

.btn-ghost {
  @apply bg-transparent text-gray-700 hover:bg-gray-100
         dark:text-gray-300 dark:hover:bg-gray-800;
}

.btn-link {
  @apply bg-transparent text-blue-600 hover:text-blue-700 underline hover:no-underline
         dark:text-blue-400 dark:hover:text-blue-300;
}

/* State variants */
.btn-block {
  @apply w-full;
}

.btn-rounded {
  @apply rounded-full;
}

.btn-disabled {
  @apply opacity-50 cursor-not-allowed pointer-events-none;
}

.btn-loading {
  @apply cursor-wait;
}

/* Loading spinner */
.button-spinner {
  @apply inline-block w-4 h-4 mr-2 border-2 border-current border-t-transparent
         rounded-full animate-spin;
}

/* Button content spacing */
.button-content {
  @apply flex items-center gap-2;
}

/* Icon spacing */
.base-button :slotted(.icon) {
  @apply w-4 h-4;
}

/* Focus states for accessibility */
.base-button:focus-visible {
  @apply ring-2 ring-offset-2 ring-blue-500;
}

/* Hover animations */
.base-button:hover:not(.btn-disabled):not(.btn-loading) {
  @apply transform scale-[1.02];
}

.base-button:active:not(.btn-disabled):not(.btn-loading) {
  @apply transform scale-[0.98];
}

/* Dark mode adjustments */
@media (prefers-color-scheme: dark) {
  .base-button {
    @apply focus:ring-offset-gray-800;
  }
}

/* Responsive adjustments */
@media (max-width: 640px) {
  .btn-lg {
    @apply px-4 py-2 text-base;
  }

  .btn-xl {
    @apply px-6 py-3 text-base;
  }
}
</style>
