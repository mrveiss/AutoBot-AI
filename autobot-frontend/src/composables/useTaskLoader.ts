/**
 * Generic background-task loader composable (#1321).
 *
 * Wraps useBackgroundTask with reactive loading/error/data/progress state.
 * Replaces repetitive background-task loaders in CodebaseAnalytics.
 *
 * Usage:
 *   const deps = useTaskLoader<DependencyGraph>(
 *     '/api/analytics/codebase/analytics/dependencies',
 *     (result) => result.dependency_data as DependencyGraph,
 *   )
 *   await deps.load()   // deps.data.value now holds extracted result
 *
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 */

import { ref, type Ref } from 'vue'
import { useBackgroundTask } from '@/composables/useBackgroundTask'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useTaskLoader')

export interface TaskLoaderReturn<T> {
  data: Ref<T | null>
  loading: Ref<boolean>
  error: Ref<string | null>
  progress: Ref<number>
  currentStep: Ref<string | null>
  wasInterrupted: Ref<boolean>
  load: (
    body?: Record<string, unknown>,
    query?: Record<string, string>,
  ) => Promise<T | null>
  reset: () => void
}

/**
 * Reusable composable for background-task analytics endpoints.
 *
 * @param baseUrl       API path prefix (must expose POST /analyze
 *                      and GET /status/{id}).
 * @param extract       Transform applied to the task result before storing.
 *                      Return `undefined` to signal "no data" (sets data to null).
 * @param clearStuckUrl Forwarded to useBackgroundTask.
 */
export function useTaskLoader<T = Record<string, unknown>>(
  baseUrl: string,
  extract?: (result: Record<string, unknown>) => T | undefined,
  clearStuckUrl?: string,
): TaskLoaderReturn<T> {
  const data: Ref<T | null> = ref(null)
  const task = useBackgroundTask(baseUrl, clearStuckUrl)

  const load = async (
    body?: Record<string, unknown>,
    query?: Record<string, string>,
  ): Promise<T | null> => {
    data.value = null
    const ok = await task.start(body, query)
    if (ok && task.result.value) {
      if (extract) {
        const extracted = extract(task.result.value)
        data.value = extracted !== undefined ? extracted : null
      } else {
        data.value = task.result.value as unknown as T
      }
      return data.value
    }
    if (task.error.value) {
      logger.error(`Task failed for ${baseUrl}: ${task.error.value}`)
    }
    return null
  }

  const reset = () => {
    data.value = null
    task.reset()
  }

  return {
    data,
    loading: task.running,
    error: task.error,
    progress: task.progress,
    currentStep: task.currentStep,
    wasInterrupted: task.wasInterrupted,
    load,
    reset,
  }
}

export default useTaskLoader
