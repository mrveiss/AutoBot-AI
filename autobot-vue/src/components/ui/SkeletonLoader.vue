<template>
  <div class="skeleton-loader" :class="containerClass">
    <!-- Predefined layouts -->
    <div v-if="variant === 'chat-message'" class="skeleton-chat-message">
      <div class="skeleton-avatar"></div>
      <div class="skeleton-message-content">
        <div class="skeleton-line w-1/4 mb-2"></div>
        <div class="skeleton-line w-full mb-1"></div>
        <div class="skeleton-line w-3/4"></div>
      </div>
    </div>
    
    <div v-else-if="variant === 'knowledge-card'" class="skeleton-knowledge-card">
      <div class="skeleton-line w-1/2 mb-3"></div>
      <div class="skeleton-line w-full mb-2"></div>
      <div class="skeleton-line w-full mb-2"></div>
      <div class="skeleton-line w-2/3 mb-4"></div>
      <div class="flex gap-2">
        <div class="skeleton-tag"></div>
        <div class="skeleton-tag"></div>
        <div class="skeleton-tag"></div>
      </div>
    </div>
    
    <div v-else-if="variant === 'file-list'" class="skeleton-file-list">
      <div v-for="i in count" :key="i" class="skeleton-file-item">
        <div class="skeleton-file-icon"></div>
        <div class="skeleton-file-details">
          <div class="skeleton-line w-3/4 mb-1"></div>
          <div class="skeleton-line w-1/3"></div>
        </div>
        <div class="skeleton-file-size"></div>
      </div>
    </div>
    
    <div v-else-if="variant === 'stats-cards'" class="skeleton-stats-grid">
      <div v-for="i in count" :key="i" class="skeleton-stat-card">
        <div class="skeleton-stat-icon"></div>
        <div class="skeleton-stat-content">
          <div class="skeleton-line w-1/2 mb-2"></div>
          <div class="skeleton-line w-full mb-1"></div>
          <div class="skeleton-line w-3/4"></div>
        </div>
      </div>
    </div>
    
    <!-- Custom layout using slots -->
    <div v-else class="skeleton-custom">
      <slot>
        <!-- Default skeleton -->
        <div v-for="i in count" :key="i" class="skeleton-line mb-2" :class="lineClass"></div>
      </slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  variant?: 'chat-message' | 'knowledge-card' | 'file-list' | 'stats-cards' | 'custom'
  count?: number
  animated?: boolean
  theme?: 'light' | 'dark'
  rounded?: boolean
  lines?: number
  width?: string
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'custom',
  count: 1,
  animated: true,
  theme: 'light',
  rounded: true,
  lines: 3,
  width: 'full'
})

const containerClass = computed(() => ({
  'skeleton-animated': props.animated,
  'skeleton-dark': props.theme === 'dark',
  'skeleton-rounded': props.rounded
}))

