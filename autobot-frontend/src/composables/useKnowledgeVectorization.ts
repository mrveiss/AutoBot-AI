/**
 * useKnowledgeVectorization Composable
 *
 * Manages vectorization state, batch operations, and status tracking for knowledge base documents.
 * Provides hooks for backend integration when individual document vectorization endpoints are available.
 * Issue #4006: Added request deduplication with TTL caching and debouncing for batch status calls
 */

import { ref, computed } from 'vue'
import { useKnowledgeJobs } from './knowledge/useKnowledgeJobs'
import { usePollingJob } from './usePollingJob'
import { useBatchSelection } from './useBatchSelection'
import apiClient from '@/utils/ApiClient'
import appConfig from '@/config/AppConfig.js'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'

// Create scoped logger for useKnowledgeVectorization

/** Response shape from /knowledge_base/vectorization_status */
interface VectorizationStatusResponse {
  statuses: Record<string, { vectorized: boolean; [key: string]: unknown }>
  [key: string]: unknown
}

/** Response shape from /knowledge_base/vectorize_fact/:id and /knowledge_base/vectorize_documents */
interface VectorizationJobResponse {
  job_id?: string
  status?: string
  [key: string]: unknown
}

/** Response shape from /knowledge_base/vectorize_job/:id */
interface VectorizationJobStatusResponse {
  status?: string
  progress?: number
  error?: string
  [key: string]: unknown
}

const logger = createLogger('useKnowledgeVectorization')

// Request cache for batch status API calls (Issue #4006)
interface CachedRequest {
  data: Promise<void>
  time: number
}

// Constants for request deduplication (Issue #4006)
const BATCH_STATUS_CACHE_TTL = 30000 // 30 seconds

export type VectorizationStatus = 'vectorized' | 'pending' | 'failed' | 'unknown'

export interface DocumentVectorizationState {
  documentId: string
  name?: string
  status: VectorizationStatus
  progress?: number
  error?: string
  lastUpdated?: Date
  // Issue #165: Track document changes - indicates content changed since last vectorization
  needsReindex?: boolean
  contentHash?: string
}

export interface VectorizationProgress {
  total: number
  completed: number
  failed: number
  inProgress: number
}

