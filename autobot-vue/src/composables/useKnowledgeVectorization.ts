/**
 * useKnowledgeVectorization Composable
 *
 * Manages vectorization state, batch operations, and status tracking for knowledge base documents.
 * Provides hooks for backend integration when individual document vectorization endpoints are available.
 */

import { ref, computed } from 'vue'
import { useKnowledgeBase } from './useKnowledgeBase'

export type VectorizationStatus = 'vectorized' | 'pending' | 'failed' | 'unknown'

export interface DocumentVectorizationState {
  documentId: string
  status: VectorizationStatus
  progress?: number
  error?: string
  lastUpdated?: Date
}

export interface VectorizationProgress {
  total: number
  completed: number
  failed: number
  inProgress: number
}

export function useKnowledgeVectorization() {
  const { startBackgroundVectorization, getVectorizationStatus } = useKnowledgeBase()

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
   * Get vectorization status for a document
   * TODO: Replace with actual backend call when endpoint is available
   */
  const getDocumentStatus = (documentId: string): VectorizationStatus => {
    const state = documentStates.value.get(documentId)
    if (!state) {
      // MOCK DATA - Replace with actual backend call
      // For now, randomly assign status for demonstration
      const mockStatus = getMockStatus(documentId)
      setDocumentStatus(documentId, mockStatus)
      return mockStatus
    }
    return state.status
  }

  /**
   * Set vectorization status for a document
   */
  const setDocumentStatus = (
    documentId: string,
    status: VectorizationStatus,
    progress?: number,
    error?: string
  ) => {
    documentStates.value.set(documentId, {
      documentId,
      status,
      progress,
      error,
      lastUpdated: new Date()
    })
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
   * TODO: Replace with actual backend call when individual vectorization endpoint is available
   *
   * Expected endpoint: POST /api/knowledge_base/vectorize_document/{document_id}
   */
  const vectorizeDocument = async (documentId: string): Promise<boolean> => {
    try {
      setDocumentStatus(documentId, 'pending', 0)

      // PLACEHOLDER - Replace with actual API call
      // const response = await apiClient.post(`/api/knowledge_base/vectorize_document/${documentId}`)
      // const data = await response.json()

      // Simulate processing
      console.log(`[PLACEHOLDER] Vectorizing document: ${documentId}`)

      // Simulate progress updates
      for (let i = 0; i <= 100; i += 20) {
        await new Promise(resolve => setTimeout(resolve, 200))
        setDocumentStatus(documentId, 'pending', i)
      }

      // Mark as completed
      setDocumentStatus(documentId, 'vectorized', 100)

      return true
    } catch (error) {
      console.error('Failed to vectorize document:', error)
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

      // PLACEHOLDER - Replace with actual batch API call
      // const response = await apiClient.post('/api/knowledge_base/vectorize_documents', {
      //   document_ids: documentIds
      // })
      // const data = await response.json()

      console.log(`[PLACEHOLDER] Vectorizing batch of ${documentIds.length} documents`)

      // Simulate batch processing
      for (const docId of documentIds) {
        const success = await vectorizeDocument(docId)
        if (success) {
          succeeded.push(docId)
        } else {
          failed.push(docId)
        }
      }

      return { succeeded, failed }
    } catch (error) {
      console.error('Failed to vectorize batch:', error)
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
      const result = await startBackgroundVectorization()
      console.log('Background vectorization started:', result)

      // Start polling for status updates
      startPolling()

      return result
    } catch (error) {
      console.error('Failed to start background vectorization:', error)
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
        // Update global progress
        globalProgress.value = {
          total: status.total_documents || 0,
          completed: status.completed || 0,
          failed: status.failed || 0,
          inProgress: status.in_progress || 0
        }

        // Stop polling if complete
        if (status.status === 'completed' || status.status === 'idle') {
          stopPolling()
        }
      }
    } catch (error) {
      console.error('Failed to poll vectorization status:', error)
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

  // ==================== MOCK DATA (TEMPORARY) ====================

  /**
   * Generate mock status for demonstration
   * TODO: Remove when backend endpoints are available
   */
  const getMockStatus = (documentId: string): VectorizationStatus => {
    // Use document ID hash to generate consistent random status
    const hash = documentId.split('').reduce((acc, char) => {
      return char.charCodeAt(0) + ((acc << 5) - acc)
    }, 0)

    const rand = Math.abs(hash % 100)

    if (rand < 60) return 'vectorized'  // 60% vectorized
    if (rand < 85) return 'pending'     // 25% pending
    if (rand < 95) return 'unknown'     // 10% unknown
    return 'failed'                      // 5% failed
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

    // Document status
    getDocumentStatus,
    setDocumentStatus,
    clearDocumentStatus,
    clearAllStatuses,

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
