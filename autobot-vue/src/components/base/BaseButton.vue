<template>
  <component
    :is="tag"
    :class="buttonClasses"
    :disabled="disabled || loading"
    :type="htmlType"
    @click="handleClick"
    @touchstart="handleTouchStart"
    @touchend="handleTouchEnd"
    @touchcancel="handleTouchCancel"
  >
    <span v-if="loading" class="button-spinner"></span>
    <slot name="icon-left" v-if="$slots['icon-left'] && !loading"></slot>
    <span class="button-content" v-if="$slots.default || label">
      <slot>{{ label }}</slot>
    </span>
    <slot name="icon-right" v-if="$slots['icon-right'] && !loading"></slot>
    <div v-if="touchOptimized" class="touch-ripple" ref="ripple"></div>
  </component>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

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
  touchOptimized?: boolean
  touchFeedback?: boolean
  hapticFeedback?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'primary',
  size: 'md',
  disabled: false,
  loading: false,
  block: false,
  rounded: false,
  htmlType: 'button',
  tag: 'button',
  touchOptimized: false,
  touchFeedback: true,
  hapticFeedback: true
})

const emit = defineEmits<{
  click: [event: MouseEvent]
  touchStart: [event: TouchEvent]
  touchEnd: [event: TouchEvent]
}>()

const ripple = ref<HTMLElement>()
const isPressed = ref(false)

const buttonClasses = computed(() => [
  'base-button',
  `btn-${props.variant}`,
  `btn-${props.size}`,
  {
    'btn-block': props.block,
    'btn-rounded': props.rounded,
    'btn-loading': props.loading,
    'btn-disabled': props.disabled,
    'btn-touch-optimized': props.touchOptimized,
    'btn-pressed': isPressed.value
  }
])

const handleClick = (event: MouseEvent) => {
  if (!props.disabled && !props.loading) {
    emit('click', event)
  }
}

const handleTouchStart = (event: TouchEvent) => {
  if (props.disabled || props.loading || !props.touchOptimized) return

  isPressed.value = true

  if (props.touchFeedback) {
    createRipple(event)
  }

  if (props.hapticFeedback && 'vibrate' in navigator) {
    navigator.vibrate(10)
  }

  emit('touchStart', event)
}

const handleTouchEnd = (event: TouchEvent) => {
  if (!props.touchOptimized) return
  isPressed.value = false
  emit('touchEnd', event)
}

const handleTouchCancel = () => {
  if (!props.touchOptimized) return
  isPressed.value = false
}

const createRipple = (event: TouchEvent) => {
  if (!ripple.value || !props.touchFeedback) return

  const button = ripple.value.parentElement!
  const rect = button.getBoundingClientRect()
  const touch = event.touches[0]

  const x = touch.clientX - rect.left
  const y = touch.clientY - rect.top

  const rippleElement = document.createElement('div')
  rippleElement.className = 'ripple-effect'
  rippleElement.style.left = `${x - 25}px`
  rippleElement.style.top = `${y - 25}px`

  ripple.value.appendChild(rippleElement)

  // Remove ripple after animation
  setTimeout(() => {
    if (ripple.value && ripple.value.contains(rippleElement)) {
      ripple.value.removeChild(rippleElement)
    }
  }, 600)
}
</script>

<style scoped>
.base-button {
  position: relative;
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
}

.base-button:focus-visible {
  outline: 2px solid var(--indigo-500);
  outline-offset: 2px;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.3);
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

/* Touch optimization styles */
.btn-touch-optimized {
  min-height: 44px;
  min-width: 44px;
  overflow: hidden;
  -webkit-tap-highlight-color: transparent;
  touch-action: manipulation;
}

.btn-pressed {
  transform: scale(0.95);
}

.touch-ripple {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
  border-radius: inherit;
}

.ripple-effect {
  position: absolute;
  width: 50px;
  height: 50px;
  background: rgba(255, 255, 255, 0.4);
  border-radius: 50%;
  transform: scale(0);
  animation: ripple-animation 0.6s ease-out;
}

@keyframes ripple-animation {
  to {
    transform: scale(4);
    opacity: 0;
  }
}

/* Touch-optimized button overrides hover behavior on touch devices */
@media (hover: none) and (pointer: coarse) {
  .btn-touch-optimized:hover:not(.btn-disabled):not(.btn-loading) {
    transform: none;
  }

  .btn-touch-optimized:active:not(.btn-disabled):not(.btn-loading) {
    transform: scale(0.95);
  }
}
</style>
