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
          <button
            @click="retry"
            class="btn btn-primary"
            :disabled="retrying || retryCount >= maxRetries"
          >
            <i class="fas fa-redo" :class="{ 'fa-spin': retrying }"></i>
            {{ retrying ? 'Retrying...' : `Retry${retryCount > 0 ? ` (${retryCount}/${maxRetries})` : ''}` }}
          </button>

          <button
            @click="reload"
            class="btn btn-secondary"
          >
            <i class="fas fa-refresh"></i>
            Reload Page
          </button>

          <button
            @click="goHome"
            class="btn btn-outline"
          >
            <i class="fas fa-home"></i>
            Go to Home
          </button>

          <button
            @click="toggleDetails"
            class="btn btn-ghost"
          >
            {{ showDetails ? 'Hide Details' : 'Show Details' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, withDefaults } from 'vue'
import { useRouter } from 'vue-router'

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
  console.log(`[AsyncErrorFallback] Retrying component: ${props.componentName}, attempt ${props.retryCount + 1}`)

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

  } catch (retryError) {
    console.error(`[AsyncErrorFallback] Retry failed for ${props.componentName}:`, retryError)

    if (rum) {
      rum.trackError('async_component_retry_failed', {
        component: props.componentName,
        originalError: props.error?.message,
        retryError: retryError.message,
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

  console.log(`[AsyncErrorFallback] Reloading page due to ${props.componentName} failure`)

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

  console.log(`[AsyncErrorFallback] Navigating to home due to ${props.componentName} failure`)
  router.push('/chat').catch(err => {
    console.error('Failed to navigate to home:', err)
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
  console.error(`[AsyncErrorFallback] Component loading failed:`, {
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
.async-error-fallback {
  min-height: 300px;
  padding: 2rem;
  background: linear-gradient(135deg, #fff8e1 0%, #ffecb3 100%);
  border-radius: 12px;
  border: 2px solid #ffb74d;
  margin: 1rem;
  box-shadow: 0 4px 12px rgba(255, 183, 77, 0.15);
  display: flex;
  align-items: center;
  justify-content: center;
}

.error-container {
  display: flex;
  align-items: flex-start;
  gap: 1.5rem;
  max-width: 600px;
  width: 100%;
}

.error-icon {
  font-size: 3rem;
  color: #f57c00;
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
  margin: 0 0 0.75rem 0;
  color: #e65100;
  font-size: 1.5rem;
  font-weight: 600;
}

.error-message {
  margin: 0 0 1.5rem 0;
  color: #bf360c;
  line-height: 1.6;
  font-size: 1rem;
}

.error-details {
  margin: 1.5rem 0;
  padding: 1rem;
  background: rgba(255, 255, 255, 0.8);
  border-radius: 8px;
  border: 1px solid #ffcc02;
}

.error-details-toggle {
  cursor: pointer;
  color: #f57c00;
  font-weight: 500;
  font-size: 0.9rem;
}

.error-stack {
  margin-top: 0.75rem;
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 0.875rem;
}

.stack-trace {
  background: #f5f5f5;
  padding: 0.75rem;
  border-radius: 4px;
  margin: 0.5rem 0;
  overflow-x: auto;
  white-space: pre;
  max-height: 200px;
  overflow-y: auto;
  border: 1px solid #e0e0e0;
}

.error-info {
  margin-top: 0.75rem;
  color: #bf360c;
  font-size: 0.875rem;
  line-height: 1.5;
}

.error-actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.btn {
  padding: 0.75rem 1.25rem;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 500;
  font-size: 0.9rem;
  transition: all 0.2s ease;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  min-width: 100px;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary {
  background: #2196f3;
  color: white;
  box-shadow: 0 2px 4px rgba(33, 150, 243, 0.3);
}

.btn-primary:hover:not(:disabled) {
  background: #1976d2;
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(33, 150, 243, 0.4);
}

.btn-secondary {
  background: #607d8b;
  color: white;
  box-shadow: 0 2px 4px rgba(96, 125, 139, 0.3);
}

.btn-secondary:hover:not(:disabled) {
  background: #455a64;
  transform: translateY(-1px);
}

.btn-outline {
  background: transparent;
  color: #f57c00;
  border: 2px solid #f57c00;
}

.btn-outline:hover {
  background: #f57c00;
  color: white;
  transform: translateY(-1px);
}

.btn-ghost {
  background: transparent;
  color: #757575;
  border: 1px solid #bdbdbd;
}

.btn-ghost:hover {
  background: #f5f5f5;
  border-color: #9e9e9e;
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
    padding: 1rem;
    margin: 0.5rem;
  }

  .error-container {
    flex-direction: column;
    text-align: center;
    gap: 1rem;
  }

  .error-icon {
    font-size: 2rem;
  }

  .error-title {
    font-size: 1.25rem;
  }

  .error-actions {
    justify-content: center;
    gap: 0.5rem;
  }

  .btn {
    padding: 0.6rem 1rem;
    font-size: 0.85rem;
    min-width: 80px;
  }
}
</style>