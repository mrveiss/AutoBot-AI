<template>
  <div class="async-error-fallback">
    <div class="error-container">
      <div class="error-icon">
        <i class="fas fa-exclamation-triangle"></i>
      </div>
      <div class="error-content">
        <h3 class="error-title">Failed to Load Component</h3>
        <p class="error-message">{{ errorMessage }}</p>

        <div class="error-details" v-if="showDetails">
          <details>
            <summary class="error-details-toggle">Technical Details</summary>
            <div class="error-stack">
              <pre>{{ error?.message }}</pre>
              <pre v-if="error?.stack" class="stack-trace">{{ error.stack }}</pre>
              <div class="error-info">
                <strong>Component:</strong> {{ componentName }}<br>
                <strong>Retry Attempts:</strong> {{ retryCount }}/{{ maxRetries }}<br>
                <strong>Time:</strong> {{ new Date().toLocaleString() }}
              </div>
            </div>
          </details>
        </div>

        <div class="error-actions">
          <BaseButton
            variant="primary"
            @click="retry"
            :disabled="retrying || retryCount >= maxRetries"
          >
            <i class="fas fa-redo" :class="{ 'fa-spin': retrying }"></i>
            {{ retrying ? 'Retrying...' : `Retry${retryCount > 0 ? ` (${retryCount}/${maxRetries})` : ''}` }}
          </BaseButton>

          <BaseButton
            variant="secondary"
            @click="reload"
          >
            <i class="fas fa-refresh"></i>
            Reload Page
          </BaseButton>

          <BaseButton
            variant="outline"
            @click="goHome"
          >
            <i class="fas fa-home"></i>
            Go to Home
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
</template>

<script setup lang="ts">
import { ref, computed, inject, withDefaults } from 'vue'
import { useRouter } from 'vue-router'
import BaseButton from '@/components/base/BaseButton.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('AsyncErrorFallback')

interface Props {
  error?: Error
  componentName?: string
  retryCount?: number
  maxRetries?: number
  onRetry?: () => void
}

const props = withDefaults(defineProps<Props>(), {
  componentName: 'Unknown Component',
  retryCount: 0,
  maxRetries: 3
})

const emit = defineEmits<{
  retry: []
}>()

const router = useRouter()
const showDetails = ref(false)
const retrying = ref(false)

// Inject RUM agent if available
const rum = inject('rum', null) as any

// Compute user-friendly error message based on error type
const errorMessage = computed(() => {
  const error = props.error

  if (!error) return 'An unknown error occurred while loading the component.'

  if (error.message?.includes('Loading chunk') || error.message?.includes('ChunkLoadError')) {
    return 'This page failed to load due to a network issue or application update. Please try refreshing the page.'
  }

  if (error.message?.includes('Loading CSS chunk')) {
    return 'The page styles failed to load. Your browser may be using an outdated version.'
  }

  if (error.message?.includes('Failed to fetch')) {
    return 'Unable to download the required files. Please check your internet connection.'
  }

  if (error.message?.includes('NetworkError')) {
    return 'Network connection failed while loading the component. Please check your internet connection.'
  }

  if (error.message?.includes('timeout')) {
    return 'The component took too long to load. Please try again or check your connection.'
  }

  return `Failed to load ${props.componentName}. This may be due to a temporary network issue.`
})

const retry = async () => {
  if (retrying.value || props.retryCount >= props.maxRetries) return

  retrying.value = true

  // Track retry attempt
  if (rum) {
    rum.trackUserInteraction('async_component_retry', null, {
      component: props.componentName,
      errorMessage: props.error?.message,
      retryCount: props.retryCount + 1,
      maxRetries: props.maxRetries
    })
  }

  // Log retry attempt

  try {
    // Wait a moment before retrying (exponential backoff)
    const delay = Math.min(1000 * Math.pow(2, props.retryCount), 5000)
    await new Promise(resolve => setTimeout(resolve, delay))

    // Emit retry event to parent
    emit('retry')

    // If custom retry handler provided, call it
    if (props.onRetry) {
      await props.onRetry()
    }

  } catch (retryError: unknown) {
    // Properly type the retry error
    const typedRetryError = retryError instanceof Error ? retryError : new Error(String(retryError))
    logger.error(`Retry failed for ${props.componentName}:`, typedRetryError)

    if (rum) {
      rum.trackError('async_component_retry_failed', {
        component: props.componentName,
        originalError: props.error?.message,
        retryError: typedRetryError.message,
        retryCount: props.retryCount + 1
      })
    }
  } finally {
    retrying.value = false
  }
}

