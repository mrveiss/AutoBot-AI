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
  transition: all 150ms cubic-bezier(0.4, 0, 0.2, 1);
  border: 1px solid transparent;
  font-family: var(--font-sans);
  cursor: pointer;
  user-select: none;
}

.base-button:focus {
  outline: none;
}

.base-button:focus-visible {
  outline: 2px solid var(--color-info);
  outline-offset: 2px;
  box-shadow: var(--shadow-focus);
}

/* Issue #901: Removed scaling animation - too playful for professional theme */
.base-button:active:not(.btn-disabled):not(.btn-loading) {
  opacity: 0.9;
}

/* Size variants - Issue #901: Technical Precision sizing */
.btn-xs {
  height: 28px;
  padding: 0 8px;
  font-size: 11px;
  border-radius: 2px;
}

.btn-sm {
  height: 32px;
  padding: 0 12px;
  font-size: 13px;
  border-radius: 2px;
}

.btn-md {
  height: 40px;
  padding: 0 16px;
  font-size: 14px;
  border-radius: 2px;
}

.btn-lg {
  height: 48px;
  padding: 0 24px;
  font-size: 16px;
  border-radius: 4px;
}

.btn-xl {
  height: 56px;
  padding: 0 32px;
  font-size: 18px;
  border-radius: 4px;
}

/* Color variants - Issue #901: Professional electric blue primary */
.btn-primary {
  background-color: var(--color-primary);
  color: var(--text-on-primary);
  font-weight: 500;
}

.btn-primary:hover {
  background-color: var(--color-primary-hover);
}

.btn-secondary {
  background-color: transparent;
  color: var(--text-primary);
  border: 1px solid var(--border-default);
  font-weight: 500;
}

.btn-secondary:hover {
  background-color: var(--bg-hover);
  border-color: var(--border-strong);
}

.btn-success {
  background-color: var(--color-success);
  color: var(--text-on-success);
  font-weight: 500;
}

.btn-success:hover {
  background-color: var(--color-success-hover);
}

.btn-danger {
  background-color: var(--color-error);
  color: var(--text-on-error);
  font-weight: 500;
}

.btn-danger:hover {
  background-color: var(--color-error-hover);
}

.btn-warning {
  background-color: var(--color-warning);
  color: var(--text-on-warning);
  font-weight: 600;
}

.btn-warning:hover {
  background-color: var(--color-warning-hover);
}

.btn-info {
  background-color: var(--color-info);
  color: var(--text-on-primary);
  font-weight: 500;
}

.btn-info:hover {
  background-color: var(--color-info-hover);
}

.btn-light {
  background-color: var(--bg-secondary);
  color: var(--text-primary);
}

.btn-light:hover {
  background-color: var(--bg-tertiary);
}

.btn-dark {
  background-color: var(--bg-primary);
  color: var(--text-inverse);
  border: 1px solid var(--border-default);
}

.btn-dark:hover {
  background-color: var(--bg-secondary);
}

.btn-outline {
  background-color: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
}

.btn-outline:hover {
  background-color: var(--bg-hover);
  color: var(--text-primary);
  border-color: var(--border-strong);
}

.btn-ghost {
  background-color: transparent;
  color: var(--text-secondary);
  border: 1px solid transparent;
}

.btn-ghost:hover {
  background-color: var(--bg-hover);
  color: var(--text-primary);
}

.btn-link {
  background-color: transparent;
  color: var(--color-primary);
  text-decoration: none;
  padding-left: 0;
  padding-right: 0;
  border: none;
}

.btn-link:hover {
  color: var(--color-primary-hover);
  text-decoration: underline;
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

/* Issue #901: Removed hover scale - professional aesthetic prefers subtle state changes */

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
