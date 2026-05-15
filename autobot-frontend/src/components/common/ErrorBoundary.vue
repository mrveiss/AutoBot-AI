<template>
  <div v-if="hasError" class="error-boundary">
    <div class="error-container">
      <div class="error-icon">
        ⚠️
      </div>
      <div class="error-content">
        <h3 class="error-title">{{ $t('common.errorBoundary.title') }}</h3>
        <p class="error-message">{{ userFriendlyMessage }}</p>

        <div class="error-details" v-if="showDetails">
          <details>
            <summary class="error-details-toggle">{{ $t('common.errorBoundary.technicalDetails') }}</summary>
            <div class="error-stack">
              <pre>{{ errorInfo.message }}</pre>
              <pre v-if="errorInfo.stack" class="stack-trace">{{ errorInfo.stack }}</pre>
              <div v-if="errorInfo.componentInfo" class="component-info">
                <strong>{{ $t('common.errorBoundary.component') }}:</strong> {{ errorInfo.componentInfo }}
              </div>
            </div>
          </details>
        </div>

        <div class="error-actions">
          <BaseButton
            variant="primary"
            @click="retry"
            :disabled="retrying"
          >
            {{ retrying ? $t('common.errorBoundary.retrying') : $t('common.errorBoundary.tryAgain') }}
          </BaseButton>
          <BaseButton
            variant="secondary"
            @click="reload"
          >
            {{ $t('common.errorBoundary.reloadPage') }}
          </BaseButton>
          <BaseButton
            variant="ghost"
            @click="toggleDetails"
          >
            {{ showDetails ? $t('common.errorBoundary.hideDetails') : $t('common.errorBoundary.showDetails') }}
          </BaseButton>
        </div>
      </div>
    </div>
  </div>
  <div v-else>
    <slot />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onErrorCaptured, inject } from 'vue'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/debugUtils'
import BaseButton from '@/components/base/BaseButton.vue'

const { t } = useI18n()
const logger = createLogger('ErrorBoundary')

interface Props {
  fallback?: string
  onError?: (error: Error, instance: any, info: string) => void
  showRetry?: boolean
  showReload?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  fallback: undefined,
  showRetry: true,
  showReload: true
})

const hasError = ref(false)
const errorInfo = ref<{
  message: string
  stack?: string
  componentInfo?: string
  component?: string
}>({ message: '' })
const showDetails = ref(false)
const retrying = ref(false)

// Inject RUM agent if available
const rum = inject('rum', null) as any

// Compute user-friendly error message
const userFriendlyMessage = computed(() => {
  const error = errorInfo.value

  // Map common errors to user-friendly messages
  if (error.message?.includes('Network Error')) {
    return t('common.errorBoundary.networkError')
  }
  if (error.message?.includes('Failed to fetch')) {
    return t('common.errorBoundary.fetchError')
  }
  if (error.message?.includes('Cannot read properties')) {
    return t('common.errorBoundary.dataError')
  }
  if (error.message?.includes('ChunkLoadError')) {
    return t('common.errorBoundary.chunkLoadError')
  }
  if (error.message?.includes('ResizeObserver loop limit exceeded')) {
    return t('common.errorBoundary.resizeError')
  }

  return props.fallback || t('common.errorBoundary.defaultFallback')
})

// Capture errors from child components
onErrorCaptured((error: Error, instance: any, info: string) => {
  // Combine error and info into a single data object for the logger
  logger.error('Error captured by ErrorBoundary:', { error, info })

  hasError.value = true
  errorInfo.value = {
    message: error.message,
    stack: error.stack,
    componentInfo: info,
    component: instance?.$options?.name || 'Unknown Component'
  }

  // Track error with RUM if available
  if (rum) {
    rum.trackError('component_error', {
      message: error.message,
      stack: error.stack,
      componentInfo: info,
      component: instance?.$options?.name || 'unknown',
      boundaryComponent: 'ErrorBoundary'
    })
  }

  // Call custom error handler if provided
  if (props.onError) {
    props.onError(error, instance, info)
  }

  // Return false to stop the error from propagating
  return false
})

const retry = async () => {
  retrying.value = true
  hasError.value = false

  // Wait a moment before resetting retry state
  setTimeout(() => {
    retrying.value = false
  }, 1000)

  // Track retry attempt
  if (rum) {
    rum.trackUserInteraction('error_boundary_retry', null, {
      component: errorInfo.value.component,
      errorMessage: errorInfo.value.message
    })
  }
}

const reload = () => {
  // Track reload attempt
  if (rum) {
    rum.trackUserInteraction('error_boundary_reload', null, {
      component: errorInfo.value.component,
      errorMessage: errorInfo.value.message
    })
  }

  window.location.reload()
}

const toggleDetails = () => {
  showDetails.value = !showDetails.value

  if (rum) {
    rum.trackUserInteraction('error_boundary_toggle_details', null, {
      expanded: showDetails.value
    })
  }
}

// Reset error state when component is mounted
const reset = () => {
  hasError.value = false
  errorInfo.value = { message: '' }
  showDetails.value = false
  retrying.value = false
}

// Expose reset method for parent components
defineExpose({
  reset,
  hasError: () => hasError.value,
  errorInfo: () => errorInfo.value
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.error-boundary {
  padding: var(--spacing-8);
  background: var(--color-error-bg);
  border-radius: var(--radius-lg);
  border: 2px solid var(--color-error);
  margin: var(--spacing-4) 0;
  box-shadow: var(--shadow-md);
}

.error-container {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-4);
}

.error-icon {
  font-size: var(--text-2xl);
  flex-shrink: 0;
}

.error-content {
  flex: 1;
}

.error-title {
  margin: 0 0 var(--spacing-2) 0;
  color: var(--color-error-dark);
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
}

.error-message {
  margin: 0 0 var(--spacing-4) 0;
  color: var(--text-secondary);
  line-height: var(--leading-relaxed);
}

.error-details {
  margin: var(--spacing-4) 0;
  padding: var(--spacing-4);
  background: var(--bg-overlay);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-error-bg);
}

.error-details-toggle {
  cursor: pointer;
  color: var(--color-error-dark);
  font-weight: var(--font-medium);
}

.error-stack {
  margin-top: var(--spacing-2);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
}

.stack-trace {
  background: var(--bg-secondary);
  padding: var(--spacing-2);
  border-radius: var(--radius-sm);
  margin-top: var(--spacing-2);
  overflow-x: auto;
  white-space: pre;
  max-height: 200px;
  overflow-y: auto;
}

.component-info {
  margin-top: var(--spacing-2);
  color: var(--text-secondary);
}

.error-actions {
  display: flex;
  gap: var(--spacing-2);
  flex-wrap: wrap;
}

@media (max-width: 640px) {
  .error-container {
    flex-direction: column;
    text-align: center;
  }

  .error-actions {
    justify-content: center;
  }
}
</style>
