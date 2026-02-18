<template>
  <div class="loading-spinner" :class="sizeClass" :style="customStyle">
    <div v-if="variant === 'dots'" class="loading-dots">
      <div class="dot"></div>
      <div class="dot"></div>
      <div class="dot"></div>
    </div>

    <div v-else-if="variant === 'pulse'" class="loading-pulse">
      <div class="pulse-ring"></div>
      <div class="pulse-ring"></div>
      <div class="pulse-ring"></div>
    </div>

    <div v-else-if="variant === 'bars'" class="loading-bars">
      <div class="bar"></div>
      <div class="bar"></div>
      <div class="bar"></div>
      <div class="bar"></div>
    </div>

    <div v-else class="loading-circle">
      <svg class="circular" viewBox="25 25 50 50">
        <circle
          class="path"
          cx="50"
          cy="50"
          r="20"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-miterlimit="10"
        />
      </svg>
    </div>

    <div v-if="label" class="loading-label" :class="labelClass">
      {{ label }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  variant?: 'circle' | 'dots' | 'pulse' | 'bars'
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  color?: string
  label?: string
  labelPosition?: 'bottom' | 'right'
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'circle',
  size: 'md',
  color: 'currentColor',
  labelPosition: 'bottom'
})

const sizeClass = computed(() => {
  const sizes = {
    xs: 'loading-xs',
    sm: 'loading-sm',
    md: 'loading-md',
    lg: 'loading-lg',
    xl: 'loading-xl'
  }
  return sizes[props.size]
})

const labelClass = computed(() => ({
  'label-right': props.labelPosition === 'right',
  'label-bottom': props.labelPosition === 'bottom'
}))

const customStyle = computed(() => ({
  color: props.color
}))
</script>

<style scoped>
.loading-spinner {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
}

.loading-spinner.loading-xs { width: 16px; height: 16px; }
.loading-spinner.loading-sm { width: 20px; height: 20px; }
.loading-spinner.loading-md { width: 24px; height: 24px; }
.loading-spinner.loading-lg { width: 32px; height: 32px; }
.loading-spinner.loading-xl { width: 40px; height: 40px; }

/* Circle Spinner */
.loading-circle {
  width: 100%;
  height: 100%;
}

.circular {
  animation: rotate 2s linear infinite;
  width: 100%;
  height: 100%;
}

.path {
  stroke-dasharray: 90, 150;
  stroke-dashoffset: 0;
  stroke-linecap: round;
  animation: dash 1.5s ease-in-out infinite;
}

@keyframes rotate {
  100% { transform: rotate(360deg); }
}

@keyframes dash {
  0% {
    stroke-dasharray: 1, 150;
    stroke-dashoffset: 0;
  }
  50% {
    stroke-dasharray: 90, 150;
    stroke-dashoffset: -35;
  }
  100% {
    stroke-dasharray: 90, 150;
    stroke-dashoffset: -124;
  }
}

/* Dots Spinner */
.loading-dots {
  display: flex;
  gap: 4px;
  align-items: center;
}

.dot {
  width: 25%;
  height: 25%;
  background: currentColor;
  border-radius: 50%;
  animation: dot-bounce 1.4s ease-in-out infinite both;
}

.dot:nth-child(1) { animation-delay: -0.32s; }
.dot:nth-child(2) { animation-delay: -0.16s; }

@keyframes dot-bounce {
  0%, 80%, 100% {
    transform: scale(0);
  }
  40% {
    transform: scale(1.0);
  }
}

/* Pulse Spinner */
.loading-pulse {
  position: relative;
  width: 100%;
  height: 100%;
}

.pulse-ring {
  border: 2px solid currentColor;
  border-radius: 50%;
  position: absolute;
  left: 0;
  top: 0;
  width: 100%;
  height: 100%;
  animation: pulse-ring 1.25s cubic-bezier(0.215, 0.61, 0.355, 1) infinite;
}

.pulse-ring:nth-child(1) { animation-delay: 0s; }
.pulse-ring:nth-child(2) { animation-delay: 0.25s; }
.pulse-ring:nth-child(3) { animation-delay: 0.5s; }

@keyframes pulse-ring {
  0% {
    transform: scale(0);
    opacity: 1;
  }
  100% {
    transform: scale(1);
    opacity: 0;
  }
}

/* Bars Spinner */
.loading-bars {
  display: flex;
  gap: 2px;
  align-items: center;
  height: 100%;
}

.bar {
  width: 20%;
  height: 100%;
  background: currentColor;
  border-radius: 1px;
  animation: bar-scale 1.2s infinite ease-in-out;
}

.bar:nth-child(1) { animation-delay: -1.1s; }
.bar:nth-child(2) { animation-delay: -1.0s; }
.bar:nth-child(3) { animation-delay: -0.9s; }
.bar:nth-child(4) { animation-delay: -0.8s; }

@keyframes bar-scale {
  0%, 40%, 100% {
    transform: scaleY(0.4);
  }
  20% {
    transform: scaleY(1.0);
  }
}

/* Issue #704: Migrated to CSS design tokens */
/* Label */
.loading-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-top: var(--spacing-2);
  text-align: center;
}

.label-right {
  margin-top: 0;
  margin-left: var(--spacing-2);
}

.label-bottom {
  margin-top: var(--spacing-2);
  margin-left: 0;
}

/* Right-aligned label layout */
.loading-spinner:has(.label-right) {
  flex-direction: row;
}
</style>
