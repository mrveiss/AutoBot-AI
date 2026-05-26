<template>
  <component
    :is="tag"
    :class="buttonClasses"
    :disabled="disabled || loading"
    :type="htmlType"
    :aria-label="ariaLabel || undefined"
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
import { computed, ref, onMounted, watchEffect, useSlots, Comment } from 'vue'
import type { ButtonVariant, ComponentSize } from '@/types/component-props'
import { size as SIZE_VALUES } from '@/design-tokens/tokens'
import { createLogger } from '@/utils/debugUtils'

const BUTTON_VARIANTS: ButtonVariant[] = [
  'primary', 'secondary', 'success', 'error', 'warning', 'info',
  'light', 'dark', 'outline-solid', 'ghost', 'link',
]

const logger = createLogger('BaseButton')

interface Props {
  variant?: ButtonVariant
  size?: ComponentSize
  disabled?: boolean
  loading?: boolean
  block?: boolean
  rounded?: boolean
  label?: string
  ariaLabel?: string
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

const slots = useSlots()

if (import.meta.env.DEV) {
  onMounted(() => {
    const hasVisibleText = !!props.label || !!slots.default?.()?.some(
      (vnode: any) => vnode.type !== Comment && vnode.children
    )
    if (!hasVisibleText && !props.ariaLabel) {
      logger.warn(
        'Icon-only button rendered without ariaLabel prop. ' +
        'This is a WCAG 4.1.2 failure. Add :ariaLabel="$t(\'common.actionName\')" to the button.'
      )
    }
  })

  watchEffect(() => {
    if (props.size !== undefined && !(SIZE_VALUES as readonly string[]).includes(props.size)) {
      logger.warn(`Invalid "size" prop: "${props.size}". Expected: ${SIZE_VALUES.join(' | ')}`)
    }
    if (props.variant !== undefined && !BUTTON_VARIANTS.includes(props.variant)) {
      logger.warn(`Invalid "variant" prop: "${props.variant}". Expected: ${BUTTON_VARIANTS.join(' | ')}`)
    }
  })
}

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
  transition: all var(--duration-150) var(--ease-in-out);
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
  padding: var(--spacing-0) var(--spacing-2);
  font-size: var(--text-xs);
  border-radius: var(--radius-xs);
}

.btn-sm {
  height: 32px;
  padding: var(--spacing-0) var(--spacing-3);
  font-size: var(--text-sm);
  border-radius: var(--radius-xs);
}

.btn-md {
  height: 40px;
  padding: var(--spacing-0) var(--spacing-4);
  font-size: var(--text-sm);
  border-radius: var(--radius-xs);
}

.btn-lg {
  height: 48px;
  padding: var(--spacing-0) var(--spacing-6);
  font-size: var(--text-base);
  border-radius: var(--radius-default);
}

.btn-xl {
  height: 56px;
  padding: var(--spacing-0) var(--spacing-8);
  font-size: var(--text-lg);
  border-radius: var(--radius-default);
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
  padding-left: var(--spacing-0);
  padding-right: var(--spacing-0);
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
  border-radius: var(--radius-full);
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
  margin-right: var(--spacing-2);
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
  gap: var(--spacing-2);
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
    padding: var(--spacing-2) var(--spacing-4);
    font-size: var(--text-base);
  }

  .btn-xl {
    padding: var(--spacing-3) var(--spacing-6);
    font-size: var(--text-base);
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