export function useKnowledgeVectorization() {
  const { vectorizeFacts, getVectorizationStatus } = useKnowledgeJobs()

  // State
  const documentStates = ref<Map<string, DocumentVectorizationState>>(new Map())
  const globalProgress = ref<VectorizationProgress>({
    total: 0,
    completed: 0,
    failed: 0,
    inProgress: 0
  })

  // Request deduplication cache (Issue #4006)
  const requestCache = new Map<string, CachedRequest>()

  // Batch selection state (#5192). This composable never owned a reactive list
  // of document IDs — selection was always driven by caller-supplied IDs — so
  // we wire `useBatchSelection` against an empty items source and expose
  // id-centric shims below. The shared Set<Key> state, toggle/select/deselect
  // primitives, and selectedCount derivation are reused.
  const selection = useBatchSelection<string, string>(ref<string[]>([]))

  // Preserve the existing public API shape (Ref<Set<string>>, string[]).
  // `selection.selected` is typed `Readonly<Ref<Set<string>>>` because we
  // instantiated `useBatchSelection<string, string>` above.
  const selectedDocuments = selection.selected
  const selectionCount = selection.selectedCount
  const hasSelection = computed(() => selection.selectedCount.value > 0)
  const selectedDocumentsList = computed<string[]>(() => Array.from(selection.selected.value))

  const canVectorizeSelection = computed(() => {
    return selectedDocumentsList.value.some(docId => {
      const state = documentStates.value.get(docId)
      return !state || state.status !== 'vectorized'
    })
  })

  // ==================== REQUEST DEDUPLICATION (Issue #4006) ====================

  /**
   * Generate a cache key for a batch of document IDs
   * Sorts IDs to ensure same batch gets same key regardless of order
   */
  const generateCacheKey = (documentIds: string[]): string => {
    return [...documentIds].sort().join('|')
  }

  /**
   * Clear expired cache entries
   */
  const clearExpiredCache = () => {
    const now = Date.now()
    for (const [key, cached] of requestCache.entries()) {
      if (now - cached.time > BATCH_STATUS_CACHE_TTL) {
        requestCache.delete(key)
      }
    }
  }

  /**
   * Clear entire request cache (used for cleanup)
   */
  const clearRequestCache = () => {
    requestCache.clear()
  }

  // ==================== DOCUMENT STATE MANAGEMENT ====================

  /**
   * Get vectorization status for a document (synchronous - from cache)
   * Returns cached status or 'pending' if not yet loaded
   * Use fetchDocumentStatus() to load from backend
   */
  const getDocumentStatus = (documentId: string): VectorizationStatus => {
    const state = documentStates.value.get(documentId)
    return state?.status || 'pending'
  }

  /**
   * Fetch vectorization status for a document from backend
   * Queries the actual Redis vectorization state via backend API
   * Updates cache with result
   */
  const fetchDocumentStatus = async (documentId: string): Promise<VectorizationStatus> => {
    try {
      // Query actual backend status
      const data = await apiClient.post<VectorizationStatusResponse>(`${getApiBase()}/knowledge_base/vectorization_status`, {
        fact_ids: [documentId],
        use_cache: true
      })

      if (data?.statuses?.[documentId]) {
        const status: VectorizationStatus = data.statuses[documentId].vectorized ? 'vectorized' : 'pending'
        setDocumentStatus(documentId, status)
        return status
      }

      // If no data returned, default to pending
      setDocumentStatus(documentId, 'pending')
      return 'pending'
    } catch (error) {
      logger.error('Failed to fetch document vectorization status:', error)
      // On error, mark as unknown
      setDocumentStatus(documentId, 'unknown')
      return 'unknown'
    }
  }

  /**
   * Fetch vectorization status for multiple documents in batch.
   * Issue #4006: Added request deduplication with TTL caching to avoid duplicate API calls.
   *
   * The function maintains a cache of recent requests with a 30-second TTL. If the same
   * batch of document IDs is requested within the TTL window, the cached promise is returned
   * instead of making a new API call. This significantly reduces API load when the component
   * renders multiple times or when multiple components request the same batch simultaneously.
   *
   * Cache keys are order-invariant (sorted), so [doc1, doc2] and [doc2, doc1] use the same cache.
   *
   * @param documentIds - List of document IDs to check
   * @param documentNames - Optional map of document ID to display name (Issue #165)
   */
  const fetchBatchStatus = async (
    documentIds: string[],
    documentNames?: Map<string, string>
  ): Promise<void> => {
    if (documentIds.length === 0) return

    // Issue #4006: Check request cache for deduplication
    clearExpiredCache()
    const cacheKey = generateCacheKey(documentIds)
    const cached = requestCache.get(cacheKey)

    if (cached && Date.now() - cached.time < BATCH_STATUS_CACHE_TTL) {
      logger.debug(`Using cached batch status for ${documentIds.length} documents (age: ${Date.now() - cached.time}ms)`)
      return cached.data
    }

    // Create the fetch promise
    const fetchPromise = (async () => {
      try {
        // Query backend in batches of 1000 (API limit)
        const batchSize = 1000
        for (let i = 0; i < documentIds.length; i += batchSize) {
          const batch = documentIds.slice(i, i + batchSize)

          const data = await apiClient.post<VectorizationStatusResponse>(`${getApiBase()}/knowledge_base/vectorization_status`, {
            fact_ids: batch,
            use_cache: true
          })

          if (data?.statuses) {
            // Update cache with all statuses, including document names if provided (Issue #165)
            Object.entries(data.statuses).forEach(([docId, statusData]) => {
              const status: VectorizationStatus = statusData.vectorized ? 'vectorized' : 'pending'
              const name = documentNames?.get(docId)
              setDocumentStatus(docId, status, undefined, undefined, name)
            })
          }
        }
      } catch (error) {
        logger.error('Failed to fetch batch vectorization status:', error)
        // Mark all as unknown on error, preserving names if provided (Issue #165)
        documentIds.forEach(id => {
          const name = documentNames?.get(id)
          setDocumentStatus(id, 'unknown', undefined, undefined, name)
        })
      }
    })()

    // Issue #4006: Store in cache for deduplication
    requestCache.set(cacheKey, {
      data: fetchPromise,
      time: Date.now()
    })

    logger.debug(`Fetching batch status for ${documentIds.length} documents`)
    return fetchPromise
  }

  /**
   * Set vectorization status for a document
   * Issue #165: Added needsReindex and contentHash parameters for change tracking
   */
  const setDocumentStatus = (
    documentId: string,
    status: VectorizationStatus,
    progress?: number,
    error?: string,
    name?: string,
    needsReindex?: boolean,
    contentHash?: string
  ) => {
    // Preserve existing values if not provided
    const existingState = documentStates.value.get(documentId)
    const documentName = name || existingState?.name
    const documentNeedsReindex = needsReindex ?? existingState?.needsReindex
    const documentContentHash = contentHash || existingState?.contentHash

    documentStates.value.set(documentId, {
      documentId,
      name: documentName,
      status,
      progress,
      error,
      lastUpdated: new Date(),
      needsReindex: documentNeedsReindex,
      contentHash: documentContentHash
    })
  }

  /**
   * Mark a document as needing reindexing (content changed)
   * Issue #165: Allows UI to indicate which documents have changed
   */
  const markDocumentChanged = (documentId: string, newContentHash?: string) => {
    const existingState = documentStates.value.get(documentId)
    if (existingState) {
      documentStates.value.set(documentId, {
        ...existingState,
        needsReindex: true,
        contentHash: newContentHash,
        lastUpdated: new Date()
      })
    } else {
      // Create new state with pending status
      setDocumentStatus(documentId, 'pending', undefined, undefined, undefined, true, newContentHash)
    }
  }

  /**
   * Clear document status (remove from tracking)
   */
  const clearDocumentStatus = (documentId: string) => {
    documentStates.value.delete(documentId)
  }

  /**
   * Clear all document statuses
   */
  const clearAllStatuses = () => {
    documentStates.value.clear()
  }

  // ==================== BATCH SELECTION MANAGEMENT ====================
  // Thin id-centric shims around `useBatchSelection` (#5192) to preserve this
  // composable's historical public API. The underlying state lives on
  // `selection` declared above.

  const toggleDocumentSelection = (documentId: string) => selection.toggle(documentId)
  const selectDocument = (documentId: string) => selection.select(documentId)
  const deselectDocument = (documentId: string) => selection.deselect(documentId)
  /**
   * Add the given document IDs to the current selection. Additive (existing
   * selections are preserved). Uses a single `setSelected()` assignment so the
   * cost is O(n + m) rather than O(n · m) — a per-id `selection.select()` loop
   * copies the backing Set on every call, which makes 10k-id selections take
   * ~12 s (#5412).
   */
  const selectAll = (documentIds: string[]) => {
    // #5412: O(n+m) additive bulk-add. Docstring says "existing selections
    // preserved" — so we merge the new ids into the existing selection
    // and assign once. (#5366's prior fix was also O(n) but silently
    // changed selectAll to replacement semantics, which violates the
    // docstring and may break callers that rely on incremental selection.)
    const merged = new Set<string>(selection.selected.value)
    for (const id of documentIds) merged.add(id)
    selection.setSelected(merged)
  }
  const deselectAll = () => selection.clear()
  const isDocumentSelected = (documentId: string): boolean => selection.isSelected(documentId)

  // ==================== VECTORIZATION OPERATIONS ====================

  /**
   * Vectorize a single document
   * Uses knowledge-specific timeout from AppConfig (VITE_KNOWLEDGE_TIMEOUT, default 300s)
   *
   * Expected endpoint: POST /api/knowledge_base/vectorize_fact/{document_id}
   */
  const vectorizeDocument = async (documentId: string): Promise<boolean> => {
    try {
      setDocumentStatus(documentId, 'pending', 0)

      // Get knowledge-specific timeout (300s for vectorization operations)
      const knowledgeTimeout = appConfig.getTimeout('knowledge')

      // Call backend API to vectorize the fact with proper timeout
      const data = await apiClient.post<VectorizationJobResponse>(`${getApiBase()}/knowledge_base/vectorize_fact/${documentId}`, undefined, {
        timeout: knowledgeTimeout
      })

      // Check if backend returned success status
      if (data.status !== 'success') {
        throw new Error(`Vectorization failed: ${data.message || 'Unknown error'}`)
      }

      const jobId = data.job_id

      // Poll for completion
      let completed = false
      let attempts = 0
      // Configurable timeout via environment variable (default: 60 seconds)
      const maxAttempts = Number(import.meta.env.VITE_VECTORIZATION_TIMEOUT) || 60

      while (!completed && attempts < maxAttempts) {
        await new Promise(resolve => setTimeout(resolve, 1000)) // Wait 1 second

        // Use knowledge timeout for job status polling as well
        const jobData = await apiClient.get<VectorizationJobStatusResponse>(`${getApiBase()}/knowledge_base/vectorize_job/${jobId}`, {
          timeout: knowledgeTimeout
        })

        // Backend returns: { status: "success", job: { status: "completed", error: null, ... } }
        const job = jobData.job

        if (!job) {
          throw new Error('Invalid job status response')
        }

        if (job.status === 'completed') {
          completed = true
          setDocumentStatus(documentId, 'vectorized', 100)
        } else if (job.status === 'failed') {
          throw new Error(job.error || 'Vectorization failed')
        } else {
          // Update progress
          const progress = Math.min(95, (attempts / maxAttempts) * 100)
          setDocumentStatus(documentId, 'pending', progress)
        }

        attempts++
      }

      if (!completed) {
        throw new Error('Vectorization timed out')
      }

      return true
    } catch (error) {
      logger.error('Failed to vectorize document:', error)
      setDocumentStatus(documentId, 'failed', 0, String(error))
      return false
    }
  }

  /**
   * Attempt batch vectorization via the dedicated batch endpoint.
   * Returns the per-document result map on success, throws on network/server error.
   * Issue #2077: POST /api/knowledge_base/vectorize_documents
   */
  const _tryBatchEndpoint = async (
    documentIds: string[]
  ): Promise<{ succeeded: string[], failed: string[] }> => {
    const knowledgeTimeout = appConfig.getTimeout('knowledge')
    const batchTimeout = Math.min(knowledgeTimeout * documentIds.length, 300000)
    const data = await apiClient.post<VectorizationJobResponse>(`${getApiBase()}/knowledge_base/vectorize_documents`, {
      document_ids: documentIds
    }, {
      timeout: batchTimeout
    })

    const succeeded: string[] = []
    const failed: string[] = []

    for (const result of data.results ?? []) {
      if (result.status === 'success') {
        setDocumentStatus(result.id, 'vectorized', 100)
        succeeded.push(result.id)
      } else {
        setDocumentStatus(result.id, 'failed', 0, result.error ?? undefined)
        failed.push(result.id)
      }
    }

    return { succeeded, failed }
  }

  /**
   * Vectorize multiple documents in batch.
   *
   * Calls POST /api/knowledge_base/vectorize_documents (Issue #2077) to eliminate
   * N+1 HTTP round-trips. Falls back to individual per-document requests if the
   * batch endpoint is unavailable (graceful degradation).
   */
  const vectorizeBatch = async (documentIds: string[]): Promise<{ succeeded: string[], failed: string[] }> => {
    const succeeded: string[] = []
    const failed: string[] = []

    // Mark all as pending before starting
    documentIds.forEach(id => setDocumentStatus(id, 'pending', 0))

    try {
      // Issue #2077: use single batch request instead of N+1 individual requests
      return await _tryBatchEndpoint(documentIds)
    } catch (batchError: unknown) {
      // Only fall back for 404/405 (endpoint not found); rethrow real errors
      const status = (batchError as Record<string, unknown>)?.response
        ? ((batchError as Record<string, Record<string, unknown>>).response?.status as number)
        : undefined
      if (status && status !== 404 && status !== 405) {
        throw batchError
      }

      logger.warn(
        'Batch vectorization endpoint unavailable, falling back to individual requests:',
        batchError
      )

      try {
        const results = await Promise.allSettled(
          documentIds.map(docId => vectorizeDocument(docId))
        )

        results.forEach((result, index) => {
          const docId = documentIds[index]
          if (result.status === 'fulfilled' && result.value) {
            succeeded.push(docId)
          } else {
            failed.push(docId)
          }
        })

        return { succeeded, failed }
      } catch (fallbackError) {
        logger.error('Fallback vectorization also failed:', fallbackError)
        documentIds.forEach(id => setDocumentStatus(id, 'failed', 0, String(fallbackError)))
        return { succeeded: [], failed: documentIds }
      }
    }
  }

  /**
   * Vectorize selected documents
   */
  const vectorizeSelected = async (): Promise<{ succeeded: string[], failed: string[] }> => {
    const documentIds = selectedDocumentsList.value
    const result = await vectorizeBatch(documentIds)

    // Clear selection after processing
    deselectAll()

    return result
  }

  /**
   * Start background vectorization for all non-vectorized documents
   * Uses existing backend endpoint
   */
  const startBackgroundVectorize = async () => {
    try {
      const result = await vectorizeFacts()

      // Start polling for status updates
      startPolling()

      return result
    } catch (error) {
      logger.error('Failed to start background vectorization:', error)
      throw error
    }
  }

  // ==================== STATUS POLLING ====================

  // Issue #5191: Back status polling with usePollingJob for auto-cleanup + race protection.
  type StatusResult = Awaited<ReturnType<typeof getVectorizationStatus>>

  const applyStatusUpdate = (status: StatusResult | null) => {
    if (!status) return
    globalProgress.value = {
      total: status.total_facts || 0,
      completed: status.vectorized_facts || 0,
      failed: 0,
      inProgress: status.pending_vectorization || 0
    }
  }

  const fetchStatus = async (): Promise<StatusResult | null> => {
    const status = await getVectorizationStatus()
    applyStatusUpdate(status ?? null)
    return status ?? null
  }

  // Mirrors the polling job's lifecycle; allows callers to configure intervalMs on each start.
  const isPolling = ref(false)
  let statusJob: ReturnType<typeof usePollingJob<StatusResult | null>> | null = null

  /**
   * Poll vectorization status from backend (standalone — one-shot status fetch).
   * Preserved for direct invocation by consumers that want a single status read.
   * Does NOT start or drive the polling loop.
   */
  const pollStatus = async () => {
    try {
      const status = await fetchStatus()
      if (status && (status.status === 'completed' || status.status === 'idle')) {
        stopPolling()
      }
    } catch (error) {
      logger.error('Failed to poll vectorization status:', error)
    }
  }

  /**
   * Start polling for status updates.
   * No-op if already polling (idempotent, preserves legacy contract).
   */
  const startPolling = (intervalMs: number = 2000) => {
    if (isPolling.value) return

    statusJob = usePollingJob<StatusResult | null>(fetchStatus, {
      intervalMs,
      maxAttempts: Number.MAX_SAFE_INTEGER, // lifecycle is caller-managed
      isComplete: (status) =>
        status?.status === 'completed' || status?.status === 'idle',
      onDone: () => {
        isPolling.value = false
      }
    })

    isPolling.value = true
    statusJob.start('')
  }

  /**
   * Stop polling for status updates
   */
  const stopPolling = () => {
    if (statusJob) {
      statusJob.stop()
      statusJob = null
    }
    isPolling.value = false
  }

  // ==================== CLEANUP ====================

  /**
   * Cleanup function to stop polling and clear state
   * Issue #4006: Also clears request cache
   */
  const cleanup = () => {
    stopPolling()
    clearAllStatuses()
    deselectAll()
    clearRequestCache() // Issue #4006: Clear request cache on cleanup
  }

  // ==================== RETURN PUBLIC API ====================

  return {
    // State
    documentStates,
    selectedDocuments,
    isPolling,
    globalProgress,

    // Computed
    hasSelection,
    selectionCount,
    selectedDocumentsList,
    canVectorizeSelection,

    // Document status (synchronous - reads from cache)
    getDocumentStatus,
    setDocumentStatus,
    clearDocumentStatus,
    clearAllStatuses,
    markDocumentChanged,  // Issue #165: Track document changes

    // Document status fetching (async - loads from backend)
    fetchDocumentStatus,
    fetchBatchStatus,

    // Selection management
    toggleDocumentSelection,
    selectDocument,
    deselectDocument,
    selectAll,
    deselectAll,
    isDocumentSelected,

    // Vectorization operations
    vectorizeDocument,
    vectorizeBatch,
    vectorizeSelected,
    startBackgroundVectorize,

    // Status polling
    pollStatus,
    startPolling,
    stopPolling,

    // Cleanup
    cleanup
  }
}