const lineClass = computed(() => ({
  'w-full': props.width === 'full',
  'w-3/4': props.width === '3/4',
  'w-1/2': props.width === '1/2',
  'w-1/4': props.width === '1/4'
}))
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.skeleton-loader {
  --skeleton-bg: var(--bg-tertiary, #f3f4f6);
  --skeleton-shimmer: var(--border-default, #e5e7eb);
}

.skeleton-dark {
  --skeleton-bg: var(--bg-tertiary, #374151);
  --skeleton-shimmer: var(--border-subtle, #4b5563);
}

.skeleton-line,
.skeleton-avatar,
.skeleton-tag,
.skeleton-file-icon,
.skeleton-file-size,
.skeleton-stat-icon {
  background: var(--skeleton-bg);
  position: relative;
  overflow: hidden;
}

.skeleton-rounded .skeleton-line,
.skeleton-rounded .skeleton-tag,
.skeleton-rounded .skeleton-file-size {
  border-radius: 0.375rem;
}

.skeleton-rounded .skeleton-avatar,
.skeleton-rounded .skeleton-file-icon,
.skeleton-rounded .skeleton-stat-icon {
  border-radius: 50%;
}

/* Animation */
.skeleton-animated .skeleton-line::after,
.skeleton-animated .skeleton-avatar::after,
.skeleton-animated .skeleton-tag::after,
.skeleton-animated .skeleton-file-icon::after,
.skeleton-animated .skeleton-file-size::after,
.skeleton-animated .skeleton-stat-icon::after {
  content: '';
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  background: linear-gradient(
    90deg,
    transparent,
    var(--skeleton-shimmer),
    transparent
  );
  animation: skeleton-shimmer 2s infinite;
}

@keyframes skeleton-shimmer {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

/* Common elements */
.skeleton-line {
  height: 1rem;
}

.skeleton-line.mb-1 { margin-bottom: 0.25rem; }
.skeleton-line.mb-2 { margin-bottom: 0.5rem; }
.skeleton-line.mb-3 { margin-bottom: 0.75rem; }
.skeleton-line.mb-4 { margin-bottom: 1rem; }

.skeleton-line.w-full { width: 100%; }
.skeleton-line.w-3\/4 { width: 75%; }
.skeleton-line.w-2\/3 { width: 66.666667%; }
.skeleton-line.w-1\/2 { width: 50%; }
.skeleton-line.w-1\/3 { width: 33.333333%; }
.skeleton-line.w-1\/4 { width: 25%; }

/* Chat message skeleton */
.skeleton-chat-message {
  display: flex;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-default);
}

.skeleton-avatar {
  width: 2.5rem;
  height: 2.5rem;
  flex-shrink: 0;
}

.skeleton-message-content {
  flex: 1;
}

/* Knowledge card skeleton */
.skeleton-knowledge-card {
  padding: var(--spacing-6);
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-default);
}

.skeleton-tag {
  height: 1.5rem;
  width: 4rem;
  border-radius: 1rem;
}

/* File list skeleton */
.skeleton-file-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.skeleton-file-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3);
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-default);
}

.skeleton-file-icon {
  width: 2.5rem;
  height: 2.5rem;
  flex-shrink: 0;
}

.skeleton-file-details {
  flex: 1;
}

.skeleton-file-size {
  width: 4rem;
  height: 1rem;
  flex-shrink: 0;
}

/* Stats cards skeleton */
.skeleton-stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

.skeleton-stat-card {
  display: flex;
  gap: var(--spacing-4);
  padding: var(--spacing-6);
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-default);
}

.skeleton-stat-icon {
  width: 3rem;
  height: 3rem;
  flex-shrink: 0;
}

.skeleton-stat-content {
  flex: 1;
}

/* Custom skeleton */
.skeleton-custom {
  padding: 1rem;
}

/* Dark theme adjustments */
.skeleton-dark .skeleton-chat-message,
.skeleton-dark .skeleton-knowledge-card,
.skeleton-dark .skeleton-file-item,
.skeleton-dark .skeleton-stat-card {
  background: var(--bg-secondary);
  border-color: var(--border-subtle);
}

/* Responsive adjustments */
@media (max-width: 640px) {
  .skeleton-stats-grid {
    grid-template-columns: 1fr;
  }
  
  .skeleton-chat-message {
    padding: 0.75rem;
  }
  
  .skeleton-avatar {
    width: 2rem;
    height: 2rem;
  }
  
  .skeleton-stat-card {
    padding: 1rem;
  }
  
  .skeleton-stat-icon {
    width: 2.5rem;
    height: 2.5rem;
  }
}

/* Loading state indicators */
.skeleton-loader[aria-label]::before {
  content: attr(aria-label);
  display: block;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
  font-weight: var(--font-medium);
}

/* Accessibility */
.skeleton-loader {
  role: progressbar;
  aria-label: 'Loading content';
}

/* Reduced motion support */
@media (prefers-reduced-motion: reduce) {
  .skeleton-animated .skeleton-line::after,
  .skeleton-animated .skeleton-avatar::after,
  .skeleton-animated .skeleton-tag::after,
  .skeleton-animated .skeleton-file-icon::after,
  .skeleton-animated .skeleton-file-size::after,
  .skeleton-animated .skeleton-stat-icon::after {
    animation: none;
  }
}
</style>