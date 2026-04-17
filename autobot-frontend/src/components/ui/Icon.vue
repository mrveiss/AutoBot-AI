<!--
  Icon.vue renders a single-path SVG icon from the ICONS registry.
  For multi-element loading indicators use `<LoadingSpinner>` instead — this
  component is intentionally single-responsibility so each IconName maps to
  exactly one path.
-->
<template>
  <svg
    xmlns="http://www.w3.org/2000/svg"
    :class="['icon', sizeClass, { 'icon-spin': spin }]"
    :fill="filled ? 'currentColor' : 'none'"
    :stroke="filled ? 'none' : 'currentColor'"
    viewBox="0 0 24 24"
    aria-hidden="true"
  >
    <path
      v-if="path"
      stroke-linecap="round"
      stroke-linejoin="round"
      :stroke-width="strokeWidth"
      :d="path"
    />
  </svg>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const ICONS = {
  // Navigation
  'chevron-down': 'M19 9l-7 7-7-7',
  'chevron-up': 'M5 15l7-7 7 7',
  'chevron-left': 'M15 19l-7-7 7-7',
  'chevron-right': 'M9 5l7 7-7 7',

  // Actions
  times: 'M6 18L18 6M6 6l12 12',
  check: 'M5 13l4 4L19 7',
  plus: 'M12 4v16m8-8H4',
  minus: 'M20 12H4',
  redo: 'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15',
  undo: 'M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6',

  // Status
  'check-circle': 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',
  'exclamation-circle': 'M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
  'exclamation-triangle': 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z',
  'info-circle': 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z',

  // Theme
  sun: 'M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z',
  moon: 'M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z',
  desktop: 'M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z',
  palette: 'M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01',

  // Communication
  'paper-plane': 'M12 19l9 2-9-18-9 18 9-2zm0 0v-8',
  comment: 'M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z',
  terminal: 'M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z',

  // Misc
  inbox: 'M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4',
  'sliders-h': 'M4 6h16M4 12h16M4 18h16M8 4v4m4 4v4m-4 4v4',
  font: 'M5 4v3h5.5v12h3V7H19V4z',
  'paint-brush': 'M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485',
  th: 'M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z',
} as const

export type IconName = keyof typeof ICONS

interface IconProps {
  name: IconName
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  spin?: boolean
  strokeWidth?: number
  filled?: boolean
}

const props = withDefaults(defineProps<IconProps>(), {
  size: 'md',
  spin: false,
  strokeWidth: 2,
  filled: false,
})

const path = computed(() => ICONS[props.name])

const sizeClass = computed(() => `icon-${props.size}`)
</script>

<style scoped>
.icon {
  display: inline-block;
  vertical-align: middle;
  flex-shrink: 0;
}

.icon-xs {
  width: 0.75rem;
  height: 0.75rem;
}

.icon-sm {
  width: 1rem;
  height: 1rem;
}

.icon-md {
  width: 1.25rem;
  height: 1.25rem;
}

.icon-lg {
  width: 1.5rem;
  height: 1.5rem;
}

.icon-xl {
  width: 2rem;
  height: 2rem;
}

.icon-spin {
  animation: icon-spin 1s linear infinite;
}

@keyframes icon-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
