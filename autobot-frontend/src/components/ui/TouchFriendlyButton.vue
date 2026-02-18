<template>
  <button
    :class="buttonClasses"
    :disabled="disabled"
    @touchstart="handleTouchStart"
    @touchend="handleTouchEnd"
    @touchcancel="handleTouchCancel"
    @click="handleClick"
    v-bind="$attrs"
  >
    <div v-if="loading" class="loading-overlay">
      <LoadingSpinner :variant="loadingVariant" :size="loadingSize" color="currentColor" />
    </div>

    <div class="button-content" :class="{ 'opacity-0': loading }">
      <slot name="icon" />
      <span v-if="$slots.default" class="button-text">
        <slot />
      </span>
      <slot name="trailing" />
    </div>

    <div class="touch-ripple" ref="ripple"></div>
  </button>
</template>

<script setup lang="ts">
import { computed, ref, nextTick } from 'vue'
import LoadingSpinner from './LoadingSpinner.vue'

interface Props {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger'
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  loading?: boolean
  disabled?: boolean
  loadingVariant?: 'circle' | 'dots' | 'pulse'
  loadingSize?: 'xs' | 'sm' | 'md'
  touchFeedback?: boolean
  hapticFeedback?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'primary',
  size: 'md',
  loading: false,
  disabled: false,
  loadingVariant: 'circle',
  loadingSize: 'sm',
  touchFeedback: true,
  hapticFeedback: true
})

const emit = defineEmits<{
  click: [event: MouseEvent | TouchEvent]
  touchStart: [event: TouchEvent]
  touchEnd: [event: TouchEvent]
}>()

const ripple = ref<HTMLElement>()
const isPressed = ref(false)

const buttonClasses = computed(() => [
  'touch-friendly-button',
  `button-${props.variant}`,
  `button-${props.size}`,
  {
    'button-loading': props.loading,
    'button-disabled': props.disabled,
    'button-pressed': isPressed.value
  }
])

const handleTouchStart = (event: TouchEvent) => {
  if (props.disabled || props.loading) return

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
  isPressed.value = false
  emit('touchEnd', event)
}

const handleTouchCancel = () => {
  isPressed.value = false
}

const handleClick = (event: MouseEvent) => {
  if (props.disabled || props.loading) return
  emit('click', event)
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
.touch-friendly-button {
  @apply relative overflow-hidden focus:outline-none focus:ring-2 focus:ring-offset-2 transition-all duration-200 font-medium;
  min-height: 44px; /* iOS/Android minimum touch target */
  min-width: 44px;
  -webkit-tap-highlight-color: transparent;
  user-select: none;
  touch-action: manipulation;
}

.button-content {
  @apply flex items-center justify-center gap-2 relative z-10 transition-opacity duration-200;
}

.loading-overlay {
  @apply absolute inset-0 flex items-center justify-center z-20;
}

.touch-ripple {
  @apply absolute inset-0 overflow-hidden pointer-events-none;
}

.ripple-effect {
  @apply absolute w-12 h-12 bg-white bg-opacity-30 rounded-full;
  animation: ripple 0.6s ease-out;
  pointer-events: none;
}

@keyframes ripple {
  0% {
    transform: scale(0);
    opacity: 1;
  }
  100% {
    transform: scale(4);
    opacity: 0;
  }
}

/* Size variants */
.button-xs {
  @apply px-2 py-1 text-xs rounded min-h-8 min-w-8;
}

.button-sm {
  @apply px-3 py-2 text-sm rounded-md min-h-10 min-w-10;
}

.button-md {
  @apply px-4 py-2 text-base rounded-lg min-h-11 min-w-11;
}

.button-lg {
  @apply px-6 py-3 text-lg rounded-lg min-h-12 min-w-12;
}

.button-xl {
  @apply px-8 py-4 text-xl rounded-xl min-h-14 min-w-14;
}

/* Variant styles */
.button-primary {
  @apply bg-blue-600 text-white border border-transparent;
}

.button-primary:hover:not(.button-disabled):not(.button-loading) {
  @apply bg-blue-700;
}

.button-primary:focus {
  @apply ring-blue-500;
}

.button-secondary {
  @apply bg-autobot-bg-primary text-autobot-text-primary border border-transparent;
}

.button-secondary:hover:not(.button-disabled):not(.button-loading) {
  @apply bg-autobot-bg-secondary;
}

.button-secondary:focus {
  @apply ring-autobot-border;
}

.button-outline {
  @apply bg-transparent text-autobot-text-secondary border border-autobot-border;
}

.button-outline:hover:not(.button-disabled):not(.button-loading) {
  @apply bg-autobot-bg-tertiary border-autobot-border;
}

.button-outline:focus {
  @apply ring-autobot-border;
}

.button-ghost {
  @apply bg-transparent text-autobot-text-secondary border border-transparent;
}

.button-ghost:hover:not(.button-disabled):not(.button-loading) {
  @apply bg-autobot-bg-secondary text-autobot-text-primary;
}

.button-ghost:focus {
  @apply ring-autobot-border;
}

.button-danger {
  @apply bg-red-600 text-white border border-transparent;
}

.button-danger:hover:not(.button-disabled):not(.button-loading) {
  @apply bg-red-700;
}

.button-danger:focus {
  @apply ring-red-500;
}

/* States */
.button-pressed {
  @apply transform scale-95;
}

.button-loading {
  @apply cursor-wait;
}

.button-disabled {
  @apply opacity-50 cursor-not-allowed;
}

/* Dark mode support — project uses data-theme attribute, not prefers-color-scheme */
/* Design tokens (autobot-*) handle theming via CSS custom properties on [data-theme] */

/* High contrast mode support */
@media (prefers-contrast: high) {
  .touch-friendly-button {
    @apply border-2;
  }
}

/* Reduced motion support */
@media (prefers-reduced-motion: reduce) {
  .touch-friendly-button {
    @apply transition-none;
  }

  .button-content {
    @apply transition-none;
  }

  .button-pressed {
    @apply transform-none;
  }

  .ripple-effect {
    display: none;
  }
}

/* Mobile-specific optimizations */
@media (max-width: 768px) {
  .touch-friendly-button {
    min-height: 48px; /* Larger touch targets on mobile */
    min-width: 48px;
  }

  .button-text {
    @apply text-base; /* Ensure text is readable on mobile */
  }
}

/* iOS-specific optimizations */
@supports (-webkit-touch-callout: none) {
  .touch-friendly-button {
    -webkit-appearance: none;
    -webkit-touch-callout: none;
  }
}
</style>
