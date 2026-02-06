/**
 * Unified Loading System for AutoBot
 * Single source of truth for all loading states with automatic timeout and error handling
 */

import { ref, computed, type Ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for useUnifiedLoading
const logger = createLogger('useUnifiedLoading')

export interface LoadingOptions {
  timeout?: number // milliseconds, default 10000 (10 seconds)
  message?: string
  showError?: boolean
  fallbackOnTimeout?: boolean
}

export interface LoadingState {
  isLoading: Ref<boolean>
  error: Ref<string | null>
  message: Ref<string>
  hasTimedOut: Ref<boolean>
}

class UnifiedLoadingManager {
  private states: Map<string, LoadingState> = new Map()
  private timeouts: Map<string, NodeJS.Timeout> = new Map()

  // Global loading state (for app-level loading)
  public readonly global = this.createState('global')

  /**
   * Create or get a loading state for a specific component/feature
   */
  getState(key: string): LoadingState {
    if (!this.states.has(key)) {
      this.states.set(key, this.createState(key))
    }
    return this.states.get(key)!
  }

  private createState(_key: string): LoadingState {
    return {
      isLoading: ref(false),
      error: ref(null),
      message: ref(''),
      hasTimedOut: ref(false)
    }
  }

  /**
   * Start loading with automatic timeout protection
   */
  async startLoading(
    key: string,
    asyncOperation: () => Promise<any>,
    options: LoadingOptions = {}
  ): Promise<any> {
    const {
      timeout = 10000,
      message = 'Loading...',
      showError = true,
      fallbackOnTimeout = true
    } = options

    const state = this.getState(key)

    // Clear any existing timeout
    this.clearTimeout(key)

    // Reset state
    state.isLoading.value = true
    state.error.value = null
    state.message.value = message
    state.hasTimedOut.value = false

    // Set timeout protection
    const timeoutId = setTimeout(() => {
      if (state.isLoading.value) {
        state.hasTimedOut.value = true
        if (fallbackOnTimeout) {
          state.isLoading.value = false
          state.error.value = showError ? `Operation timed out after ${timeout/1000} seconds` : null
          logger.warn(`[Loading] ${key} timed out after ${timeout}ms`)
        }
      }
    }, timeout)

    this.timeouts.set(key, timeoutId)

    try {
      // Execute the async operation
      const result = await asyncOperation()

      // Success - clear loading state
      state.isLoading.value = false
      state.error.value = null
      this.clearTimeout(key)

      return result
    } catch (error) {
      // Error - show error message
      state.isLoading.value = false
      state.error.value = showError ? (error as Error).message : null
      this.clearTimeout(key)

      logger.error(`[Loading] ${key} failed:`, error)
      throw error
    }
  }

  /**
   * Manually stop loading for a specific key
   */
  stopLoading(key: string, error?: string) {
    const state = this.getState(key)
    state.isLoading.value = false
    state.error.value = error || null
    this.clearTimeout(key)
  }

  /**
   * Clear timeout for a specific key
   */
  private clearTimeout(key: string) {
    const timeoutId = this.timeouts.get(key)
    if (timeoutId) {
      clearTimeout(timeoutId)
      this.timeouts.delete(key)
    }
  }

  /**
   * Reset all loading states (useful for route changes)
   */
  resetAll() {
    this.states.forEach((state, key) => {
      state.isLoading.value = false
      state.error.value = null
      state.message.value = ''
      state.hasTimedOut.value = false
      this.clearTimeout(key)
    })
  }

  /**
   * Check if any loading is active
   */
  get anyLoading(): boolean {
    for (const [_, state] of this.states) {
      if (state.isLoading.value) return true
    }
    return false
  }
}

// Singleton instance
const loadingManager = new UnifiedLoadingManager()

/**
 * Vue composable for unified loading management
 */
export function useUnifiedLoading(componentKey?: string) {
  const key = componentKey || 'default'
  const state = loadingManager.getState(key)

  const withLoading = async <T>(
    operation: () => Promise<T>,
    options?: LoadingOptions
  ): Promise<T | null> => {
    try {
      return await loadingManager.startLoading(key, operation, options)
    } catch (_error) {
      // Return null on error to allow component to handle gracefully
      return null
    }
  }

  const setLoading = (loading: boolean, message?: string) => {
    if (loading) {
      state.isLoading.value = true
      state.message.value = message || 'Loading...'
    } else {
      loadingManager.stopLoading(key)
    }
  }

  const setError = (error: string | null) => {
    state.error.value = error
  }

  return {
    // State
    isLoading: computed(() => state.isLoading.value),
    error: computed(() => state.error.value),
    message: computed(() => state.message.value),
    hasTimedOut: computed(() => state.hasTimedOut.value),

    // Methods
    withLoading,
    setLoading,
    setError,
    stopLoading: () => loadingManager.stopLoading(key),

    // Global access
    global: loadingManager.global,
    anyLoading: computed(() => loadingManager.anyLoading)
  }
}

// Export manager for special cases
export { loadingManager }
export default useUnifiedLoading
