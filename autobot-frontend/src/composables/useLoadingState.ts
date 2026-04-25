// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref } from 'vue'
import type { Ref } from 'vue'

/**
 * Lightweight composable that eliminates the manual isLoading boilerplate:
 *   isLoading.value = true
 *   try { ... } finally { isLoading.value = false }
 *
 * Usage:
 *   const { isLoading, wrap } = useLoadingState()
 *   async function doSomething() {
 *     return wrap(() => apiClient.post('/endpoint', payload))
 *   }
 */
export function useLoadingState(initial = false): {
  isLoading: Ref<boolean>
  wrap: <T>(fn: () => Promise<T>) => Promise<T>
} {
  const isLoading = ref(initial)

  async function wrap<T>(fn: () => Promise<T>): Promise<T> {
    isLoading.value = true
    try {
      return await fn()
    } finally {
      isLoading.value = false
    }
  }

  return { isLoading, wrap }
}

export default useLoadingState
