/**
 * useKnowledgeVectorization Composable
 *
 * Manages vectorization state, batch operations, and status tracking for knowledge base documents.
 * Provides hooks for backend integration when individual document vectorization endpoints are available.
 */

import { ref, computed } from 'vue'
import { useKnowledgeBase } from './useKnowledgeBase'
import apiClient from '@/utils/ApiClient'
import appConfig from '@/config/AppConfig.js'
import { parseApiResponse } from '@/utils/apiResponseHelpers'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for useKnowledgeVectorization
const logger = createLogger('useKnowledgeVectorization')

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
  const { vectorizeFacts, getVectorizationStatus } = useKnowledgeBase()

  // State
  const documentStates = ref<Map<string, DocumentVectorizationState>>(new Map())
  const selectedDocuments = ref<Set<string>>(new Set())
  const isPolling = ref(false)
  const pollInterval = ref<number | null>(null)
  const globalProgress = ref<VectorizationProgress>({
    total: 0,
    completed: 0,
    failed: 0,
    inProgress: 0
  })

  // Computed
  const hasSelection = computed(() => selectedDocuments.value.size > 0)

  const selectionCount = computed(() => selectedDocuments.value.size)

  const selectedDocumentsList = computed(() => Array.from(selectedDocuments.value))

  const canVectorizeSelection = computed(() => {
    return selectedDocumentsList.value.some(docId => {
      const state = documentStates.value.get(docId)
      return !state || state.status !== 'vectorized'
    })
  })

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
      const response = await apiClient.post('/api/knowledge_base/vectorization_status', {
        fact_ids: [documentId],
        use_cache: true
      })
      const data = await parseApiResponse(response)

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
   * Fetch vectorization status for multiple documents in batch
   * More efficient than calling fetchDocumentStatus individually
   *
   * @param documentIds - List of document IDs to check
   * @param documentNames - Optional map of document ID to display name (Issue #165)
   */
  const fetchBatchStatus = async (
    documentIds: string[],
    documentNames?: Map<string, string>
  ): Promise<void> => {
    if (documentIds.length === 0) return

    try {
      // Query backend in batches of 1000 (API limit)
      const batchSize = 1000
      for (let i = 0; i < documentIds.length; i += batchSize) {
        const batch = documentIds.slice(i, i + batchSize)

        const response = await apiClient.post('/api/knowledge_base/vectorization_status', {
          fact_ids: batch,
          use_cache: true
        })
        const data = await parseApiResponse(response)

        if (data?.statuses) {
          // Update cache with all statuses, including document names if provided (Issue #165)
          Object.entries(data.statuses).forEach(([docId, statusData]: [string, any]) => {
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

  /**
   * Toggle document selection
   */
  const toggleDocumentSelection = (documentId: string) => {
    if (selectedDocuments.value.has(documentId)) {
      selectedDocuments.value.delete(documentId)
    } else {
      selectedDocuments.value.add(documentId)
    }
  }

  /**
   * Select document
   */
  const selectDocument = (documentId: string) => {
    selectedDocuments.value.add(documentId)
  }

  /**
   * Deselect document
   */
  const deselectDocument = (documentId: string) => {
    selectedDocuments.value.delete(documentId)
  }

  /**
   * Select all documents
   */
  const selectAll = (documentIds: string[]) => {
    documentIds.forEach(id => selectedDocuments.value.add(id))
  }

  /**
   * Deselect all documents
   */
  const deselectAll = () => {
    selectedDocuments.value.clear()
  }

  /**
   * Check if document is selected
   */
  const isDocumentSelected = (documentId: string): boolean => {
    return selectedDocuments.value.has(documentId)
  }

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
      // Issue #648: Use parseApiResponse to handle both Response objects and parsed JSON
      const response = await apiClient.post(`/api/knowledge_base/vectorize_fact/${documentId}`, undefined, {
        timeout: knowledgeTimeout
      })

      // Parse JSON response (handles both ApiClient.ts Response and ApiClient.js parsed JSON)
      const data = await parseApiResponse(response)

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
        // Issue #648: Use parseApiResponse to handle both Response objects and parsed JSON
        const jobResponse = await apiClient.get(`/api/knowledge_base/vectorize_job/${jobId}`, {
          timeout: knowledgeTimeout
        })
        const jobData = await parseApiResponse(jobResponse)

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
   * Vectorize multiple documents in batch
   * TODO: Replace with actual backend call when batch vectorization endpoint is available
   *
   * Expected endpoint: POST /api/knowledge_base/vectorize_documents
   * Body: { document_ids: string[] }
   */
  const vectorizeBatch = async (documentIds: string[]): Promise<{ succeeded: string[], failed: string[] }> => {
    const succeeded: string[] = []
    const failed: string[] = []

    try {
      // Mark all as pending
      documentIds.forEach(id => setDocumentStatus(id, 'pending', 0))

      // Process documents in parallel using Promise.allSettled - eliminates N+1 sequential calls
      const results = await Promise.allSettled(
        documentIds.map(docId => vectorizeDocument(docId))
      )

      // Process results
      results.forEach((result, index) => {
        const docId = documentIds[index]
        if (result.status === 'fulfilled' && result.value) {
          succeeded.push(docId)
        } else {
          failed.push(docId)
        }
      })

      return { succeeded, failed }
    } catch (error) {
      logger.error('Failed to vectorize batch:', error)
      documentIds.forEach(id => setDocumentStatus(id, 'failed', 0, String(error)))
      return { succeeded, failed: documentIds }
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

  /**
   * Poll vectorization status from backend
   */
  const pollStatus = async () => {
    try {
      const status = await getVectorizationStatus()

      if (status) {
        // Update global progress using correct property names
        globalProgress.value = {
          total: status.total_facts || 0,
          completed: status.vectorized_facts || 0,
          failed: 0, // Not provided by backend, calculate from document states if needed
          inProgress: status.pending_vectorization || 0
        }

        // Stop polling if complete
        if (status.status === 'completed' || status.status === 'idle') {
          stopPolling()
        }
      }
    } catch (error) {
      logger.error('Failed to poll vectorization status:', error)
    }
  }

  /**
   * Start polling for status updates
   */
  const startPolling = (intervalMs: number = 2000) => {
    if (isPolling.value) return

    isPolling.value = true
    pollInterval.value = window.setInterval(pollStatus, intervalMs)
  }

  /**
   * Stop polling for status updates
   */
  const stopPolling = () => {
    if (pollInterval.value) {
      clearInterval(pollInterval.value)
      pollInterval.value = null
    }
    isPolling.value = false
  }

  // ==================== CLEANUP ====================

  /**
   * Cleanup function to stop polling and clear state
   */
  const cleanup = () => {
    stopPolling()
    clearAllStatuses()
    deselectAll()
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
