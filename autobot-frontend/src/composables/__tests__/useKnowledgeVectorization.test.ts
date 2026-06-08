// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * Unit Tests for useKnowledgeVectorization Composable (Sprint 2 #162)
 *
 * Tests the vectorization composable:
 * - Status polling mechanism
 * - Batch status fetching
 * - Request deduplication (Issue #4006)
 * - Error handling
 * - Cleanup on unmount
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { useKnowledgeVectorization } from '../useKnowledgeVectorization'

// Mock useKnowledgeJobs composable (migrated from useKnowledgeBase BC shim in #5193)
vi.mock('../knowledge/useKnowledgeJobs', () => ({
  useKnowledgeJobs: vi.fn(() => ({
    vectorizeFacts: vi.fn(),
    getVectorizationStatus: vi.fn()
  }))
}))

// Mock ApiClient
vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn()
  }
}))


describe('useKnowledgeVectorization', () => {
  let composable: ReturnType<typeof useKnowledgeVectorization>

  beforeEach(() => {
    composable = useKnowledgeVectorization()
    vi.clearAllMocks()
  })

  afterEach(() => {
    composable.cleanup()
  })

  // ============================================================================
  // DOCUMENT STATE MANAGEMENT TESTS
  // ============================================================================

  describe('Document State Management', () => {
    it('should get document status from cache', () => {
      const docId = 'doc_123'
      composable.setDocumentStatus(docId, 'vectorized')

      const status = composable.getDocumentStatus(docId)

      expect(status).toBe('vectorized')
    })

    it('should return pending for unknown document', () => {
      const status = composable.getDocumentStatus('unknown_doc')

      expect(status).toBe('pending')
    })

    it('should set document status with progress', () => {
      const docId = 'doc_123'
      composable.setDocumentStatus(docId, 'pending', 50)

      const state = composable.documentStates.value.get(docId)

      expect(state).toBeDefined()
      expect(state?.status).toBe('pending')
      expect(state?.progress).toBe(50)
    })

    it('should set document status with error', () => {
      const docId = 'doc_123'
      const error = 'Vectorization failed'
      composable.setDocumentStatus(docId, 'failed', 0, error)

      const state = composable.documentStates.value.get(docId)

      expect(state?.status).toBe('failed')
      expect(state?.error).toBe(error)
    })

    it('should clear document status', () => {
      const docId = 'doc_123'
      composable.setDocumentStatus(docId, 'vectorized')
      composable.clearDocumentStatus(docId)

      const status = composable.getDocumentStatus(docId)

      expect(status).toBe('pending')
    })

    it('should clear all statuses', () => {
      composable.setDocumentStatus('doc_1', 'vectorized')
      composable.setDocumentStatus('doc_2', 'pending')
      composable.setDocumentStatus('doc_3', 'failed')

      composable.clearAllStatuses()

      expect(composable.documentStates.value.size).toBe(0)
    })
  })

  // ============================================================================
  // BATCH SELECTION MANAGEMENT TESTS
  // ============================================================================

  describe('Batch Selection Management', () => {
    it('should select document', () => {
      const docId = 'doc_123'
      composable.selectDocument(docId)

      expect(composable.isDocumentSelected(docId)).toBe(true)
      expect(composable.selectionCount.value).toBe(1)
    })

    it('should deselect document', () => {
      const docId = 'doc_123'
      composable.selectDocument(docId)
      composable.deselectDocument(docId)

      expect(composable.isDocumentSelected(docId)).toBe(false)
      expect(composable.selectionCount.value).toBe(0)
    })

    it('should toggle document selection', () => {
      const docId = 'doc_123'

      composable.toggleDocumentSelection(docId)
      expect(composable.isDocumentSelected(docId)).toBe(true)

      composable.toggleDocumentSelection(docId)
      expect(composable.isDocumentSelected(docId)).toBe(false)
    })

    it('should select all documents', () => {
      const docIds = ['doc_1', 'doc_2', 'doc_3']
      composable.selectAll(docIds)

      expect(composable.selectionCount.value).toBe(3)
      expect(composable.selectedDocumentsList.value).toEqual(expect.arrayContaining(docIds))
    })

    it('should deselect all documents', () => {
      composable.selectAll(['doc_1', 'doc_2', 'doc_3'])
      composable.deselectAll()

      expect(composable.selectionCount.value).toBe(0)
      expect(composable.hasSelection.value).toBe(false)
    })

    it('should compute hasSelection correctly', () => {
      expect(composable.hasSelection.value).toBe(false)

      composable.selectDocument('doc_1')
      expect(composable.hasSelection.value).toBe(true)

      composable.deselectAll()
      expect(composable.hasSelection.value).toBe(false)
    })

    it('should compute canVectorizeSelection correctly', () => {
      // All vectorized - cannot vectorize
      composable.selectDocument('doc_1')
      composable.setDocumentStatus('doc_1', 'vectorized')
      expect(composable.canVectorizeSelection.value).toBe(false)

      // Has pending - can vectorize
      composable.selectDocument('doc_2')
      composable.setDocumentStatus('doc_2', 'pending')
      expect(composable.canVectorizeSelection.value).toBe(true)
    })
  })

  // ============================================================================
  // BATCH STATUS FETCHING TESTS
  // ============================================================================

  describe('Batch Status Fetching', () => {
    it('should fetch batch status and update cache', async () => {
      const apiClient = await import('@/utils/ApiClient')
      apiClient.default.post = vi.fn().mockResolvedValue({
          statuses: {
            doc_1: { vectorized: true },
            doc_2: { vectorized: false },
            doc_3: { vectorized: true }
          }
        })

      await composable.fetchBatchStatus(['doc_1', 'doc_2', 'doc_3'])

      expect(composable.getDocumentStatus('doc_1')).toBe('vectorized')
      expect(composable.getDocumentStatus('doc_2')).toBe('pending')
      expect(composable.getDocumentStatus('doc_3')).toBe('vectorized')
    })

    it('should handle empty batch gracefully', async () => {
      await composable.fetchBatchStatus([])

      // Should not throw error
      expect(composable.documentStates.value.size).toBe(0)
    })

    it('should handle API error in batch fetch', async () => {
      const apiClient = await import('@/utils/ApiClient')
      apiClient.default.post = vi.fn().mockRejectedValue(new Error('Network error'))

      await composable.fetchBatchStatus(['doc_1', 'doc_2'])

      // Should mark all as unknown on error
      expect(composable.getDocumentStatus('doc_1')).toBe('unknown')
      expect(composable.getDocumentStatus('doc_2')).toBe('unknown')
    })

    it('should batch requests in chunks of 1000', async () => {
      const apiClient = await import('@/utils/ApiClient')
      apiClient.default.post = vi.fn().mockResolvedValue({ statuses: {} })

      // Create 2500 document IDs (should require 3 batches)
      const docIds = Array.from({ length: 2500 }, (_, i) => `doc_${i}`)

      await composable.fetchBatchStatus(docIds)

      // Should have made 3 API calls
      expect(apiClient.default.post).toHaveBeenCalledTimes(3)
    })
  })

  // ============================================================================
  // REQUEST DEDUPLICATION TESTS (Issue #4006)
  // ============================================================================

  describe('Request Deduplication (Issue #4006)', () => {
    it('should deduplicate identical batch requests within TTL', async () => {
      const apiClient = await import('@/utils/ApiClient')
      apiClient.default.post = vi.fn().mockResolvedValue({
          statuses: {
            doc_1: { vectorized: true },
            doc_2: { vectorized: false }
          }
        })

      // Make first request
      const docIds = ['doc_1', 'doc_2']
      await composable.fetchBatchStatus(docIds)

      // Make identical request (should use cache)
      await composable.fetchBatchStatus(docIds)

      // Should only make one API call (deduplication working)
      expect(apiClient.default.post).toHaveBeenCalledTimes(1)
    })

    it('should deduplicate requests with different order but same IDs', async () => {
      const apiClient = await import('@/utils/ApiClient')
      apiClient.default.post = vi.fn().mockResolvedValue({
          statuses: {
            doc_1: { vectorized: true },
            doc_2: { vectorized: false },
            doc_3: { vectorized: true }
          }
        })

      // First request: [doc_1, doc_2, doc_3]
      await composable.fetchBatchStatus(['doc_1', 'doc_2', 'doc_3'])

      // Second request with different order: [doc_3, doc_1, doc_2]
      // Should use cache because sorted keys are identical
      await composable.fetchBatchStatus(['doc_3', 'doc_1', 'doc_2'])

      // Should only make one API call (order-invariant cache key)
      expect(apiClient.default.post).toHaveBeenCalledTimes(1)
    })

    it('should make new request for different batch IDs', async () => {
      const apiClient = await import('@/utils/ApiClient')
      apiClient.default.post = vi.fn().mockResolvedValue({
          statuses: {
            doc_1: { vectorized: true },
            doc_2: { vectorized: false },
            doc_3: { vectorized: true }
          }
        })

      // First request
      await composable.fetchBatchStatus(['doc_1', 'doc_2'])

      // Second request with different IDs
      await composable.fetchBatchStatus(['doc_3', 'doc_4'])

      // Should make two API calls (different batches)
      expect(apiClient.default.post).toHaveBeenCalledTimes(2)
    })

    it('should clear request cache on cleanup', async () => {
      const apiClient = await import('@/utils/ApiClient')
      apiClient.default.post = vi.fn().mockResolvedValue({
          statuses: {
            doc_1: { vectorized: true }
          }
        })

      // Make a request to populate cache
      await composable.fetchBatchStatus(['doc_1'])

      // Clear mocks
      vi.clearAllMocks()
      apiClient.default.post = vi.fn().mockResolvedValue({
        statuses: {
          doc_1: { vectorized: true }
        }
      })

      // Cleanup should clear the cache
      composable.cleanup()

      // Make the same request again
      await composable.fetchBatchStatus(['doc_1'])

      // Should make a new API call because cache was cleared
      expect(apiClient.default.post).toHaveBeenCalledTimes(1)
    })

    it('should handle concurrent requests to same batch', async () => {
      const apiClient = await import('@/utils/ApiClient')
      apiClient.default.post = vi.fn().mockResolvedValue({
          statuses: {
            doc_1: { vectorized: true },
            doc_2: { vectorized: false }
          }
        })

      // Make concurrent requests for the same batch
      const docIds = ['doc_1', 'doc_2']
      const promises = [
        composable.fetchBatchStatus(docIds),
        composable.fetchBatchStatus(docIds),
        composable.fetchBatchStatus(docIds)
      ]

      await Promise.all(promises)

      // All should resolve successfully
      expect(composable.getDocumentStatus('doc_1')).toBe('vectorized')
      expect(composable.getDocumentStatus('doc_2')).toBe('pending')

      // First request goes to API, subsequent use cache
      expect(apiClient.default.post).toHaveBeenCalledTimes(1)
    })
  })

  // ============================================================================
  // STATUS POLLING TESTS
  // ============================================================================

  describe('Status Polling', () => {
    it('should start polling', () => {
      composable.startPolling(1000)

      expect(composable.isPolling.value).toBe(true)
    })

    it('should stop polling', () => {
      composable.startPolling(1000)
      composable.stopPolling()

      expect(composable.isPolling.value).toBe(false)
    })

    it('should not start polling if already polling', () => {
      composable.startPolling(1000)
      expect(composable.isPolling.value).toBe(true)

      // Calling startPolling again should not cause issues
      composable.startPolling(1000)
      expect(composable.isPolling.value).toBe(true)

      composable.stopPolling()
      expect(composable.isPolling.value).toBe(false)
    })

    it('should update global progress on poll', async () => {
      const { useKnowledgeJobs } = await import('../knowledge/useKnowledgeJobs')
      const mockGetStatus = vi.fn().mockResolvedValue({
        status: 'in_progress',
        total_facts: 100,
        vectorized_facts: 45,
        pending_vectorization: 55
      })

      vi.mocked(useKnowledgeJobs).mockReturnValue({
        getVectorizationStatus: mockGetStatus
      } as unknown as ReturnType<typeof useKnowledgeJobs>)

      const freshComposable = useKnowledgeVectorization()
      await freshComposable.pollStatus()

      expect(freshComposable.globalProgress.value.total).toBe(100)
      expect(freshComposable.globalProgress.value.completed).toBe(45)
      expect(freshComposable.globalProgress.value.inProgress).toBe(55)

      freshComposable.cleanup()
    })

    it('should stop polling when job completes', async () => {
      const { useKnowledgeJobs } = await import('../knowledge/useKnowledgeJobs')
      const mockGetStatus = vi.fn().mockResolvedValue({
        status: 'completed',
        total_facts: 100,
        vectorized_facts: 100,
        pending_vectorization: 0
      })

      vi.mocked(useKnowledgeJobs).mockReturnValue({
        getVectorizationStatus: mockGetStatus
      } as unknown as ReturnType<typeof useKnowledgeJobs>)

      const freshComposable = useKnowledgeVectorization()
      freshComposable.startPolling(100)
      await freshComposable.pollStatus()

      expect(freshComposable.isPolling.value).toBe(false)

      freshComposable.cleanup()
    })

    it('should handle polling errors gracefully', async () => {
      const { useKnowledgeJobs } = await import('../knowledge/useKnowledgeJobs')
      const mockGetStatus = vi.fn().mockRejectedValue(new Error('API error'))

      vi.mocked(useKnowledgeJobs).mockReturnValue({
        getVectorizationStatus: mockGetStatus
      } as unknown as ReturnType<typeof useKnowledgeJobs>)

      const freshComposable = useKnowledgeVectorization()

      // Should not throw
      await expect(freshComposable.pollStatus()).resolves.toBeUndefined()

      freshComposable.cleanup()
    })
  })

  // ============================================================================
  // VECTORIZATION OPERATIONS TESTS
  // ============================================================================

  describe('Vectorization Operations', () => {
    it('should vectorize single document successfully', async () => {
      const apiClient = await import('@/utils/ApiClient')

      // Mock vectorize start
      // Mock job completion
      apiClient.default.post = vi.fn().mockResolvedValue({
          status: 'success',
          job_id: 'job_123'
        })
      apiClient.default.get = vi.fn().mockResolvedValue({
          status: 'success',
          job: { status: 'completed', error: null }
        })

      const success = await composable.vectorizeDocument('doc_123')

      expect(success).toBe(true)
      expect(composable.getDocumentStatus('doc_123')).toBe('vectorized')
    })

    it('should handle vectorization failure', async () => {
      const apiClient = await import('@/utils/ApiClient')

      apiClient.default.post = vi.fn().mockResolvedValue({
          status: 'error',
          message: 'Vectorization failed'
        })

      const success = await composable.vectorizeDocument('doc_123')

      expect(success).toBe(false)
      expect(composable.getDocumentStatus('doc_123')).toBe('failed')
    })

    it('should vectorize batch of documents', async () => {
      const apiClient = await import('@/utils/ApiClient')

      // Fix (#2641): vectorizeBatch first calls _tryBatchEndpoint which expects
      // data.results array from POST /api/knowledge_base/vectorize_documents.
      // Mock the batch endpoint response format correctly.
      apiClient.default.post = vi.fn().mockResolvedValue({
          results: [
            { id: 'doc_1', status: 'success' },
            { id: 'doc_2', status: 'success' },
            { id: 'doc_3', status: 'success' }
          ]
        })

      const result = await composable.vectorizeBatch(['doc_1', 'doc_2', 'doc_3'])

      expect(result.succeeded.length).toBeGreaterThan(0)
    })

    it('should vectorize selected documents and clear selection', async () => {
      composable.selectAll(['doc_1', 'doc_2'])

      const apiClient = await import('@/utils/ApiClient')

      // Mock batch endpoint response for vectorizeSelected -> vectorizeBatch
      apiClient.default.post = vi.fn().mockResolvedValue({
          results: [
            { id: 'doc_1', status: 'success' },
            { id: 'doc_2', status: 'success' }
          ]
        })

      await composable.vectorizeSelected()

      expect(composable.selectionCount.value).toBe(0)
    })
  })

  // ============================================================================
  // CLEANUP TESTS
  // ============================================================================

  describe('Cleanup', () => {
    it('should stop polling on cleanup', () => {
      composable.startPolling(1000)
      composable.cleanup()

      expect(composable.isPolling.value).toBe(false)
    })

    it('should clear all state on cleanup', () => {
      composable.setDocumentStatus('doc_1', 'vectorized')
      composable.selectDocument('doc_1')
      composable.startPolling(1000)

      composable.cleanup()

      expect(composable.documentStates.value.size).toBe(0)
      expect(composable.selectedDocuments.value.size).toBe(0)
      expect(composable.isPolling.value).toBe(false)
    })
  })

  // ============================================================================
  // ERROR HANDLING TESTS
  // ============================================================================

  describe('Error Handling', () => {
    it('should handle network errors in status fetch', async () => {
      const apiClient = await import('@/utils/ApiClient')
      apiClient.default.post = vi.fn().mockRejectedValue(new Error('Network error'))

      await composable.fetchDocumentStatus('doc_123')

      expect(composable.getDocumentStatus('doc_123')).toBe('unknown')
    })

    it('should handle malformed API responses', async () => {
      const apiClient = await import('@/utils/ApiClient')
      apiClient.default.post = vi.fn().mockResolvedValue({
          // Missing expected fields
          invalid: 'response'
        })

      await composable.fetchDocumentStatus('doc_123')

      // Should default to pending on invalid response
      expect(composable.getDocumentStatus('doc_123')).toBe('pending')
    })

    it('should handle timeout in job polling', async () => {
      // Fix (#2641): vectorizeDocument polls with setTimeout(1000) in a while
      // loop up to maxAttempts times.  Use fake timers to avoid real-time waits.
      vi.useFakeTimers()

      try {
        const apiClient = await import('@/utils/ApiClient')

        // Mock job that never completes
        apiClient.default.post = vi.fn().mockResolvedValue({ status: 'success', job_id: 'job_timeout' })
        apiClient.default.get = vi.fn().mockResolvedValue({
            status: 'success',
            job: { status: 'in_progress', error: null }
          })

        // Start vectorization (will enter polling loop)
        const promise = composable.vectorizeDocument('doc_timeout')

        // Advance all timers to exhaust the polling loop
        await vi.runAllTimersAsync()

        const success = await promise

        expect(success).toBe(false)
        expect(composable.getDocumentStatus('doc_timeout')).toBe('failed')
      } finally {
        vi.useRealTimers()
      }
    })
  })

  // ============================================================================
  // EDGE CASES TESTS
  // ============================================================================

  describe('Edge Cases', () => {
    it('should handle document ID with special characters', async () => {
      const docId = 'doc:123-abc_def'
      composable.setDocumentStatus(docId, 'vectorized')

      expect(composable.getDocumentStatus(docId)).toBe('vectorized')
    })

    it('should handle very large selection', () => {
      const largeSelection = Array.from({ length: 10000 }, (_, i) => `doc_${i}`)
      composable.selectAll(largeSelection)

      expect(composable.selectionCount.value).toBe(10000)
    })

    it('should handle rapid status updates', () => {
      const docId = 'doc_123'

      composable.setDocumentStatus(docId, 'pending', 0)
      composable.setDocumentStatus(docId, 'pending', 25)
      composable.setDocumentStatus(docId, 'pending', 50)
      composable.setDocumentStatus(docId, 'pending', 75)
      composable.setDocumentStatus(docId, 'vectorized', 100)

      expect(composable.getDocumentStatus(docId)).toBe('vectorized')
      const state = composable.documentStates.value.get(docId)
      expect(state?.progress).toBe(100)
    })

    it('should handle concurrent operations', async () => {
      const operations = [
        composable.fetchDocumentStatus('doc_1'),
        composable.fetchDocumentStatus('doc_2'),
        composable.fetchDocumentStatus('doc_3')
      ]

      // Should not throw
      await expect(Promise.all(operations)).resolves.toBeDefined()
    })
  })
})
