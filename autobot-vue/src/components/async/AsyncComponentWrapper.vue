<template>
  <Suspense @error="handleAsyncError">
    <template #default>
      <component
        :is="asyncComponent"
        v-bind="{ ...componentProps, ...attrs }"
        @error="handleComponentError"
      />
    </template>

    <template #fallback>
      <div class="async-loading">
        <div class="loading-container">
          <div class="loading-spinner">
            <div class="spinner-ring"></div>
            <div class="spinner-ring"></div>
            <div class="spinner-ring"></div>
          </div>
          <div class="loading-content">
            <h3 class="loading-title">Loading {{ componentDisplayName }}...</h3>
            <p class="loading-message">{{ loadingMessage }}</p>
            <div class="loading-progress">
              <div class="progress-bar" :style="{ width: `${loadingProgress}%` }"></div>
            </div>
            <div class="loading-time">{{ formatLoadingTime(loadingTime) }}</div>
          </div>
        </div>
      </div>
    </template>
  </Suspense>

  <!-- Custom error fallback for async loading failures -->
  <AsyncErrorFallback
    v-if="showAsyncError"
    :error="asyncError ?? undefined"
    :component-name="componentDisplayName"
    :retry-count="retryCount"
    :max-retries="maxRetries"
    @retry="retryAsyncLoad"
  />
</template>

<script setup lang="ts">
import { ref, computed, onUnmounted, inject, withDefaults, useAttrs } from 'vue'
import type { Component, AsyncComponentLoader } from 'vue'
import AsyncErrorFallback from './AsyncErrorFallback.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('AsyncComponentWrapper')

// Disable automatic attribute inheritance to handle manually
defineOptions({
  inheritAttrs: false
})

interface RumAgent {
  trackError: (type: string, data: Record<string, unknown>) => void
  trackUserInteraction: (type: string, element: unknown, data: Record<string, unknown>) => void
}

interface Props {
  componentLoader: AsyncComponentLoader
  componentName?: string
  componentProps?: Record<string, unknown>
  loadingMessage?: string
  maxRetries?: number
  retryDelay?: number
  timeout?: number
}

const props = withDefaults(defineProps<Props>(), {
  componentName: 'Component',
  componentProps: () => ({}),
  loadingMessage: 'Please wait while we load the component...',
  maxRetries: 3,
  retryDelay: 1000,
  timeout: 10000
})

const emit = defineEmits<{
  loaded: [component: Component]
  error: [error: Error]
  retry: [attempt: number]
}>()

// Get attributes to pass to child component
const attrs = useAttrs()

// State
const asyncError = ref<Error | null>(null)
const showAsyncError = ref(false)
const retryCount = ref(0)
const loadingTime = ref(0)
const loadingProgress = ref(0)

// Computed
const componentDisplayName = computed(() => {
  return props.componentName
    .replace(/([A-Z])/g, ' $1')
    .trim()
    .replace(/^./, (str) => str.toUpperCase())
})

// RUM tracking
const rum = inject<RumAgent>('rum', {
  trackError: () => {},
  trackUserInteraction: () => {}
})

// Loading timer - use browser-compatible types instead of NodeJS
let loadingStartTime = 0
let loadingTimer: ReturnType<typeof setInterval> | null = null
let progressTimer: ReturnType<typeof setInterval> | null = null

// Create async component with retry logic
const asyncComponent = ref<Component | null>(null)

