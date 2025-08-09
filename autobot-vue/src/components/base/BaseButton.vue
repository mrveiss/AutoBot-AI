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
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 500;
  transition: all 0.2s ease;
  border: 1px solid transparent;
  cursor: pointer;
  user-select: none;
}

.base-button:focus {
  outline: none;
  box-shadow: 0 0 0 2px var(--indigo-500);
}

.base-button:active:not(.btn-disabled):not(.btn-loading) {
  transform: scale(0.98);
}

/* Size variants */
.btn-xs {
  padding: 0.375rem 0.625rem;
  font-size: 0.75rem;
  border-radius: 0.25rem;
}

.btn-sm {
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
  border-radius: 0.25rem;
}

.btn-md {
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
  border-radius: 0.375rem;
}

.btn-lg {
  padding: 0.75rem 1.5rem;
  font-size: 1rem;
  border-radius: 0.375rem;
}

.btn-xl {
  padding: 1rem 2rem;
  font-size: 1.125rem;
  border-radius: 0.5rem;
}

/* Color variants */
.btn-primary {
  background-color: var(--indigo-500);
  color: white;
}

.btn-primary:hover {
  background-color: var(--indigo-700);
}

.btn-secondary {
  background-color: var(--blue-gray-600);
  color: white;
}

.btn-secondary:hover {
  background-color: var(--blue-gray-700);
}

.btn-success {
  background-color: var(--emerald-500);
  color: white;
}

.btn-success:hover {
  background-color: var(--emerald-700);
}

.btn-danger {
  background-color: var(--red-500);
  color: white;
}

.btn-danger:hover {
  background-color: var(--red-700);
}

.btn-warning {
  background-color: var(--yellow-500);
  color: white;
}

.btn-warning:hover {
  background-color: var(--orange-500);
}

.btn-info {
  background-color: var(--indigo-500);
  color: white;
}

.btn-info:hover {
  background-color: var(--indigo-600);
}

.btn-light {
  background-color: var(--blue-gray-100);
  color: var(--blue-gray-900);
}

.btn-light:hover {
  background-color: var(--blue-gray-200);
}

.btn-dark {
  background-color: var(--blue-gray-800);
  color: white;
}

.btn-dark:hover {
  background-color: var(--blue-gray-900);
}

.btn-outline {
  background-color: transparent;
  color: var(--blue-gray-700);
  border: 1px solid var(--blue-gray-500);
}

.btn-outline:hover {
  background-color: var(--blue-gray-500);
  color: white;
}

.btn-ghost {
  background-color: transparent;
  color: var(--blue-gray-700);
}

.btn-ghost:hover {
  background-color: var(--blue-gray-100);
}

.btn-link {
  background-color: transparent;
  color: var(--indigo-600);
  text-decoration: underline;
}

.btn-link:hover {
  color: var(--indigo-700);
  text-decoration: none;
}

/* State variants */
.btn-block {
  width: 100%;
}

.btn-rounded {
  border-radius: 9999px;
}

.btn-disabled {
  opacity: 0.5;
  cursor: not-allowed;
  pointer-events: none;
}

.btn-loading {
  cursor: wait;
}

/* Loading spinner */
.button-spinner {
  display: inline-block;
  width: 1rem;
  height: 1rem;
  margin-right: 0.5rem;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Button content spacing */
.button-content {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

/* Icon spacing */
.base-button :deep(.icon) {
  width: 1rem;
  height: 1rem;
}

/* Hover animations */
.base-button:hover:not(.btn-disabled):not(.btn-loading) {
  transform: scale(1.02);
}

/* Responsive adjustments */
@media (max-width: 640px) {
  .btn-lg {
    padding: 0.5rem 1rem;
    font-size: 1rem;
  }

  .btn-xl {
    padding: 0.75rem 1.5rem;
    font-size: 1rem;
  }
}
</style>