const reload = () => {
  // Track reload attempt
  if (rum) {
    rum.trackUserInteraction('async_component_reload', null, {
      component: props.componentName,
      errorMessage: props.error?.message,
      retryCount: props.retryCount
    })
  }


  // Clear any cached chunks and reload
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.getRegistrations().then(registrations => {
      registrations.forEach(registration => registration.unregister())
    }).finally(() => {
      window.location.reload()
    })
  } else {
    window.location.reload()
  }
}

const goHome = () => {
  // Track navigation to home
  if (rum) {
    rum.trackUserInteraction('async_component_go_home', null, {
      component: props.componentName,
      errorMessage: props.error?.message
    })
  }

  router.push('/chat').catch(err => {
    logger.error('Failed to navigate to home:', err)
    // Last resort - hard navigation
    window.location.href = '/chat'
  })
}

const toggleDetails = () => {
  showDetails.value = !showDetails.value

  if (rum) {
    rum.trackUserInteraction('async_error_toggle_details', null, {
      expanded: showDetails.value,
      component: props.componentName
    })
  }
}

// Log error for debugging
if (props.error) {
  logger.error('Component loading failed:', {
    component: props.componentName,
    error: props.error,
    retryCount: props.retryCount,
    timestamp: new Date().toISOString()
  })

  // Track error with RUM
  if (rum) {
    rum.trackError('async_component_load_failed', {
      component: props.componentName,
      message: props.error.message,
      stack: props.error.stack,
      retryCount: props.retryCount,
      maxRetries: props.maxRetries
    })
  }
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.async-error-fallback {
  min-height: 300px;
  padding: var(--spacing-8);
  background: linear-gradient(135deg, var(--color-warning-bg) 0%, var(--color-warning-bg-hover) 100%);
  border-radius: var(--radius-xl);
  border: 2px solid var(--color-warning);
  margin: var(--spacing-4);
  box-shadow: var(--shadow-warning);
  display: flex;
  align-items: center;
  justify-content: center;
}

.error-container {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-6);
  max-width: 600px;
  width: 100%;
}

.error-icon {
  font-size: var(--text-4xl);
  color: var(--color-warning-hover);
  flex-shrink: 0;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

.error-content {
  flex: 1;
}

.error-title {
  margin: 0 0 var(--spacing-3) 0;
  color: var(--color-warning-active);
  font-size: var(--text-2xl);
  font-weight: var(--font-semibold);
}

.error-message {
  margin: 0 0 var(--spacing-6) 0;
  color: var(--color-error-hover);
  line-height: var(--leading-relaxed);
  font-size: var(--text-base);
}

.error-details {
  margin: var(--spacing-6) 0;
  padding: var(--spacing-4);
  background: var(--bg-primary-transparent);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-warning);
}

.error-details-toggle {
  cursor: pointer;
  color: var(--color-warning-hover);
  font-weight: var(--font-medium);
  font-size: var(--text-sm);
}

.error-stack {
  margin-top: var(--spacing-3);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
}

.stack-trace {
  background: var(--bg-tertiary);
  padding: var(--spacing-3);
  border-radius: var(--radius-sm);
  margin: var(--spacing-2) 0;
  overflow-x: auto;
  white-space: pre;
  max-height: 200px;
  overflow-y: auto;
  border: 1px solid var(--border-default);
}

.error-info {
  margin-top: var(--spacing-3);
  color: var(--color-error-hover);
  font-size: var(--text-sm);
  line-height: var(--leading-normal);
}

.error-actions {
  display: flex;
  gap: var(--spacing-3);
  flex-wrap: wrap;
}

.fa-spin {
  animation: fa-spin 1s infinite linear;
}

@keyframes fa-spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

@media (max-width: 640px) {
  .async-error-fallback {
    padding: var(--spacing-4);
    margin: var(--spacing-2);
  }

  .error-container {
    flex-direction: column;
    text-align: center;
    gap: var(--spacing-4);
  }

  .error-icon {
    font-size: var(--text-3xl);
  }

  .error-title {
    font-size: var(--text-xl);
  }

  .error-actions {
    justify-content: center;
    gap: var(--spacing-2);
  }

  .btn {
    padding: var(--spacing-2-5) var(--spacing-4);
    font-size: var(--text-sm);
    min-width: 80px;
  }
}
</style>