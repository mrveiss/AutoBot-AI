<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<!--
  LoadingBoundary — full-replace loading component.
  Shows a spinner (with optional custom #loading-message slot) when :loading is true.
  Shows slot content when not loading.
  Shows error state with optional #error-content slot when :error is set.

  Replaces UnifiedLoadingView for callers that need a "big spinner OR slot" pattern.
  See #6698 for the migration rationale.
-->
<template>
  <div class="loading-boundary">
    <!-- Error State -->
    <div v-if="error && !loading" class="error-container" role="alert">
      <slot name="error-content">
        <div class="error-content">
          <div class="error-icon">
            <Icon name="exclamation-triangle" size="xl" class="text-4xl" style="color: var(--color-error)" />
          </div>
          <h3 class="error-title">{{ t('ui.unifiedLoading.somethingWentWrong') }}</h3>
          <p class="error-message">{{ error }}</p>
          <div class="error-actions">
            <button v-if="onRetry" @click="onRetry" class="btn-retry">
              <Icon name="redo" size="sm" class="mr-2" />
              {{ t('ui.unifiedLoading.retry') }}
            </button>
            <button @click="emit('loading-complete')" class="btn-dismiss">
              {{ t('ui.unifiedLoading.continueAnyway') }}
            </button>
          </div>
        </div>
      </slot>
    </div>

    <!-- Loading State -->
    <div v-else-if="loading" class="loading-container" role="status" aria-live="polite" aria-atomic="true">
      <div class="loading-content">
        <div class="loading-spinner">
          <LoadingSpinner size="xl" />
        </div>
        <slot name="loading-message">
          <p class="loading-message">{{ message || t('ui.unifiedLoading.loading') }}</p>
        </slot>
        <div v-if="hasTimedOut" class="timeout-warning">
          <p style="color: var(--color-warning)">{{ t('ui.unifiedLoading.takingLonger') }}</p>
          <button @click="emit('loading-timeout')" class="btn-cancel">
            {{ t('ui.unifiedLoading.cancelAndContinue') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Content -->
    <slot v-else />
  </div>
</template>

<script setup lang="ts">
import { ref, onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from './Icon.vue'
import LoadingSpinner from './LoadingSpinner.vue'

const { t } = useI18n()

interface Props {
  loading?: boolean
  error?: string | null
  message?: string
  timeoutMs?: number
  onRetry?: () => void
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  error: null,
  message: '',
  timeoutMs: 10000,
})

const emit = defineEmits<{
  'loading-complete': []
  'loading-error': [error: string]
  'loading-timeout': []
}>()

const hasTimedOut = ref(false)
let timeoutId: ReturnType<typeof setTimeout> | null = null

function clearTimer() {
  if (timeoutId !== null) {
    clearTimeout(timeoutId)
    timeoutId = null
  }
}

watch(() => props.loading, (isLoading: boolean) => {
  clearTimer()
  hasTimedOut.value = false
  if (isLoading && props.timeoutMs > 0) {
    timeoutId = setTimeout(() => {
      hasTimedOut.value = true
      emit('loading-timeout')
    }, props.timeoutMs)
  } else if (!isLoading) {
    emit('loading-complete')
  }
}, { immediate: false })

watch(() => props.error, (err: string | null | undefined) => {
  if (err) emit('loading-error', err)
})

onUnmounted(clearTimer)
</script>

<style scoped>
@reference "../../assets/tailwind.css";
.loading-boundary {
  @apply relative h-full;
}

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
</style>
