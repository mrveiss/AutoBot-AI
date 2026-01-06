<template>
  <div v-if="hasError" class="error-boundary">
    <div class="error-container">
      <div class="error-icon">
        ⚠️
      </div>
      <div class="error-content">
        <h3 class="error-title">Something went wrong</h3>
        <p class="error-message">{{ userFriendlyMessage }}</p>

        <div class="error-details" v-if="showDetails">
          <details>
            <summary class="error-details-toggle">Technical Details</summary>
            <div class="error-stack">
              <pre>{{ errorInfo.message }}</pre>
              <pre v-if="errorInfo.stack" class="stack-trace">{{ errorInfo.stack }}</pre>
              <div v-if="errorInfo.componentInfo" class="component-info">
                <strong>Component:</strong> {{ errorInfo.componentInfo }}
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
            {{ retrying ? 'Retrying...' : 'Try Again' }}
          </BaseButton>
          <BaseButton
            variant="secondary"
            @click="reload"
          >
            Reload Page
          </BaseButton>
          <BaseButton
            variant="ghost"
            @click="toggleDetails"
          >
            {{ showDetails ? 'Hide Details' : 'Show Details' }}
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
import { createLogger } from '@/utils/debugUtils'
import BaseButton from '@/components/base/BaseButton.vue'

const logger = createLogger('ErrorBoundary')

interface Props {
  fallback?: string
  onError?: (error: Error, instance: any, info: string) => void
  showRetry?: boolean
  showReload?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  fallback: 'An unexpected error occurred',
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
    return 'Connection lost. Please check your internet connection and try again.'
  }
  if (error.message?.includes('Failed to fetch')) {
    return 'Unable to connect to the server. Please try again in a moment.'
  }
  if (error.message?.includes('Cannot read properties')) {
    return 'Some data is missing or corrupted. Reloading may help.'
  }
  if (error.message?.includes('ChunkLoadError')) {
    return 'Application update detected. Please reload the page to get the latest version.'
  }
  if (error.message?.includes('ResizeObserver loop limit exceeded')) {
    return 'Display refresh needed. This error is usually harmless.'
  }

  return props.fallback
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
.error-boundary {
  padding: 2rem;
  background: linear-gradient(135deg, #fff5f5 0%, #fed7d7 100%);
  border-radius: 12px;
  border: 2px solid #fc8181;
  margin: 1rem 0;
  box-shadow: 0 4px 12px rgba(252, 129, 129, 0.15);
}

.error-container {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
}

.error-icon {
  font-size: 2rem;
  flex-shrink: 0;
}

.error-content {
  flex: 1;
}

.error-title {
  margin: 0 0 0.5rem 0;
  color: #c53030;
  font-size: 1.25rem;
  font-weight: 600;
}

.error-message {
  margin: 0 0 1rem 0;
  color: #744210;
  line-height: 1.5;
}

.error-details {
  margin: 1rem 0;
  padding: 1rem;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 8px;
  border: 1px solid #fed7d7;
}

.error-details-toggle {
  cursor: pointer;
  color: #c53030;
  font-weight: 500;
}

.error-stack {
  margin-top: 0.5rem;
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 0.875rem;
}

.stack-trace {
  background: #f7fafc;
  padding: 0.5rem;
  border-radius: 4px;
  margin-top: 0.5rem;
  overflow-x: auto;
  white-space: pre;
  max-height: 200px;
  overflow-y: auto;
}

.component-info {
  margin-top: 0.5rem;
  color: #744210;
}

.error-actions {
  display: flex;
  gap: 0.5rem;
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