async function loadComponent(attempt = 1): Promise<void> {
  try {
    loadingStartTime = Date.now()
    startLoadingTimer()
    startProgressAnimation()


    const component = await props.componentLoader()

    if (component) {
      asyncComponent.value = component.default || component
      // Fix emit type issue - ensure component is not null
      if (asyncComponent.value) {
        emit('loaded', asyncComponent.value)
      }

      const loadTime = Date.now() - loadingStartTime

      // Reset error state on success
      asyncError.value = null
      showAsyncError.value = false
      retryCount.value = 0
    }
  } catch (error: unknown) {
    logger.error(`Failed to load ${props.componentName}:`, error)

    // Properly type the error
    const typedError = error instanceof Error ? error : new Error(String(error))
    asyncError.value = typedError

    // Track loading error
    rum.trackError('async_component_load_failed', {
      component: props.componentName,
      attempt,
      message: typedError.message,
      stack: typedError.stack
    })

    if (attempt < props.maxRetries) {
      retryCount.value = attempt

      emit('retry', attempt + 1)

      // Exponential backoff delay
      const delay = Math.min(props.retryDelay * Math.pow(2, attempt - 1), 5000)
      await new Promise(resolve => setTimeout(resolve, delay))

      return loadComponent(attempt + 1)
    } else {
      // Max retries reached
      logger.error(`Max retries reached for ${props.componentName}`)
      showAsyncError.value = true
      emit('error', typedError)
    }
  } finally {
    stopLoadingTimer()
    stopProgressAnimation()
  }
}

function handleAsyncError(error: Error) {
  logger.error(`Suspense error in ${props.componentName}:`, error)
  asyncError.value = error
  showAsyncError.value = true
  emit('error', error)
}

function handleComponentError(error: Error) {
  logger.error(`Component error in ${props.componentName}:`, error)
  asyncError.value = error
  emit('error', error)
}

function retryAsyncLoad() {
  asyncError.value = null
  showAsyncError.value = false
  retryCount.value = 0
  loadComponent()
}

function startLoadingTimer() {
  loadingTimer = setInterval(() => {
    loadingTime.value = Date.now() - loadingStartTime
  }, 100)
}

function stopLoadingTimer() {
  if (loadingTimer) {
    clearInterval(loadingTimer)
    loadingTimer = null
  }
}

function startProgressAnimation() {
  loadingProgress.value = 0
  progressTimer = setInterval(() => {
    if (loadingProgress.value < 90) {
      loadingProgress.value += Math.random() * 3
    }
  }, 200)
}

function stopProgressAnimation() {
  if (progressTimer) {
    clearInterval(progressTimer)
    progressTimer = null
  }
  loadingProgress.value = 100
}

function formatLoadingTime(time: number): string {
  if (time < 1000) {
    return `${time}ms`
  }
  return `${(time / 1000).toFixed(1)}s`
}

// Start loading on mount
loadComponent()

// Cleanup on unmount
onUnmounted(() => {
  stopLoadingTimer()
  stopProgressAnimation()
})
</script>

<style scoped>
.async-loading {
  @apply flex items-center justify-center min-h-64 p-8;
}

.loading-container {
  @apply text-center max-w-md mx-auto;
}

.loading-spinner {
  @apply relative inline-flex items-center justify-center w-16 h-16 mb-6;
}

.spinner-ring {
  @apply absolute border-2 border-transparent rounded-full animate-spin;
}

.spinner-ring:nth-child(1) {
  @apply w-16 h-16 border-t-blue-500 border-r-blue-500;
  animation: spin 1.5s linear infinite;
}

.spinner-ring:nth-child(2) {
  @apply w-12 h-12 border-t-green-500 border-r-green-500;
  animation: spin 1s linear infinite reverse;
}

.spinner-ring:nth-child(3) {
  @apply w-8 h-8 border-t-purple-500 border-r-purple-500;
  animation: spin 2s linear infinite;
}

.loading-title {
  @apply text-xl font-semibold text-gray-700 mb-2;
}

.loading-message {
  @apply text-gray-600 mb-4;
}

.loading-progress {
  @apply w-full bg-gray-200 rounded-full h-2 mb-4;
}

.progress-bar {
  @apply bg-blue-500 h-2 rounded-full transition-all duration-300 ease-out;
}

.loading-time {
  @apply text-sm text-gray-500;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>