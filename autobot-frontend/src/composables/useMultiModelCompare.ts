// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Multi-model comparison composable (Issue #4414).
 *
 * Manages fan-out SSE state for N models.  Opens a single SSE connection to
 * POST /api/chat/compare, then demultiplexes events by model key.
 *
 * Usage:
 *   const { responses, selectedModels, isComparing, compare, reset } = useMultiModelCompare()
 */

import { ref, type Ref } from 'vue'
import { getBackendUrl, getApiBase } from '@/config/ssot-config'
import { getAuthToken } from '@/utils/fetchWithAuth'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useMultiModelCompare')

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ModelResponse {
  content: string
  done: boolean
  error?: string
}

export interface UseMultiModelCompareReturn {
  /** Per-model streaming responses keyed by 'provider/model'. */
  responses: Ref<Map<string, ModelResponse>>
  /** Currently selected models (persisted in localStorage). */
  selectedModels: Ref<string[]>
  /** True while a fan-out comparison is in progress. */
  isComparing: Ref<boolean>
  /** Start a new comparison.  Resets responses first. */
  compare: (prompt: string, models?: string[]) => Promise<void>
  /** Clear all response state. */
  reset: () => void
}

// ---------------------------------------------------------------------------
// Local-storage persistence
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'autobot_compare_models'

function loadStoredModels(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (Array.isArray(parsed)) return parsed as string[]
  } catch {
    // ignore
  }
  return []
}

function saveModels(models: string[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(models))
  } catch {
    // ignore
  }
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useMultiModelCompare(): UseMultiModelCompareReturn {
  const responses = ref<Map<string, ModelResponse>>(new Map())
  const selectedModels = ref<string[]>(loadStoredModels())
  const isComparing = ref(false)

  // Persist selected models whenever they change (caller is responsible for
  // updating selectedModels; we expose a watcher-free API for simplicity)
  function _persistModels(): void {
    saveModels(selectedModels.value)
  }

  function reset(): void {
    responses.value = new Map()
    isComparing.value = false
  }

  async function compare(prompt: string, models?: string[]): Promise<void> {
    const targetModels = models ?? selectedModels.value
    if (!prompt.trim() || targetModels.length === 0) return

    _persistModels()
    reset()
    isComparing.value = true

    // Initialise placeholders so the UI can render empty cards immediately
    const initial = new Map<string, ModelResponse>()
    for (const m of targetModels) {
      initial.set(m, { content: '', done: false })
    }
    responses.value = initial

    const url = `${getBackendUrl()}${getApiBase()}/chat/compare`
    const token = getAuthToken()
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`

    let fetchResponse: Response
    try {
      fetchResponse = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify({ prompt, models: targetModels }),
      })
    } catch (err) {
      logger.error('compare fetch failed:', err)
      for (const m of targetModels) {
        responses.value.set(m, { content: '', done: true, error: String(err) })
      }
      isComparing.value = false
      return
    }

    if (!fetchResponse.ok || !fetchResponse.body) {
      const msg = `HTTP ${fetchResponse.status}`
      for (const m of targetModels) {
        responses.value.set(m, { content: '', done: true, error: msg })
      }
      isComparing.value = false
      return
    }

    const reader = fetchResponse.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    try {
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // SSE lines are separated by "\n\n"
        let boundary = buffer.indexOf('\n\n')
        while (boundary !== -1) {
          const chunk = buffer.slice(0, boundary)
          buffer = buffer.slice(boundary + 2)

          for (const line of chunk.split('\n')) {
            if (!line.startsWith('data: ')) continue
            try {
              const event = JSON.parse(line.slice(6)) as {
                model: string
                delta?: string
                done?: boolean
                error?: string
              }
              const current = responses.value.get(event.model) ?? { content: '', done: false }
              if (event.error) {
                responses.value.set(event.model, { ...current, done: true, error: event.error })
              } else if (event.delta !== undefined) {
                responses.value.set(event.model, {
                  ...current,
                  content: current.content + event.delta,
                })
              } else if (event.done) {
                responses.value.set(event.model, { ...current, done: true })
              }
            } catch {
              // malformed JSON — skip
            }
          }

          boundary = buffer.indexOf('\n\n')
        }
      }
    } catch (err) {
      logger.error('compare stream read error:', err)
    } finally {
      reader.releaseLock()
      isComparing.value = false
    }
  }

  return { responses, selectedModels, isComparing, compare, reset }
}
