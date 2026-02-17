<template>
  <div class="unified-loading-view" :data-loading-key="loadingKey">
    <!-- Error State -->
    <div v-if="error && !isLoading" class="error-container">
      <div class="error-content">
        <div class="error-icon">
          <i class="fas fa-exclamation-triangle text-red-500 text-4xl"></i>
        </div>
        <h3 class="error-title">Something went wrong</h3>
        <p class="error-message">{{ error }}</p>
        <div class="error-actions">
          <button @click="retry" class="btn-retry">
            <i class="fas fa-redo mr-2"></i>
            Retry
          </button>
          <button @click="dismiss" class="btn-dismiss">
            Continue Anyway
          </button>
        </div>
      </div>
    </div>

    <!-- Loading State -->
    <div v-else-if="isLoading && !hasContent" class="loading-container">
      <div class="loading-content">
        <div class="loading-spinner">
          <div class="animate-spin rounded-full h-16 w-16 border-b-2 border-indigo-600"></div>
        </div>
        <p class="loading-message">{{ message || 'Loading...' }}</p>
        <div v-if="hasTimedOut" class="timeout-warning">
          <p class="text-yellow-600">This is taking longer than expected...</p>
          <button @click="cancelLoading" class="btn-cancel">
            Cancel and Continue
          </button>
        </div>
      </div>
    </div>

    <!-- Content with Optional Loading Overlay -->
    <div v-else class="content-container" :class="{ 'loading-overlay': isLoading && hasContent }">
      <slot />

      <!-- Subtle loading indicator when content exists -->
      <div v-if="isLoading && hasContent" class="updating-indicator">
        <div class="updating-pulse"></div>
        <span class="updating-text">Updating...</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { useUnifiedLoading } from '@/composables/useUnifiedLoading'

const logger = createLogger('UnifiedLoadingView')

interface Props {
  loadingKey?: string
  hasContent?: boolean
  onRetry?: () => void
  autoTimeoutMs?: number
}

const props = withDefaults(defineProps<Props>(), {
  loadingKey: 'default',
  hasContent: false,
  autoTimeoutMs: 10000
})

const emit = defineEmits<{
  'loading-complete': []
  'loading-error': [error: string]
  'loading-timeout': []
}>()

const { isLoading, error, message, hasTimedOut, stopLoading, setError } = useUnifiedLoading(props.loadingKey)

// Auto-stop loading after timeout if still loading
onMounted(() => {
  const timeoutId = setTimeout(() => {
    if (isLoading.value) {
      logger.warn(`Auto-stopping loading for key: ${props.loadingKey}`)
      stopLoading()
      emit('loading-timeout')
    }
  }, props.autoTimeoutMs)

  // Cleanup on unmount
  onUnmounted(() => {
    clearTimeout(timeoutId)
  })
})

const retry = () => {
  setError(null)
  if (props.onRetry) {
    props.onRetry()
  }
}

const dismiss = () => {
  setError(null)
  stopLoading()
  emit('loading-complete')
}

const cancelLoading = () => {
  stopLoading()
  emit('loading-complete')
}
</script>

<style scoped>
.unified-loading-view {
  @apply relative h-full;
  /* CRITICAL FIX: Remove w-full to prevent width override issues */
  /* CRITICAL FIX: Remove min-h-[200px] to prevent extra empty space in chat */
  /* Width is now controlled by parent component/class */
}

/* Error Container */
.error-container {
  @apply flex items-center justify-center h-full p-8;
}

.error-content {
  @apply text-center max-w-md;
}

.error-icon {
  @apply mb-4;
}

.error-title {
  @apply text-xl font-semibold text-autobot-text-primary mb-2;
}

.error-message {
  @apply text-autobot-text-secondary mb-6;
}

.error-actions {
  @apply flex gap-3 justify-center;
}

.btn-retry {
  @apply px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors;
}

.btn-dismiss {
  @apply px-4 py-2 bg-autobot-bg-secondary text-autobot-text-secondary rounded-lg hover:bg-autobot-bg-tertiary transition-colors;
}

/* Loading Container */
.loading-container {
  @apply flex items-center justify-center h-full;
}

.loading-content {
  @apply text-center;
}

.loading-spinner {
  @apply flex justify-center mb-4;
}

.loading-message {
  @apply text-autobot-text-secondary mb-4;
}

.timeout-warning {
  @apply mt-6 space-y-3;
}

.btn-cancel {
  @apply px-4 py-2 bg-yellow-100 text-yellow-800 rounded-lg hover:bg-yellow-200 transition-colors;
}

/* Content Container */
.content-container {
  @apply relative h-full flex flex-col;
  /* CRITICAL FIX: Remove w-full to allow parent to control width */
  /* CRITICAL FIX: Add flex flex-col to ensure children fill height */
  transition: opacity 0.2s ease;
}

.content-container.loading-overlay {
  @apply opacity-75;
}

/* Updating Indicator */
.updating-indicator {
  @apply absolute top-4 right-4 flex items-center gap-2 bg-autobot-bg-card px-3 py-1.5 rounded-full shadow-sm;
  opacity: 0.9;
}

.updating-pulse {
  @apply w-2 h-2 bg-blue-500 rounded-full animate-pulse;
}

.updating-text {
  @apply text-sm text-autobot-text-secondary;
}
</style>
