<template>
  <div class="stable-loading-container" :class="containerClasses">
    <!-- Consistent Layout Placeholder -->
    <div
      v-if="isLoading && !hasContent"
      class="loading-placeholder"
      :style="placeholderStyle"
    >
      <div class="loading-content">
        <div class="loading-header">
          <div class="loading-avatar"></div>
          <div class="loading-info">
            <div class="loading-name"></div>
            <div class="loading-time"></div>
          </div>
        </div>
        <div class="loading-text">
          <div class="loading-line"></div>
          <div class="loading-line short"></div>
          <div class="loading-line medium"></div>
        </div>
      </div>
    </div>

    <!-- Stable Content Area -->
    <div
      v-if="hasContent || !isLoading"
      class="content-area"
      :class="{ 'content-loading': isLoading && hasContent }"
    >
      <slot />
    </div>

    <!-- Minimal Loading Indicator for Content Updates -->
    <div
      v-if="isLoading && hasContent"
      class="content-update-indicator"
    >
      <div class="update-pulse"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  isLoading: boolean
  hasContent: boolean
  variant?: 'chat' | 'sidebar' | 'modal' | 'inline'
  minHeight?: string
  preserveSpace?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'chat',
  minHeight: '200px',
  preserveSpace: true
})

const containerClasses = computed(() => {
  return [
    `variant-${props.variant}`,
    {
      'preserve-space': props.preserveSpace,
      'is-loading': props.isLoading,
      'has-content': props.hasContent
    }
  ]
})

const placeholderStyle = computed(() => {
  return {
    minHeight: props.minHeight
  }
})
</script>

<style scoped>
.stable-loading-container {
  @apply relative w-full;
  transition: all 0.2s ease-in-out;
}

/* Preserve minimum height to prevent layout shifts */
.preserve-space {
  min-height: var(--min-height, 200px);
}

/* Loading Placeholder - matches actual content layout */
.loading-placeholder {
  @apply w-full p-4 animate-pulse;
}

.loading-content {
  @apply bg-autobot-bg-primary rounded-lg shadow-sm border border-autobot-border p-4;
}

.loading-header {
  @apply flex items-center gap-3 mb-3;
}

.loading-avatar {
  @apply w-8 h-8 bg-autobot-bg-secondary rounded-full;
}

.loading-info {
  @apply flex-1 space-y-2;
}

.loading-name {
  @apply h-4 bg-autobot-bg-secondary rounded w-24;
}

.loading-time {
  @apply h-3 bg-autobot-bg-tertiary rounded w-16;
}

.loading-text {
  @apply space-y-2;
}

.loading-line {
  @apply h-4 bg-autobot-bg-tertiary rounded;
}

.loading-line.short {
  @apply w-3/4;
}

.loading-line.medium {
  @apply w-1/2;
}

/* Content Area - stable positioning */
.content-area {
  @apply w-full;
  transition: opacity 0.15s ease-in-out;
}

.content-loading {
  @apply opacity-95;
}

/* Minimal update indicator */
.content-update-indicator {
  @apply absolute top-2 right-2 pointer-events-none;
}

.update-pulse {
  @apply w-2 h-2 bg-blue-500 rounded-full animate-pulse;
}

/* Variant-specific styles */
.variant-chat .loading-placeholder {
  @apply space-y-4;
}

.variant-sidebar .loading-placeholder {
  @apply p-2;
}

.variant-sidebar .loading-content {
  @apply shadow-none border-0 bg-transparent;
}

.variant-modal .loading-placeholder {
  @apply p-6;
}

.variant-inline .loading-placeholder {
  @apply p-0;
}

.variant-inline .loading-content {
  @apply shadow-none border-0 bg-transparent p-0;
}

/* Instant transitions for better responsiveness */
.stable-loading-container * {
  transition: opacity 0.05s ease-in-out;
}

/* Prevent layout shifts during loading */
.stable-loading-container {
  contain: layout style;
}
</style>
