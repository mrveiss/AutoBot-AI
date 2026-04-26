<template>
  <div class="unified-loading-view">
    <!-- Error State -->
    <div v-if="error && !isLoading" class="error-container" role="alert">
      <div class="error-content">
        <div class="error-icon">
          <Icon name="exclamation-triangle" size="xl" class="text-4xl" style="color: var(--color-error)" />
        </div>
        <h3 class="error-title">{{ t('ui.unifiedLoading.somethingWentWrong') }}</h3>
        <p class="error-message">{{ error }}</p>
        <div class="error-actions">
          <button @click="retry" class="btn-retry">
            <Icon name="redo" size="sm" class="mr-2" />
            {{ t('ui.unifiedLoading.retry') }}
          </button>
          <button @click="dismiss" class="btn-dismiss">
            {{ t('ui.unifiedLoading.continueAnyway') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Loading State -->
    <div v-else-if="isLoading && !hasContent" class="loading-container" role="status" aria-live="polite" aria-atomic="true">
      <div class="loading-content">
        <div class="loading-spinner">
          <LoadingSpinner size="xl" />
        </div>
        <p class="loading-message">{{ message || t('ui.unifiedLoading.loading') }}</p>
        <div v-if="hasTimedOut" class="timeout-warning">
          <p style="color: var(--color-warning)">{{ t('ui.unifiedLoading.takingLonger') }}</p>
          <button @click="cancelLoading" class="btn-cancel">
            {{ t('ui.unifiedLoading.cancelAndContinue') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Content with Optional Loading Overlay -->
    <div v-else class="content-container" :class="{ 'loading-overlay': isLoading && hasContent }">
      <slot />

      <!-- Subtle loading indicator when content exists -->
      <div v-if="isLoading && hasContent" class="updating-indicator" role="status" aria-live="polite" aria-atomic="true">
        <div class="updating-pulse"></div>
        <span class="updating-text">{{ t('ui.unifiedLoading.updating') }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/debugUtils'
import Icon from './Icon.vue'
import LoadingSpinner from './LoadingSpinner.vue'

const logger = createLogger('UnifiedLoadingView')
const { t } = useI18n()

interface Props {
  isLoading?: boolean
  error?: string | null
  message?: string
  hasTimedOut?: boolean
  hasContent?: boolean
  onRetry?: () => void
  timeoutMs?: number
}

const props = withDefaults(defineProps<Props>(), {
  isLoading: false,
  error: null,
  message: '',
  hasTimedOut: false,
  hasContent: false,
  timeoutMs: 10000
})

const emit = defineEmits<{
  'loading-complete': []
  'loading-error': [error: string]
  'loading-timeout': []
}>()

let timeoutId: ReturnType<typeof setTimeout> | null = null

function clearTimer() {
  if (timeoutId !== null) {
    clearTimeout(timeoutId)
    timeoutId = null
  }
}

watch(() => props.isLoading, (loading: boolean) => {
  clearTimer()
  if (loading && props.timeoutMs > 0) {
    timeoutId = setTimeout(() => {
      logger.warn(`Loading timed out after ${props.timeoutMs}ms`)
      emit('loading-timeout')
    }, props.timeoutMs)
  } else if (!loading) {
    emit('loading-complete')
  }
})

watch(() => props.error, (err: string | null | undefined) => {
  if (err) emit('loading-error', err)
})

onUnmounted(clearTimer)

const retry = () => {
  if (props.onRetry) props.onRetry()
}

const dismiss = () => {
  emit('loading-complete')
}

const cancelLoading = () => {
  emit('loading-timeout')
}
</script>

<style scoped>
@reference "../../assets/tailwind.css";
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
  @apply px-4 py-2 rounded-lg transition-colors;
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.btn-cancel:hover {
  filter: brightness(1.15);
}

/* Content Container */
.content-container {
  @apply relative h-full flex flex-col;
  /* CRITICAL FIX: Remove w-full to allow parent to control width */
  /* CRITICAL FIX: Add flex flex-col to ensure children fill height */
  transition: opacity var(--duration-200) var(--ease-out);
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
  @apply w-2 h-2 rounded-full animate-pulse;
  background: var(--color-primary);
}

.updating-text {
  @apply text-sm text-autobot-text-secondary;
}
</style>
